# SPDX-License-Identifier: GPL-3.0-or-later
"""A simple text editor plugin.

A micro version of vs code, for editing any plain text file resource.
Accessible from any file using the file actions system like Excalidraw.

REST APIs for reading/writing/renaming/deleting/creating files and
folders, a websocket for live file updates, and a dedicated websocket
that bridges the browser editor to a language server.
"""

import asyncio
import functools
import os
import shutil
import threading
from typing import Any
from urllib.parse import quote_plus

import quart
import quart.utils

from kaithem.api import lifespan
from kaithem.api.modules import (
    filename_for_file_resource,
    scan_file_resources,
)
from kaithem.api.web import (
    add_file_resource_link,
    quart_app,
    require,
)
from kaithem.src import pages

from . import lsp

logger = __import__("structlog").get_logger(__name__)

MAX_FILE_BYTES = 5 * 1024 * 1024


def _admin_api(f):
    """Require the ``system_admin`` permission for an HTTP API handler.

    Unlike the default ``require`` behavior, an authentication failure is
    returned as JSON instead of a login redirect, so the frontend can show
    its own full-screen "not logged in" splash rather than silently
    following a redirect and receiving a login page.
    """

    @functools.wraps(f)
    async def wrapper(*args, **kwargs):
        try:
            require("system_admin")
        except pages.KaithemUserPermissionError:
            if pages.getAcessingUser() == "__guest__":
                return quart.jsonify({"error": "not_logged_in"}), 401
            return quart.jsonify({"error": "forbidden"}), 403
        return await f(*args, **kwargs)

    return wrapper


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


# Live file updates ---------------------------------------------------------

# A single process-wide manager polls the subscribed files for changes.  We
# deliberately use polling only: inotify needs a per-user instance
# (fs.inotify.max_user_instances), which is a small shared budget that other
# applications rely on, and the extra code path buys nothing for a simple
# text editor.
_POLL_INTERVAL_S = 1.0


class _FileWatchManager:
    """Process-wide live file change notifications.

    A single daemon thread polls the files that websocket clients have
    subscribed to.  Subscriptions are added/removed from the event loop
    thread; notifications are delivered by enqueuing onto each subscriber's
    asyncio queue via ``call_soon_threadsafe``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # abs_path -> {queue: (module_root, loop)}
        self._subs = {}
        # abs_path -> last content sent, to suppress duplicate notifications
        self._last: dict[str, str] = {}
        self._started = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _ensure_started(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="text-editor-file-watch"
        )
        self._thread.start()

    def subscribe(self, abs_path: str, queue, module_root, loop) -> None:
        with self._lock:
            self._subs.setdefault(abs_path, {})[queue] = (module_root, loop)
        self._ensure_started()

    def unsubscribe(self, abs_path, queue) -> None:
        with self._lock:
            subs = self._subs.get(abs_path)
            if not subs:
                return
            subs.pop(queue, None)
            if not subs:
                self._subs.pop(abs_path, None)
                self._last.pop(abs_path, None)

    def unsubscribe_all(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Drop every subscription belonging to one connection's queue."""
        with self._lock:
            for abs_path in list(self._subs):
                subs = self._subs[abs_path]
                subs.pop(queue, None)
                if not subs:
                    self._subs.pop(abs_path, None)
                    self._last.pop(abs_path, None)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    # -- background thread --

    def _poll_loop(self) -> None:
        last: dict[str, tuple] = {}
        while not self._stop.wait(_POLL_INTERVAL_S):
            with self._lock:
                paths = list(self._subs)
            for abs_path in paths:
                try:
                    st = os.stat(abs_path)
                except OSError:
                    last.pop(abs_path, None)
                    continue
                sig = (st.st_mtime_ns, st.st_size)
                if last.get(abs_path) == sig:
                    continue
                last[abs_path] = sig
                self._dispatch(abs_path)

    def _dispatch(self, abs_path: str) -> None:
        with self._lock:
            if abs_path not in self._subs:
                return
        try:
            if os.path.getsize(abs_path) >= MAX_FILE_BYTES:
                return
            with open(abs_path, "rb") as f:
                content = f.read().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            # File removed, replaced by a directory, or no longer text.
            return
        with self._lock:
            if self._last.get(abs_path) == content:
                return
            self._last[abs_path] = content
            targets = list(self._subs.get(abs_path, {}).items())
        for queue, (module_root, loop) in targets:
            resource = os.path.relpath(abs_path, module_root).replace(
                os.sep, "/"
            )
            try:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "type": "file-changed",
                        "resource": resource,
                        "content": content,
                    },
                )
            except Exception:
                pass


_watch_manager: _FileWatchManager | None = None
_watch_manager_lock = threading.Lock()


def _get_watch_manager() -> _FileWatchManager:
    global _watch_manager
    with _watch_manager_lock:
        if _watch_manager is None:
            _watch_manager = _FileWatchManager()
        return _watch_manager


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
@_admin_api
async def api_list():
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


def _list_dir(module: str, root: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
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
@_admin_api
async def api_read():
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
@_admin_api
async def api_write():
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
@_admin_api
async def api_rename():
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
@_admin_api
async def api_delete():
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
@_admin_api
async def api_new_file():
    kw = dict(await quart.request.form)
    module = kw["module"]
    resource = kw["resource"]

    def f():
        fn = _safe_path(module, resource)
        if os.path.exists(fn):
            return quart.jsonify({"error": "exists"}), 400
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        open(fn, "w").close()
        scan_file_resources(module)
        return quart.jsonify({"status": "ok"})

    return await quart.utils.run_sync(f)()


@quart_app.route("/text-editor-plugin/api/new_folder", methods=["POST"])
@_admin_api
async def api_new_folder():
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


@quart_app.route("/text-editor-plugin/api/lsp_info", methods=["GET"])
@_admin_api
async def api_lsp_info():
    """Describe the language servers available for a module.

    Returns the set of languages the backend can serve, plus the workspace
    layout the client needs to build file URIs.  This is per-module, not
    per-file: the client opens one socket per language on demand.
    """
    module = quart.request.args["module"]

    def f():
        module_root = filename_for_file_resource(module, "")
        workspace = lsp.detect_workspace(module_root)
        # The container always mounts the workspace at /workspace, so the
        # client must build file:///workspace/<rel-to-workspace> URIs.  That
        # only works if the module's file data lives inside the workspace.
        try:
            rel = os.path.relpath(os.path.abspath(module_root), workspace)
        except ValueError:
            rel = ".."
        if rel.startswith(".."):
            return quart.jsonify(
                {"languages": [], "workspaceUri": None, "moduleBaseRel": None}
            )
        if rel == ".":
            rel = ""
        return quart.jsonify(
            {
                "languages": sorted(lsp.LANGUAGE_IMAGES),
                "workspaceUri": "file:///workspace",
                "moduleBaseRel": rel.replace(os.sep, "/"),
            }
        )

    return await quart.utils.run_sync(f)()


@quart_app.websocket("/text-editor-plugin/ws/<module>/<path:resource>")
async def text_editor_ws(module: str, resource: str):
    """Live file update notifications for the text editor.

    Only carries the ``watch``/``unwatch`` control messages and the
    ``file-changed`` notifications; LSP traffic has its own socket.
    """
    require("system_admin")

    ws = quart.websocket

    loop = asyncio.get_running_loop()
    send_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _forward() -> None:
        while True:
            msg = await send_queue.get()
            await ws.send_json(msg)

    forward_task = asyncio.create_task(_forward())

    root = filename_for_file_resource(module, "")
    manager = _get_watch_manager()

    def _resource_abs_path(res: str) -> str | None:
        """Resolve a subscribed resource to an absolute path inside root."""
        real_root = os.path.realpath(root)
        full = os.path.realpath(os.path.join(root, res))
        if full != real_root and not full.startswith(real_root + os.sep):
            return None
        return full

    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type") if isinstance(msg, dict) else None
            if mtype == "watch":
                abs_path = _resource_abs_path(msg.get("resource", ""))
                if abs_path is not None:
                    manager.subscribe(abs_path, send_queue, root, loop)
            elif mtype == "unwatch":
                abs_path = _resource_abs_path(msg.get("resource", ""))
                if abs_path is not None:
                    manager.unsubscribe(abs_path, send_queue)
    except Exception:
        pass
    finally:
        forward_task.cancel()
        manager.unsubscribe_all(send_queue)


@quart_app.websocket("/text-editor-plugin/lsp-ws/<module>/<language>")
async def text_editor_lsp_ws(module: str, language: str):
    """Dedicated, transparent JSON-RPC bridge to a language server.

    One socket bridges one language for one module.  Each connection gets
    its own language server container.  Only raw JSON-RPC bodies are
    exchanged: the browser client (ace-linters) sends and receives exactly
    what the language server does, so this backend must never send a
    message of its own (not even a status message) or it would corrupt the
    protocol stream.

    If the language is unknown or no workspace could be resolved the socket
    is closed immediately with code 4004, which the client treats as
    "unavailable".
    """
    require("system_admin")

    ws = quart.websocket
    loop = asyncio.get_running_loop()

    if language not in lsp.LANGUAGE_IMAGES:
        await ws.close(4004, "no_lsp")
        return

    # The workspace is always mounted at /workspace in the container, so
    # the client mirrors this layout with file:///workspace/... URIs.  That
    # only works if the module's file data lives inside the workspace.
    module_root = filename_for_file_resource(module, "")
    workspace = lsp.detect_workspace(module_root)
    try:
        rel = os.path.relpath(os.path.abspath(module_root), workspace)
    except ValueError:
        rel = ".."
    if rel.startswith(".."):
        await ws.close(4004, "no_lsp")
        return

    try:
        server = lsp.start_language_server(language, workspace)
    except Exception:
        logger.exception("Failed to start language server")
        await ws.close(4005, "lsp_start_failed")
        return

    out_queue: asyncio.Queue[str] = asyncio.Queue()

    def _on_server_message(text: str) -> None:
        # Called from the language server's reader thread; hop onto the
        # event loop that owns the websocket.
        try:
            loop.call_soon_threadsafe(out_queue.put_nowait, text)
        except Exception:
            pass

    server.set_sink(_on_server_message)

    async def _pump_to_ws() -> None:
        while True:
            text = await out_queue.get()
            await ws.send(text)

    pump_task = asyncio.create_task(_pump_to_ws())
    try:
        while True:
            data = await ws.receive()
            if data is None:
                break
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            server.send_raw(data)
    except Exception:
        pass
    finally:
        pump_task.cancel()
        lsp.stop_language_server(server)


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


def _stop_watch_manager() -> None:
    if _watch_manager is not None:
        _watch_manager.stop()


lifespan.at_shutdown(_stop_watch_manager)
