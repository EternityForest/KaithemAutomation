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

    path = modules.filename_for_file_resource(module, name + ".content")
    return module, path


def _api(module: str, suffix: str) -> str:
    return f"/presentation-screen/api{suffix}/{module}/screen"


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
    response = await client.post(_api(module, "/save/deck.pptx"), data=payload)
    assert response.status_code == 200

    response = await client.get(_api(module, "/files"))
    files = (await response.get_json())["files"]
    assert [f["name"] for f in files] == ["deck.pptx"]
    assert files[0]["size"] == len(payload)

    assert os.path.isfile(os.path.join(path, "deck.pptx"))

    response = await client.get(_api(module, "/file/deck.pptx"))
    assert response.status_code == 200
    assert await response.get_data() == payload
    assert response.headers["Cache-Control"] == "no-store"

    response = await client.post(_api(module, "/delete/deck.pptx"))
    assert response.status_code == 200
    assert not os.path.exists(os.path.join(path, "deck.pptx"))

    response = await client.get(_api(module, "/file/deck.pptx"))
    assert response.status_code == 404


async def test_save_rejects_bad_input():
    module, _ = _make_screen()
    client = await make_client()

    response = await client.post(_api(module, "/save/notes.txt"), data=b"PK")
    assert response.status_code == 400

    response = await client.post(_api(module, "/save/../evil.pptx"), data=b"PK")
    assert response.status_code in (400, 404)

    response = await client.post(_api(module, "/save/empty.pptx"), data=b"")
    assert response.status_code == 400

    response = await client.post(
        _api(module, "/save/notzip.pptx"), data=b"not a zip"
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
    response = await admin.post(_api(module, "/save/guest.pptx"), data=b"PKok")
    assert response.status_code == 200
    response = await guest.get(_api(module, "/file/guest.pptx"))
    assert response.status_code == 200

    response = await admin.post(
        _api(module, "/config"),
        json={"view_requires_admin": True},
    )
    assert response.status_code == 200
    assert (await response.get_json())["view_requires_admin"] is True

    response = await guest.get(_api(module, "/file/guest.pptx"))
    assert response.status_code in (401, 403)
    response = await guest.get(_api(module, "/files"))
    assert response.status_code in (401, 403)

    # Admin keeps access.
    response = await admin.get(_api(module, "/file/guest.pptx"))
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

    response = await guest.post(_api(module, "/save/x.pptx"), data=b"PK")
    assert response.status_code in (401, 403)

    response = await guest.post(_api(module, "/delete/x.pptx"))
    assert response.status_code in (401, 403)


async def test_commands_validate_and_broadcast(monkeypatch):
    from kaithem.src.plugins import CorePluginPresentationScreen as plugin

    module, _ = _make_screen()
    client = await make_client()

    sent: list[dict] = []

    def fake_broadcast(_module, _resource, payload):
        sent.append(payload)

    monkeypatch.setattr(plugin, "_broadcast", fake_broadcast)

    response = await client.post(_api(module, "/save/deck.pptx"), data=b"PKok")
    assert response.status_code == 200

    for action in ("next", "prev", "stop"):
        response = await client.post(
            _api(module, "/command"), json={"action": action}
        )
        assert response.status_code == 200

    response = await client.post(
        _api(module, "/command"), json={"action": "load", "file": "deck.pptx"}
    )
    assert response.status_code == 200

    response = await client.post(
        _api(module, "/command"), json={"action": "goto", "slide": 3}
    )
    assert response.status_code == 200

    assert sent == [
        {"action": "next"},
        {"action": "prev"},
        {"action": "stop"},
        {"action": "load", "file": "deck.pptx"},
        {"action": "goto", "slide": 3},
    ]

    # Invalid inputs never broadcast.
    for body in (
        {"action": "bogus"},
        {"action": "goto", "slide": -1},
        {"action": "goto", "slide": "2"},
        {"action": "load"},
        {"action": "load", "file": "missing.pptx"},
        {"action": "load", "file": "../deck.pptx"},
    ):
        response = await client.post(_api(module, "/command"), json=body)
        assert response.status_code in (400, 404)

    assert len(sent) == 5


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


async def test_websocket_broadcasts_commands_to_all_viewers():
    import json

    module, _ = _make_screen()
    admin = await make_client()
    response = await admin.post(_api(module, "/save/deck.pptx"), data=b"PKok")
    assert response.status_code == 200

    url = f"/presentation-screen/ws/{module}/screen"
    async with admin.websocket(url) as first:
        assert json.loads(await first.receive()) == {"action": "ready"}

        async with admin.websocket(url) as second:
            assert json.loads(await second.receive()) == {"action": "ready"}

            response = await admin.post(
                _api(module, "/command"),
                json={"action": "load", "file": "deck.pptx"},
            )
            assert response.status_code == 200

            expected = {"action": "load", "file": "deck.pptx"}
            assert json.loads(await first.receive()) == expected
            assert json.loads(await second.receive()) == expected

            response = await admin.post(
                _api(module, "/command"), json={"action": "next"}
            )
            assert response.status_code == 200
            assert json.loads(await first.receive()) == {"action": "next"}
            assert json.loads(await second.receive()) == {"action": "next"}

            response = await admin.get(_api(module, "/status"))
            assert (await response.get_json())["connected"] == 2

    response = await admin.get(_api(module, "/status"))
    assert (await response.get_json())["connected"] == 0


async def test_websocket_viewing_respects_locked_setting():
    module, _ = _make_screen()
    admin = await make_client()
    guest = _guest_client()
    url = f"/presentation-screen/ws/{module}/screen"

    # Open by default: guests are accepted.
    connection = guest.websocket(url)
    async with connection:
        assert connection.accepted is True

    response = await admin.post(
        _api(module, "/config"), json={"view_requires_admin": True}
    )
    assert response.status_code == 200

    locked = guest.websocket(url)
    async with locked:
        pass
    assert locked.accepted is False
