# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the CorePluginTextEditor plugin.

Two layers are covered.  The workspace helper tests exercise the pure
path logic directly (marker detection, listing/pruning, traversal
rejection).  The web route tests drive the real file APIs, the LSP info
endpoint, the live-update websocket, and the ``/edit`` redirect against a
throwaway folder in the /dev/shm test sandbox, so the workspace contract
the frontend relies on is verified end to end.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import uuid

import pytest

from kaithem.src.plugins import CorePluginTextEditor as plugin
from kaithem.src.plugins.CorePluginTextEditor import lsp

from .helpers import make_client


def _write(path: str, name: str, text: str) -> None:
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, name), "w", encoding="utf-8") as handle:
        handle.write(text)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def workspace():
    """A throwaway server folder inside the /dev/shm test sandbox."""
    path = os.path.realpath(tempfile.mkdtemp(dir="/dev/shm/kaithem_tests"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# -- workspace detection --------------------------------------------------


def test_detect_workspace_prefers_the_innermost_marker(workspace):
    # A project marker makes a nested folder its own workspace even when a
    # bigger project surrounds it.
    _write(workspace, "pyproject.toml", "")
    sub = os.path.join(workspace, "sub")
    _write(sub, "package.json", "{}")

    assert lsp.detect_workspace(sub) == sub
    assert lsp.detect_workspace(os.path.join(sub, "a.txt")) == sub
    assert lsp.detect_workspace(workspace) == workspace


def test_detect_workspace_honours_the_kaithem_marker(workspace):
    # ``lsp-workspace.json`` is a marker in its own right, so a folder can
    # declare itself a workspace without looking like any one project type.
    sub = os.path.join(workspace, "data")
    _write(sub, "lsp-workspace.json", "{}")
    os.makedirs(os.path.join(sub, "deep", "deeper"))

    deep_file = os.path.join(sub, "deep", "deeper", "f.txt")
    assert lsp.detect_workspace(deep_file) == sub


def test_detect_workspace_falls_back_to_the_containing_folder(workspace):
    # With no marker anywhere the file's own folder is the workspace, which
    # is what makes opening a loose file still give a usable editor.
    nested = os.path.join(workspace, "files")
    _write(nested, "hello.txt", "hello")

    assert lsp.detect_workspace(os.path.join(nested, "hello.txt")) == nested
    assert lsp.detect_workspace(nested) == nested


# -- directory listing ----------------------------------------------------


def test_list_dir_prunes_dependencies_builds_and_hidden_entries(workspace):
    _write(workspace, "keep.txt", "k")
    _write(workspace, ".hidden.txt", "h")
    for name in sorted(plugin.PRUNED_DIRS):
        _write(os.path.join(workspace, name), "junk.js", "junk")
    # A file that only shares a name prefix must still be listed.
    _write(workspace, "dist.txt", "d")

    names = {entry["name"] for entry in plugin._list_dir(workspace)}

    assert names == {"keep.txt", "dist.txt"}


def test_list_dir_includes_nested_children(workspace):
    _write(os.path.join(workspace, "src"), "main.py", "print('hi')")

    tree = plugin._list_dir(workspace)
    assert [entry["name"] for entry in tree] == ["src"]
    assert tree[0]["type"] == "dir"
    assert [child["name"] for child in tree[0]["children"]] == ["main.py"]


def test_list_dir_tolerates_a_missing_folder(workspace):
    assert plugin._list_dir(os.path.join(workspace, "nope")) == []


# -- web routes -----------------------------------------------------------


async def test_api_rejects_guests(workspace):
    from kaithem.src import quart_app

    client = quart_app.app.test_client(use_cookies=True)
    response = await client.get(
        "/text-editor-plugin/api/list", query_string={"workspace": workspace}
    )
    assert response.status_code == 401
    assert (await response.get_json())["error"] == "not_logged_in"


async def test_api_write_read_round_trip(workspace):
    client = await make_client()
    written = await client.post(
        "/text-editor-plugin/api/write",
        form={"workspace": workspace, "path": "a/b.txt", "content": "hi"},
    )
    assert written.status_code == 200
    # The parent folder is created for the caller.
    assert _read(os.path.join(workspace, "a", "b.txt")) == "hi"

    read = await client.get(
        "/text-editor-plugin/api/read",
        query_string={"workspace": workspace, "path": "a/b.txt"},
    )
    assert read.status_code == 200
    assert (await read.get_json())["content"] == "hi"


async def test_api_read_reports_a_missing_file(workspace):
    client = await make_client()
    response = await client.get(
        "/text-editor-plugin/api/read",
        query_string={"workspace": workspace, "path": "nope.txt"},
    )
    assert response.status_code == 400
    assert (await response.get_json())["error"] == "not_a_file"


async def test_api_list_returns_the_tree(workspace):
    client = await make_client()
    _write(workspace, "hello.txt", "hello")
    _write(os.path.join(workspace, "src"), "main.py", "x = 1")

    response = await client.get(
        "/text-editor-plugin/api/list",
        query_string={"workspace": workspace, "path": ""},
    )
    assert response.status_code == 200
    names = [entry["name"] for entry in await response.get_json()]
    assert names == ["hello.txt", "src"]


async def test_api_list_of_a_missing_folder_is_empty(workspace):
    client = await make_client()
    response = await client.get(
        "/text-editor-plugin/api/list",
        query_string={"workspace": workspace, "path": "nope"},
    )
    assert response.status_code == 200
    assert await response.get_json() == []


async def test_api_new_file_folder_rename_delete_round_trip(workspace):
    client = await make_client()

    made_file = await client.post(
        "/text-editor-plugin/api/new_file",
        form={"workspace": workspace, "path": "docs/readme.md"},
    )
    assert made_file.status_code == 200
    assert os.path.isfile(os.path.join(workspace, "docs", "readme.md"))

    made_folder = await client.post(
        "/text-editor-plugin/api/new_folder",
        form={"workspace": workspace, "path": "docs/images"},
    )
    assert made_folder.status_code == 200
    assert os.path.isdir(os.path.join(workspace, "docs", "images"))

    # A second create of the same path is a client error, not a crash.
    clash = await client.post(
        "/text-editor-plugin/api/new_file",
        form={"workspace": workspace, "path": "docs/readme.md"},
    )
    assert clash.status_code == 400
    assert (await clash.get_json())["error"] == "exists"

    renamed = await client.post(
        "/text-editor-plugin/api/rename",
        form={
            "workspace": workspace,
            "path": "docs/readme.md",
            "new_name": "guide.md",
        },
    )
    assert renamed.status_code == 200
    assert os.path.isfile(os.path.join(workspace, "docs", "guide.md"))

    deleted = await client.post(
        "/text-editor-plugin/api/delete",
        form={"workspace": workspace, "path": "docs"},
    )
    assert deleted.status_code == 200
    assert not os.path.exists(os.path.join(workspace, "docs"))


async def test_api_rename_rejects_a_path_in_the_name(workspace):
    client = await make_client()
    _write(workspace, "a.txt", "a")
    response = await client.post(
        "/text-editor-plugin/api/rename",
        form={
            "workspace": workspace,
            "path": "a.txt",
            "new_name": "../escape.txt",
        },
    )
    assert response.status_code == 400
    assert (await response.get_json())["error"] == "invalid_name"


@pytest.mark.parametrize(
    "bad_path",
    ["../outside.txt", "a/../../outside.txt", "/etc/passwd"],
)
async def test_api_rejects_paths_outside_the_workspace(workspace, bad_path):
    client = await make_client()

    read = await client.get(
        "/text-editor-plugin/api/read",
        query_string={"workspace": workspace, "path": bad_path},
    )
    assert read.status_code == 400
    assert (await read.get_json())["error"] == "bad_request"

    written = await client.post(
        "/text-editor-plugin/api/write",
        form={"workspace": workspace, "path": bad_path, "content": "x"},
    )
    assert written.status_code == 400
    assert (await written.get_json())["error"] == "bad_request"
    # Nothing leaked outside the workspace as a side effect.
    escaped = os.path.join(os.path.dirname(workspace), "outside.txt")
    assert not os.path.exists(escaped)


async def test_api_refuses_to_delete_the_workspace_root(workspace):
    client = await make_client()
    response = await client.post(
        "/text-editor-plugin/api/delete",
        form={"workspace": workspace, "path": ""},
    )
    assert response.status_code == 400
    assert (await response.get_json())["error"] == "cannot_delete_root"
    assert os.path.isdir(workspace)


async def test_api_rejects_a_workspace_that_is_not_a_folder(workspace):
    client = await make_client()
    missing = os.path.join(workspace, "gone")
    response = await client.get(
        "/text-editor-plugin/api/list", query_string={"workspace": missing}
    )
    assert response.status_code == 400
    assert (await response.get_json())["error"] == "bad_request"


async def test_api_rejects_a_missing_workspace(workspace):
    client = await make_client()
    response = await client.get("/text-editor-plugin/api/list")
    assert response.status_code == 400
    assert (await response.get_json())["error"] == "bad_request"


async def test_lsp_info_lists_languages_and_the_workspace(workspace):
    client = await make_client()
    response = await client.get(
        "/text-editor-plugin/api/lsp_info",
        query_string={"workspace": workspace},
    )
    assert response.status_code == 200
    body = await response.get_json()
    assert body["workspacePath"] == workspace
    assert "python" in body["languages"]
    assert body["languages"] == sorted(body["languages"])


async def test_lsp_info_rejects_a_missing_folder(workspace):
    client = await make_client()
    missing = os.path.join(workspace, "gone")
    response = await client.get(
        "/text-editor-plugin/api/lsp_info", query_string={"workspace": missing}
    )
    assert response.status_code == 400
    assert (await response.get_json())["error"] == "bad_request"


async def test_watch_socket_reports_file_changes(workspace):
    client = await make_client()
    _write(workspace, "watched.txt", "one")

    async with client.websocket(
        "/text-editor-plugin/ws", query_string={"workspace": workspace}
    ) as ws:
        await ws.send_json({"type": "watch", "path": "watched.txt"})

        # The poll loop notices the file on its first pass.
        first = json.loads(await asyncio.wait_for(ws.receive(), 15))
        assert first == {
            "type": "file-changed",
            "path": "watched.txt",
            "content": "one",
        }

        _write(workspace, "watched.txt", "two")
        second = json.loads(await asyncio.wait_for(ws.receive(), 15))
        assert second["type"] == "file-changed"
        assert second["content"] == "two"


async def test_watch_socket_ignores_paths_outside_the_workspace(workspace):
    client = await make_client()
    # A file next to the workspace, reachable from it only via ``..``.
    outside_name = "outside-" + uuid.uuid4().hex[:8]
    outside_dir = os.path.dirname(workspace)
    outside_file = os.path.join(outside_dir, outside_name)
    _write(outside_dir, outside_name, "secret")

    try:
        async with client.websocket(
            "/text-editor-plugin/ws", query_string={"workspace": workspace}
        ) as ws:
            await ws.send_json({"type": "watch", "path": "../" + outside_name})
            _write(workspace, "inside.txt", "inside")
            await ws.send_json({"type": "watch", "path": "inside.txt"})

            # Only the in-workspace subscription produces a notification.
            msg = json.loads(await asyncio.wait_for(ws.receive(), 15))
            assert msg["path"] == "inside.txt"
        # The file outside the workspace was never subscribed to, so the
        # watch machinery left it alone.
        assert _read(outside_file) == "secret"
    finally:
        os.unlink(outside_file)


# -- the /edit redirect ---------------------------------------------------


@pytest.fixture
def module_file():
    """A real file resource, so ``/edit`` can be pointed at it.

    The file lives in an ``__filedata__`` folder that carries a
    ``package.json`` marker, so workspace detection must land on
    ``__filedata__`` rather than the file's own subfolder.
    """
    from kaithem.api.modules import filename_for_file_resource

    module = "test_text_editor_" + uuid.uuid4().hex[:8]
    fn = filename_for_file_resource(module, "files/hello.txt")
    data_dir = os.path.realpath(os.path.dirname(os.path.dirname(fn)))
    _write(os.path.dirname(fn), "hello.txt", "hello")
    _write(data_dir, "package.json", "{}")

    try:
        yield module, "files/hello.txt", data_dir
    finally:
        module_dir = os.path.dirname(os.path.dirname(data_dir))
        shutil.rmtree(module_dir, ignore_errors=True)


async def test_edit_redirects_to_the_detected_workspace(module_file):
    from urllib.parse import parse_qs, urlparse

    module, resource, data_dir = module_file
    client = await make_client()

    response = await client.get(
        "/text-editor-plugin/edit",
        query_string={"module": module, "resource": resource},
    )
    assert response.status_code == 302
    parsed = urlparse(response.headers["Location"])
    query = parse_qs(parsed.query)
    assert query["workspace"] == [data_dir]
    assert query["file"] == ["files/hello.txt"]


async def test_edit_redirects_guests_to_the_login_page(module_file):
    from kaithem.src import quart_app

    module, resource, _ = module_file
    client = quart_app.app.test_client(use_cookies=True)

    response = await client.get(
        "/text-editor-plugin/edit",
        query_string={"module": module, "resource": resource},
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
