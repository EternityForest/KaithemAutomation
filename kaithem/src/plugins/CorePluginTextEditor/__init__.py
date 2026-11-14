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
from collections.abc import Callable
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
from kaithem.src import modules_state, pages

from . import lsp

logger = __import__("structlog").get_logger(__name__)

_VITE_PAGE = (
    "/static/vite/kaithem/src/plugins/CorePluginTextEditor/html/index.html"
)

MAX_FILE_BYTES = 5 * 1024 * 1024

# Directory names that are never worth listing in the tree: build outputs
# and dependency caches can be huge and only slow the editor down.  Names
# starting with a dot are skipped too (see _list_dir).
PRUNED_DIRS = {
    "node_modules",
    "bower_components",
    "dist",
    "build",
    "target",
    "venv",
    "__pycache__",
    "__pypackages__",
}


def _admin_api(f: Callable[..., Any]) -> Callable[..., Any]:
    """Require the ``system_admin`` permission for an HTTP API handler.

    Unlike the default ``require`` behavior, an authentication failure is
    returned as JSON instead of a login redirect, so the frontend can show
    its own full-screen "not logged in" splash rather than silently
    following a redirect and receiving a login page.
    """

    @functools.wraps(f)
    # pyrefly: ignore [implicit-any-parameter]
    async def wrapper(*arg, **kwargs):
        try:
            require("system_admin")
        except pages.KaithemUserPermissionError:
            if pages.getAcessingUser() == "__guest__":
                return quart.jsonify({"error": "not_logged_in"}), 401
            return quart.jsonify({"error": "forbidden"}), 403
        return await f(*arg, **kwargs)  # noqa: F821

    return wrapper


def _workspace_root(workspace: str) -> str:
    """Validate a workspace path and return its real absolute path."""
    if not workspace:
        raise ValueError("Missing workspace")
    root = os.path.realpath(workspace)
    if not os.path.isdir(root):
        raise ValueError("Workspace is not a directory")
    return root


def _workspace_path(workspace: str, path: str) -> str:
    """Resolve a workspace-relative path, rejecting escapes.

    Filenames are always relative to the workspace root, so ``..`` cannot
    walk out of the folder the editor was opened on.  Raises ``ValueError``
    for anything that resolves outside the workspace.
    """
    root = _workspace_root(workspace)
    fn = os.path.realpath(os.path.join(root, path))
    if fn != root and not fn.startswith(root + os.sep):
        raise ValueError("Path outside workspace")
    return fn


def _rel_path(path: str) -> str:
    """Reject an empty workspace-relative path.

    An empty path would silently mean "the workspace root" to
    ``_workspace_path``, which is never what a create/rename/delete call
    wants, so treat it as a client error instead.
    """
    if not path:
        raise ValueError("Missing path")
    return path


async def _run(job: Callable[[], Any]) -> Any:
    """Run a blocking filesystem job off the event loop.

    Path validation failures arrive as ``ValueError``; they are answered
    as 400 so a rejected path is a client error, not a server crash.
    """

    def wrapped() -> Any:
        try:
            return job()
        except ValueError as e:
            return (
                quart.jsonify({"error": "bad_request", "message": str(e)}),
                400,
            )

    return await quart.utils.run_sync(wrapped)()


def _rescan_module(abs_path: str) -> None:
    """Refresh Kaithem's file resource index for the owning module.

    Files the editor writes may live inside a module's file data folder,
    where Kaithem caches an index of file resources.  Rescan the module
    that owns ``abs_path`` (if any) so that index stays current; files
    outside every module are simply ignored.
    """
    real = os.path.realpath(abs_path)
    module = None
    with modules_state.modulesLock:
        for name in modules_state.ActiveModules:
            try:
                root = os.path.realpath(filename_for_file_resource(name, ""))
            except Exception:
                continue
            if real == root or real.startswith(root + os.sep):
                module = name
                break
    if module is None:
        return
    try:
        scan_file_resources(module)
    except Exception:
        logger.exception("Failed to rescan module after edit")


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
        # abs_path -> {queue: (workspace_root, loop)}
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

    def subscribe(
        self,
        abs_path: str,
        queue: asyncio.queues.Queue[dict[str, Any]],
        workspace_root: str,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        with self._lock:
            self._subs.setdefault(abs_path, {})[queue] = (
                workspace_root,
                loop,
            )
        self._ensure_started()

    def unsubscribe(
        self, abs_path: str, queue: asyncio.queues.Queue[dict[str, Any]]
    ) -> None:
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
        last: dict[str, tuple[int, int]] = {}
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
        for queue, (workspace_root, loop) in targets:
            rel = os.path.relpath(abs_path, workspace_root).replace(os.sep, "/")
            try:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "type": "file-changed",
                        "path": rel,
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
    """Redirect to the editor, rooted at the opened file's workspace.

    The workspace is the innermost folder around the clicked file that
    looks like a project (see ``lsp.detect_workspace``); the file tree,
    chat, snapshots, and LSP are all rooted there.
    """
    require("system_admin")
    module = quart.request.args["module"]
    resource = quart.request.args["resource"]

    fn = os.path.abspath(filename_for_file_resource(module, resource))
    workspace = lsp.detect_workspace(fn)
    rel = os.path.relpath(fn, workspace).replace(os.sep, "/")

    url = (
        _VITE_PAGE
        + "?workspace="
        + quote_plus(workspace, safe="")
        + "&file="
        + quote_plus(rel, safe="")
    )
    return quart.redirect(url)


@quart_app.route("/text-editor-plugin/api/list", methods=["GET"])
@_admin_api
async def api_list():
    workspace = quart.request.args.get("workspace", "")
    path = quart.request.args.get("path", "")

    def f():
        root = _workspace_path(workspace, path)
        if not os.path.isdir(root):
            # A missing folder just means "nothing here yet" for the tree.
            return quart.jsonify([])
        return quart.jsonify(_list_dir(root))

    return await _run(f)


def _list_dir(root: str) -> list[dict[str, Any]]:
    """List one directory level, recursively, pruning noise.

    Hidden entries (leading dot) and the build/dependency folders in
    ``PRUNED_DIRS`` are skipped.  Symlinked directories are shown as
    files so a link back up the tree cannot loop forever.
    """
    out: list[dict[str, Any]] = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for name in names:
        if name.startswith(".") or name in PRUNED_DIRS:
            continue
        p = os.path.join(root, name)
        if os.path.isdir(p) and not os.path.islink(p):
            out.append(
                {
                    "name": name,
                    "type": "dir",
                    "children": _list_dir(p),
                }
            )
        else:
            try:
                size = os.path.getsize(p)
            except OSError:
                size = 0
            out.append({"name": name, "type": "file", "size": size})
    return out


@quart_app.route("/text-editor-plugin/api/read", methods=["GET"])
@_admin_api
async def api_read():
    workspace = quart.request.args.get("workspace", "")
    path = quart.request.args.get("path", "")

    def f():
        fn = _workspace_path(workspace, _rel_path(path))
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

    return await _run(f)


@quart_app.route("/text-editor-plugin/api/write", methods=["POST"])
@_admin_api
async def api_write():
    kw = dict(await quart.request.form)
    workspace = kw.get("workspace", "")
    path = kw.get("path", "")
    content = kw.get("content", "")
    if len(content.encode("utf-8")) >= MAX_FILE_BYTES:
        return quart.jsonify({"error": "too_large"}), 400

    def f():
        fn = _workspace_path(workspace, _rel_path(path))
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "w", encoding="utf-8") as f:
            f.write(content)
        _rescan_module(fn)
        return quart.jsonify({"status": "ok"})

    return await _run(f)


@quart_app.route("/text-editor-plugin/api/rename", methods=["POST"])
@_admin_api
async def api_rename():
    kw = dict(await quart.request.form)
    workspace = kw.get("workspace", "")
    path = kw.get("path", "")
    new_name = kw.get("new_name", "")

    if not new_name or "/" in new_name or new_name.startswith("."):
        return quart.jsonify({"error": "invalid_name"}), 400

    def f():
        fn = _workspace_path(workspace, _rel_path(path))
        new_fn = os.path.join(os.path.dirname(fn), new_name)
        if os.path.exists(new_fn):
            return quart.jsonify({"error": "exists"}), 400
        os.rename(fn, new_fn)
        _rescan_module(new_fn)
        return quart.jsonify({"status": "ok"})

    return await _run(f)


@quart_app.route("/text-editor-plugin/api/delete", methods=["POST"])
@_admin_api
async def api_delete():
    kw = dict(await quart.request.form)
    workspace = kw.get("workspace", "")
    path = kw.get("path", "")

    def f():
        root = _workspace_root(workspace)
        fn = _workspace_path(workspace, path)
        if fn == root:
            return quart.jsonify({"error": "cannot_delete_root"}), 400
        if os.path.isdir(fn):
            shutil.rmtree(fn)
        else:
            os.unlink(fn)
        _rescan_module(os.path.dirname(fn))
        return quart.jsonify({"status": "ok"})

    return await _run(f)


@quart_app.route("/text-editor-plugin/api/new_file", methods=["POST"])
@_admin_api
async def api_new_file():
    kw = dict(await quart.request.form)
    workspace = kw.get("workspace", "")
    path = kw.get("path", "")

    def f():
        fn = _workspace_path(workspace, _rel_path(path))
        if os.path.exists(fn):
            return quart.jsonify({"error": "exists"}), 400
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        open(fn, "w").close()
        _rescan_module(fn)
        return quart.jsonify({"status": "ok"})

    return await _run(f)


@quart_app.route("/text-editor-plugin/api/new_folder", methods=["POST"])
@_admin_api
async def api_new_folder():
    kw = dict(await quart.request.form)
    workspace = kw.get("workspace", "")
    path = kw.get("path", "")

    def f():
        fn = _workspace_path(workspace, _rel_path(path))
        if os.path.exists(fn):
            return quart.jsonify({"error": "exists"}), 400
        os.makedirs(fn)
        _rescan_module(fn)
        return quart.jsonify({"status": "ok"})

    return await _run(f)


@quart_app.route("/text-editor-plugin/api/lsp_info", methods=["GET"])
@_admin_api
async def api_lsp_info():
    """Describe the language servers available for a workspace.

    The workspace folder is always mounted at ``/workspace`` in the
    container, so the client addresses files with
    ``file:///workspace/<workspace-relative path>`` URIs and only needs
    the list of languages plus the workspace path back.  This is
    per-workspace, not per-file: the client opens one socket per language
    on demand.
    """
    workspace = quart.request.args.get("workspace", "")

    def f():
        root = _workspace_root(workspace)
        return quart.jsonify(
            {
                "languages": sorted(lsp.LANGUAGE_IMAGES),
                "workspacePath": root,
            }
        )

    return await _run(f)


@quart_app.websocket("/text-editor-plugin/ws")
async def text_editor_ws():
    """Live file update notifications for the text editor.

    The workspace comes in as a query argument.  Only the
    ``watch``/``unwatch`` control messages and the ``file-changed``
    notifications travel here; LSP traffic has its own socket.
    """
    require("system_admin")

    ws = quart.websocket
    loop = asyncio.get_running_loop()

    try:
        root = _workspace_root(ws.args.get("workspace", ""))
    except ValueError:
        await ws.close(4004, "no_workspace")
        return

    send_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _forward() -> None:
        while True:
            msg = await send_queue.get()
            await ws.send_json(msg)

    forward_task = asyncio.create_task(_forward())
    manager = _get_watch_manager()

    def _path_abs(p: str) -> str | None:
        """Resolve a subscribed path to an absolute path inside root."""
        full = os.path.realpath(os.path.join(root, p))
        if full != root and not full.startswith(root + os.sep):
            return None
        return full

    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type") if isinstance(msg, dict) else None
            if mtype == "watch":
                abs_path = _path_abs(msg.get("path", ""))
                if abs_path is not None:
                    manager.subscribe(abs_path, send_queue, root, loop)
            elif mtype == "unwatch":
                abs_path = _path_abs(msg.get("path", ""))
                if abs_path is not None:
                    manager.unsubscribe(abs_path, send_queue)
    except Exception:
        pass
    finally:
        forward_task.cancel()
        manager.unsubscribe_all(send_queue)


@quart_app.websocket("/text-editor-plugin/lsp-ws")
async def text_editor_lsp_ws():
    """Dedicated, transparent JSON-RPC bridge to a language server.

    One socket bridges one language for one workspace folder; each
    connection gets its own language server container.  Only raw JSON-RPC
    bodies are exchanged: the browser client (ace-linters) sends and
    receives exactly what the language server does, so this backend must
    never send a message of its own (not even a status message) or it
    would corrupt the protocol stream.

    If the language is unknown or the workspace is unusable the socket is
    closed immediately with code 4004, which the client treats as
    "unavailable".
    """
    require("system_admin")

    ws = quart.websocket
    loop = asyncio.get_running_loop()

    language = ws.args.get("language", "")
    if language not in lsp.LANGUAGE_IMAGES:
        await ws.close(4004, "no_lsp")
        return

    try:
        root = _workspace_root(ws.args.get("workspace", ""))
    except ValueError:
        await ws.close(4004, "no_lsp")
        return

    try:
        # Starting the container may pull the image, so keep it off the
        # event loop.
        server = await asyncio.to_thread(
            lsp.start_language_server, language, root
        )
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
