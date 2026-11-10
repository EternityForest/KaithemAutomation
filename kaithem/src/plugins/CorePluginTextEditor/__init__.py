# SPDX-License-Identifier: GPL-3.0-or-later
"""A simple text editor plugin.

A micro version of vs code, for editing any plain text file resource.
Accessible from any file using the file actions system like Excalidraw.

REST APIs for reading/writing/renaming/deleting/creating files and
folders, and a websocket for the LSP proxy.
"""

import asyncio
import os
import shutil
from urllib.parse import quote_plus

import quart
import quart.utils

from kaithem.api.modules import (
    filename_for_file_resource,
    scan_file_resources,
)
from kaithem.api.web import (
    add_file_resource_link,
    quart_app,
    require,
)

from . import lsp

logger = __import__("structlog").get_logger(__name__)

MAX_FILE_BYTES = 5 * 1024 * 1024


def _resolve(module: str, resource: str) -> str:
    """Resolve a module/resource path and return the absolute file path."""
    fn = filename_for_file_resource(module, resource)
    if not os.path.exists(fn):
        raise FileNotFoundError(f"File {module}/{resource} does not exist")
    return fn


def _safe_path(module: str, resource: str) -> str:
    """Resolve a path, but only allow paths inside the module's file data."""
    root = filename_for_file_resource(module, "")
    fn = filename_for_file_resource(module, resource)
    if not os.path.realpath(fn).startswith(os.path.realpath(root)):
        raise ValueError("Path outside module file data")
    return fn


@quart_app.route("/text-editor-plugin/edit", methods=["GET"])
async def text_editor_edit():
    require("system_admin")
    module = quart.request.args["module"]
    resource = quart.request.args["resource"]

    url = (
        "/static/vite/kaithem/src/plugins/CorePluginTextEditor/html/index.html"
        + "?module="
        + quote_plus(module, safe="")
        + "&resource="
        + quote_plus(resource, safe="")
    )
    return quart.redirect(url)


@quart_app.route("/text-editor-plugin/api/list", methods=["GET"])
async def api_list():
    require("system_admin")
    module = quart.request.args["module"]
    resource = quart.request.args.get("resource", "")

    def f():
        root = _safe_path(module, resource)
        if not os.path.isdir(root):
            # Modules that have never had a file resource created have no
            # __filedata__ dir on disk yet (directory resources are virtual),
            # so an empty tree is the right answer.
            return quart.jsonify([])
        out = _list_dir(module, root)
        return quart.jsonify(out)

    return await quart.utils.run_sync(f)()


def _list_dir(module: str, root: str) -> list[dict]:
    out = []
    for name in sorted(os.listdir(root)):
        if name.startswith("."):
            continue
        p = os.path.join(root, name)
        if os.path.isdir(p):
            out.append(
                {
                    "name": name,
                    "type": "dir",
                    "children": _list_dir(module, p),
                }
            )
        else:
            out.append(
                {
                    "name": name,
                    "type": "file",
                    "size": os.path.getsize(p),
                }
            )
    return out


@quart_app.route("/text-editor-plugin/api/read", methods=["GET"])
async def api_read():
    require("system_admin")
    module = quart.request.args["module"]
    resource = quart.request.args["resource"]

    def f():
        fn = _resolve(module, resource)
        if not os.path.isfile(fn):
            return quart.jsonify({"error": "not_a_file"}), 400
        if os.path.getsize(fn) >= MAX_FILE_BYTES:
            return quart.jsonify({"error": "too_large"}), 400
        with open(fn, "rb") as f:
            data = f.read()
        try:
            return quart.jsonify({"content": data.decode("utf-8")})
        except UnicodeDecodeError:
            return quart.jsonify({"error": "binary"}), 400

    return await quart.utils.run_sync(f)()


@quart_app.route("/text-editor-plugin/api/write", methods=["POST"])
async def api_write():
    require("system_admin")
    kw = dict(await quart.request.form)
    module = kw["module"]
    resource = kw["resource"]
    content = kw["content"]
    if len(content.encode("utf-8")) >= MAX_FILE_BYTES:
        return quart.jsonify({"error": "too_large"}), 400

    def f():
        fn = _safe_path(module, resource)
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "w", encoding="utf-8") as f:
            f.write(content)
        scan_file_resources(module)
        return quart.jsonify({"status": "ok"})

    return await quart.utils.run_sync(f)()


@quart_app.route("/text-editor-plugin/api/rename", methods=["POST"])
async def api_rename():
    require("system_admin")
    kw = dict(await quart.request.form)
    module = kw["module"]
    resource = kw["resource"]
    new_name = kw["new_name"]

    if "/" in new_name or new_name.startswith("."):
        return quart.jsonify({"error": "invalid_name"}), 400

    def f():
        fn = _safe_path(module, resource)
        parent = os.path.dirname(fn)
        new_fn = os.path.join(parent, new_name)
        if os.path.exists(new_fn):
            return quart.jsonify({"error": "exists"}), 400
        os.rename(fn, new_fn)
        scan_file_resources(module)
        return quart.jsonify({"status": "ok"})

    return await quart.utils.run_sync(f)()


@quart_app.route("/text-editor-plugin/api/delete", methods=["POST"])
async def api_delete():
    require("system_admin")
    kw = dict(await quart.request.form)
    module = kw["module"]
    resource = kw["resource"]

    def f():
        fn = _safe_path(module, resource)
        root = filename_for_file_resource(module, "")
        if os.path.realpath(fn) == os.path.realpath(root):
            return quart.jsonify({"error": "cannot_delete_root"}), 400
        if os.path.isdir(fn):
            shutil.rmtree(fn)
        else:
            os.unlink(fn)
        scan_file_resources(module)
        return quart.jsonify({"status": "ok"})

    return await quart.utils.run_sync(f)()


@quart_app.route("/text-editor-plugin/api/new_file", methods=["POST"])
async def api_new_file():
    require("system_admin")
    kw = dict(await quart.request.form)
    module = kw["module"]
    resource = kw["resource"]

    def f():
        fn = _safe_path(module, resource)
        if os.path.exists(fn):
            return quart.jsonify({"error": "exists"}), 400
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "w") as f:
            pass
        scan_file_resources(module)
        return quart.jsonify({"status": "ok"})

    return await quart.utils.run_sync(f)()


@quart_app.route("/text-editor-plugin/api/new_folder", methods=["POST"])
async def api_new_folder():
    require("system_admin")
    kw = dict(await quart.request.form)
    module = kw["module"]
    resource = kw["resource"]

    def f():
        fn = _safe_path(module, resource)
        if os.path.exists(fn):
            return quart.jsonify({"error": "exists"}), 400
        os.makedirs(fn)
        scan_file_resources(module)
        return quart.jsonify({"status": "ok"})

    return await quart.utils.run_sync(f)()


@quart_app.route("/text-editor-plugin/api/detect_workspace", methods=["GET"])
async def api_detect_workspace():
    require("system_admin")
    module = quart.request.args["module"]
    resource = quart.request.args["resource"]

    def f():
        fn = _resolve(module, resource)
        ws = lsp.detect_workspace(fn)
        if ws is None:
            return quart.jsonify({"workspace": None})
        return quart.jsonify({"workspace": ws})

    return await quart.utils.run_sync(f)()


@quart_app.websocket("/text-editor-plugin/ws/<module>/<path:resource>")
async def text_editor_ws(module: str, resource: str):
    require("system_admin")

    ws = quart.websocket

    try:
        fn = _resolve(module, resource)
        language = lsp._language_for_file(fn)
        workspace = lsp.detect_workspace(fn)
    except Exception:
        language = None
        workspace = None

    if language is None or workspace is None:
        # No LSP support for this file or no workspace detected.
        await ws.send_json({"type": "lsp", "status": "unavailable"})
        await ws.close(1000)
        return

    peer = lsp.get_lsp_peer(language, workspace)
    if peer is None:
        await ws.send_json({"type": "lsp", "status": "unavailable"})
        await ws.close(1000)
        return

    loop = asyncio.get_running_loop()
    send_queue: asyncio.Queue = asyncio.Queue()

    peer._ws_send_loop = loop
    peer._ws_send_queues.append(send_queue)
    peer._on_message = lambda msg: _ws_send(peer, msg)

    async def _forward() -> None:
        while True:
            msg = await send_queue.get()
            await ws.send_json({"type": "lsp-server", "message": msg})

    forward_task = asyncio.create_task(_forward())

    try:
        await ws.send_json({"type": "lsp", "status": "connected"})

        while True:
            msg = await ws.receive_json()
            peer.send_client_message(msg)
    except Exception:
        pass
    finally:
        forward_task.cancel()
        try:
            peer._ws_send_queues.remove(send_queue)
        except ValueError:
            pass
        peer.release_session()


def _ws_send(peer: lsp.LSPPeer, msg: dict) -> None:
    """Forward a server message to every connected websocket.

    Called from the LSP reader thread, so we cannot await directly; we hop
    onto the event loop that owns the websocket queues.
    """
    try:
        loop = peer._ws_send_loop
        if loop is None:
            return
        remapped = lsp.remap_message(peer, msg)
        for q in list(peer._ws_send_queues):
            try:
                loop.call_soon_threadsafe(q.put_nowait, remapped)
            except Exception:
                pass
    except Exception:
        logger.exception("Error sending LSP message to websocket")


def filter_text_editor_resources(
    module: str, resource: str
) -> tuple[str, str] | None:
    """Add a link to all plain text files."""
    fn = filename_for_file_resource(module, resource)
    if not os.path.isfile(fn):
        return None
    try:
        with open(fn, "rb") as f:
            head = f.read(1024)
        head.decode("utf-8")
    except Exception:
        return None
    return (
        '<span class="mdi mdi-pencil"></span>Edit',
        f"/text-editor-plugin/edit?module={quote_plus(module, safe='')}"
        + f"&resource={quote_plus(resource, safe='')}",
    )


add_file_resource_link(filter_text_editor_resources)
