import json
import os
import time

import pytest

from .helpers import make_client


def _guest_client():
    from kaithem.src import quart_app

    return quart_app.app.test_client(use_cookies=True)


def _make_screen(title: str = "Test Screen", name: str = "screen"):
    """Create a presentation_screen resource and return (module, path)."""
    from kaithem.api import modules as modules_api
    from kaithem.src import modules, modules_state

    module = "testpresentation" + str(time.time()).replace(".", "_")
    modules.newModule(module)

    resource_type = modules_state.resource_types["presentation_screen"]
    data = resource_type.on_create_request(module, name, {"title": title})
    resource_type._validate(data)
    with modules_api.modules_lock:
        modules_state.raw_insert_resource(module, name, data)
    resource_type.on_load(module, name, data)

    path = modules_api.filename_for_file_resource(module, name + ".content")
    return module, path


def _api(module: str, suffix: str) -> str:
    """URL for an endpoint keyed only by module and resource."""
    return f"/presentation-screen/api{suffix}/{module}/screen"


def _file_api(module: str, verb: str, filename: str) -> str:
    """URL for an endpoint that also takes a filename."""
    return f"/presentation-screen/api/{verb}/{module}/screen/{filename}"


async def test_resource_creates_content_folder():
    _, path = _make_screen()
    assert os.path.isdir(path)


async def test_save_list_get_delete_roundtrip():
    module, path = _make_screen()
    client = await make_client()

    response = await client.get(_api(module, "/files"))
    assert response.status_code == 200
    assert (await response.get_json())["files"] == []

    payload = b"PK\x03\x04fake-pptx-body"
    response = await client.post(
        _file_api(module, "save", "deck.pptx"), data=payload
    )
    assert response.status_code == 200

    response = await client.get(_api(module, "/files"))
    files = (await response.get_json())["files"]
    assert [f["name"] for f in files] == ["deck.pptx"]
    assert files[0]["size"] == len(payload)

    assert os.path.isfile(os.path.join(path, "deck.pptx"))

    response = await client.get(_file_api(module, "file", "deck.pptx"))
    assert response.status_code == 200
    assert await response.get_data() == payload
    assert response.headers["Cache-Control"] == "no-store"

    response = await client.post(_file_api(module, "delete", "deck.pptx"))
    assert response.status_code == 200
    assert not os.path.exists(os.path.join(path, "deck.pptx"))

    response = await client.get(_file_api(module, "file", "deck.pptx"))
    assert response.status_code == 404


async def test_save_rejects_bad_input():
    module, _ = _make_screen()
    client = await make_client()

    response = await client.post(
        _file_api(module, "save", "notes.txt"), data=b"PK"
    )
    assert response.status_code == 400

    response = await client.post(
        _file_api(module, "save", "../evil.pptx"), data=b"PK"
    )
    assert response.status_code in (400, 404)

    response = await client.post(
        _file_api(module, "save", "empty.pptx"), data=b""
    )
    assert response.status_code == 400

    response = await client.post(
        _file_api(module, "save", "notzip.pptx"), data=b"not a zip"
    )
    assert response.status_code == 400


async def test_config_defaults_open_and_admin_can_lock():
    module, _ = _make_screen()
    admin = await make_client()
    guest = _guest_client()

    response = await guest.get(_api(module, "/config"))
    assert response.status_code == 200
    assert (await response.get_json())["view_requires_admin"] is False

    # Open viewing: guests may fetch files (once one exists).
    response = await admin.post(
        _file_api(module, "save", "guest.pptx"), data=b"PKok"
    )
    assert response.status_code == 200
    response = await guest.get(_file_api(module, "file", "guest.pptx"))
    assert response.status_code == 200
    # Viewers need the state to know what to show.
    response = await guest.get(_api(module, "/state"))
    assert response.status_code == 200
    assert (await response.get_json())["state"] == {"type": "none"}

    response = await admin.post(
        _api(module, "/config"),
        json={"view_requires_admin": True},
    )
    assert response.status_code == 200
    assert (await response.get_json())["view_requires_admin"] is True

    response = await guest.get(_file_api(module, "file", "guest.pptx"))
    assert response.status_code in (401, 403)
    response = await guest.get(_api(module, "/files"))
    assert response.status_code in (401, 403)
    response = await guest.get(_api(module, "/state"))
    assert response.status_code in (401, 403)

    # Admin keeps access.
    response = await admin.get(_file_api(module, "file", "guest.pptx"))
    assert response.status_code == 200

    # And can unlock again.
    response = await admin.post(
        _api(module, "/config"),
        json={"view_requires_admin": False, "title": "Renamed"},
    )
    assert response.status_code == 200
    body = await response.get_json()
    assert body["view_requires_admin"] is False
    assert body["title"] == "Renamed"


async def test_set_config_validates_title():
    module, _ = _make_screen()
    client = await make_client()

    response = await client.post(_api(module, "/config"), json={"title": ""})
    assert response.status_code == 400

    response = await client.post(
        _api(module, "/config"), json={"title": "x" * 201}
    )
    assert response.status_code == 400


async def test_guest_cannot_save_or_delete():
    module, _ = _make_screen()
    guest = _guest_client()

    response = await guest.post(_file_api(module, "save", "x.pptx"), data=b"PK")
    assert response.status_code in (401, 403)

    response = await guest.post(_file_api(module, "delete", "x.pptx"))
    assert response.status_code in (401, 403)

    response = await guest.post(_api(module, "/state"), json={"type": "none"})
    assert response.status_code in (401, 403)

    response = await guest.post(_api(module, "/state-default"))
    assert response.status_code in (401, 403)


def _squash_state_broadcasts(monkeypatch):
    """Collect state broadcasts instead of putting them on the message bus."""
    from kaithem.src.plugins import CorePluginPresentationScreen as plugin

    sent: list[dict] = []
    monkeypatch.setattr(
        plugin, "_broadcast", lambda _m, _r, payload: sent.append(payload)
    )
    return sent


async def test_state_endpoint_replaces_the_whole_state(monkeypatch):
    module, _ = _make_screen()
    client = await make_client()
    sent = _squash_state_broadcasts(monkeypatch)

    response = await client.get(_api(module, "/state"))
    body = await response.get_json()
    assert body["state"] == {"type": "none"}
    assert body["default_state"] == {"type": "none"}

    response = await client.post(
        _file_api(module, "save", "deck.pptx"), data=b"PKok"
    )
    assert response.status_code == 200

    playing = {"type": "pptx", "file": "deck.pptx", "slide": 2}
    response = await client.post(_api(module, "/state"), json=playing)
    assert response.status_code == 200
    assert sent == [{"action": "state", "state": playing}]

    body = await (await client.get(_api(module, "/state"))).get_json()
    assert body["state"] == playing

    # Replacement is total: stopping drops the file and the slide.
    response = await client.post(_api(module, "/state"), json={"type": "none"})
    assert response.status_code == 200
    assert sent[-1] == {"action": "state", "state": {"type": "none"}}
    body = await (await client.get(_api(module, "/state"))).get_json()
    assert body["state"] == {"type": "none"}

    for body in (
        {"type": "bogus"},
        {"type": "pptx"},
        {"type": "pptx", "file": "deck.pptx", "slide": -1},
        {"type": "pptx", "file": "deck.pptx", "slide": "2"},
        {"type": "pptx", "file": "deck.pptx", "slide": True},
        {"type": "pptx", "file": "../deck.pptx"},
        ["nope"],
    ):
        response = await client.post(_api(module, "/state"), json=body)
        assert response.status_code == 400

    response = await client.post(
        _api(module, "/state"),
        json={"type": "pptx", "file": "missing.pptx", "slide": 0},
    )
    assert response.status_code == 404

    # Nothing invalid was published.
    assert len(sent) == 2


async def test_default_state_is_stored_in_the_resource(monkeypatch):
    from kaithem.src import modules_state
    from kaithem.src.plugins import CorePluginPresentationScreen as plugin

    module, _ = _make_screen()
    client = await make_client()
    _squash_state_broadcasts(monkeypatch)

    await client.post(_file_api(module, "save", "deck.pptx"), data=b"PKok")

    response = await client.post(_api(module, "/state-default"))
    assert response.status_code == 200
    assert (await response.get_json())["default_state"] == {"type": "none"}

    playing = {"type": "pptx", "file": "deck.pptx", "slide": 3}
    await client.post(_api(module, "/state"), json=playing)

    response = await client.post(_api(module, "/state-default"))
    assert response.status_code == 200
    assert (await response.get_json())["default_state"] == playing
    stored = modules_state.ActiveModules[module]["screen"]
    assert stored["default_state"] == playing

    # Without a live state (e.g. after a restart) the default is used.
    plugin._current_states.pop((module, "screen"), None)
    body = await (await client.get(_api(module, "/state"))).get_json()
    assert body["state"] == playing
    assert body["default_state"] == playing


async def test_deleting_the_playing_file_falls_back_to_the_default(monkeypatch):
    module, _ = _make_screen()
    client = await make_client()
    sent = _squash_state_broadcasts(monkeypatch)

    await client.post(_file_api(module, "save", "deck.pptx"), data=b"PKok")
    playing = {"type": "pptx", "file": "deck.pptx", "slide": 1}
    await client.post(_api(module, "/state"), json=playing)
    assert len(sent) == 1

    response = await client.post(_file_api(module, "delete", "deck.pptx"))
    assert response.status_code == 200
    assert sent[-1] == {"action": "state", "state": {"type": "none"}}


def test_sanitize_pptx_filename():
    from kaithem.src.plugins.CorePluginPresentationScreen import (
        sanitize_pptx_filename,
    )

    assert sanitize_pptx_filename("deck.pptx") == "deck.pptx"
    assert sanitize_pptx_filename("DECK.PPTX") == "DECK.PPTX"

    bad_names = (
        "",
        "deck",
        "deck.ppt",
        "a/b.pptx",
        "../b.pptx",
        ".pptx",
        "x" * 256,
    )
    for bad in bad_names:
        with pytest.raises(ValueError):
            sanitize_pptx_filename(bad)


def test_delete_removes_content_folder():
    from kaithem.src import modules_state

    module, path = _make_screen()
    assert os.path.isdir(path)

    resource_type = modules_state.resource_types["presentation_screen"]
    data = dict(modules_state.ActiveModules[module]["screen"])
    resource_type.on_delete(module, "screen", data)

    assert not os.path.exists(path)


async def test_websocket_broadcasts_state_to_all_viewers():
    module, _ = _make_screen()
    admin = await make_client()
    response = await admin.post(
        _file_api(module, "save", "deck.pptx"), data=b"PKok"
    )
    assert response.status_code == 200

    stopped = {"action": "state", "state": {"type": "none"}}
    url = f"/presentation-screen/ws/{module}/screen"
    async with admin.websocket(url) as first:
        # A fresh viewer starts from the server's state.
        assert json.loads(await first.receive()) == stopped

        async with admin.websocket(url) as second:
            assert json.loads(await second.receive()) == stopped

            playing = {"type": "pptx", "file": "deck.pptx", "slide": 0}
            response = await admin.post(_api(module, "/state"), json=playing)
            assert response.status_code == 200

            expected = {"action": "state", "state": playing}
            assert json.loads(await first.receive()) == expected
            assert json.loads(await second.receive()) == expected

            moved = {"type": "pptx", "file": "deck.pptx", "slide": 1}
            response = await admin.post(_api(module, "/state"), json=moved)
            assert response.status_code == 200
            expected = {"action": "state", "state": moved}
            assert json.loads(await first.receive()) == expected
            assert json.loads(await second.receive()) == expected

            response = await admin.get(_api(module, "/status"))
            assert (await response.get_json())["connected"] == 2

    response = await admin.get(_api(module, "/status"))
    assert (await response.get_json())["connected"] == 0


async def test_websocket_viewing_respects_locked_setting():
    module, _ = _make_screen()
    admin = await make_client()
    guest = _guest_client()
    url = f"/presentation-screen/ws/{module}/screen"

    # Open by default: guests are accepted and receive the current state.
    connection = guest.websocket(url)
    async with connection:
        assert json.loads(await connection.receive()) == {
            "action": "state",
            "state": {"type": "none"},
        }
        assert connection.accepted is True

    response = await admin.post(
        _api(module, "/config"), json={"view_requires_admin": True}
    )
    assert response.status_code == 200

    locked = guest.websocket(url)
    async with locked:
        pass
    assert locked.accepted is False


async def test_editor_redirect_preserves_file_parameter():
    module, _ = _make_screen()
    client = await make_client()

    response = await client.get(
        f"/presentation-screen/editor/{module}/screen?file=deck.pptx",
        follow_redirects=False,
    )
    assert response.status_code in (301, 302, 303, 307, 308)
    location = response.headers["Location"]
    assert "file=deck.pptx" in location
    assert "module=" + module in location

    response = await client.get(
        f"/presentation-screen/editor/{module}/screen",
        follow_redirects=False,
    )
    assert response.status_code in (301, 302, 303, 307, 308)
    assert "file=" not in response.headers["Location"]
