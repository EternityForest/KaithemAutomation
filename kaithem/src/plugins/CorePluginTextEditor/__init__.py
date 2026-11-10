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
import threading
from typing import Any
from urllib.parse import quote_plus

import inotify.adapters
import inotify.calls
import inotify.constants as C
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


# Live file updates ---------------------------------------------------------

# A single inotify instance is shared by every websocket connection.  The
# per-user limit on inotify instances (fs.inotify.max_user_instances) is
# small, so creating one per connection quickly exhausts it and breaks
# unrelated applications.  If the process cannot create an inotify instance
# at all (the user's instance budget is already spent by other apps), the
# manager transparently falls back to polling the subscribed files so live
# updates keep working.
_POLL_INTERVAL_S = 1.0
_RELEVANT_INOTIFY_EVENTS = {
    "IN_CLOSE_WRITE",
    "IN_MOVED_TO",
    "IN_CREATE",
    "IN_DELETE",
}


class _FileWatchManager:
    """Process-wide live file change notifications.

    A single daemon thread owns one inotify instance and reports changes to
    the files that websocket clients have subscribed to.  Subscriptions are
    added/removed from the event loop thread; notifications are delivered by
    enqueuing onto each subscriber's asyncio queue via ``call_soon_threadsafe``.
    Keeping one shared instance means the process never needs more than one
    inotify instance no matter how many connections or tabs are open.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # abs_path -> {queue: (module_root, loop)}
        self._subs = {}
        # abs_path -> last content sent, to suppress duplicate notifications
        self._last: dict[str, str] = {}
        # directory -> set of abs_paths that require it to be watched
        self._dirs: dict[str, set[str]] = {}
        # inotify watch descriptor -> directory
        self._wd_to_dir: dict[int, str] = {}
        self._inotify: inotify.adapters.Inotify | None = None
        self._started = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _ensure_started(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="text-editor-file-watch"
        )
        self._thread.start()

    def subscribe(self, abs_path: str, queue, module_root, loop) -> None:
        with self._lock:
            self._subs.setdefault(abs_path, {})[queue] = (module_root, loop)
            self._add_watch(abs_path)
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
                self._remove_watch(abs_path)

    def unsubscribe_all(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Drop every subscription belonging to one connection's queue."""
        with self._lock:
            for abs_path in list(self._subs):
                subs = self._subs[abs_path]
                subs.pop(queue, None)
                if not subs:
                    self._subs.pop(abs_path, None)
                    self._last.pop(abs_path, None)
                    self._remove_watch(abs_path)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    # -- watch bookkeeping (must be called with self._lock held) --

    def _add_watch(self, abs_path: str) -> None:
        d = os.path.dirname(abs_path)
        paths = self._dirs.setdefault(d, set())
        first = not paths
        paths.add(abs_path)
        if first and self._inotify is not None:
            self._watch_dir(d)

    def _remove_watch(self, abs_path: str) -> None:
        d = os.path.dirname(abs_path)
        paths = self._dirs.get(d)
        if paths is None:
            return
        paths.discard(abs_path)
        if paths:
            return
        self._dirs.pop(d, None)
        if self._inotify is None:
            return
        try:
            self._inotify.remove_watch(d)
        except Exception:
            pass
        self._wd_to_dir = {
            wd: dd for wd, dd in self._wd_to_dir.items() if dd != d
        }

    def _watch_dir(self, d: str) -> None:
        mask = C.IN_CLOSE_WRITE | C.IN_MOVED_TO | C.IN_CREATE | C.IN_DELETE
        try:
            wd = self._inotify.add_watch(d, mask)
            self._wd_to_dir[wd] = d
        except Exception:
            logger.exception("Could not watch %s", d)

    # -- background thread --

    def _run(self) -> None:
        if not self._start_inotify():
            self._poll_loop()
            return
        try:
            for event in self._inotify.event_gen(yield_nones=True):
                if self._stop.is_set():
                    return
                if event is None:
                    # Periodic wakeup so the stop flag is checked promptly.
                    continue
                _header, type_names, path, filename = event
                if "IN_ISDIR" in type_names:
                    continue
                if not _RELEVANT_INOTIFY_EVENTS.intersection(type_names):
                    continue
                self._dispatch(os.path.join(path, filename))
        except Exception:
            logger.exception("File watcher stopped")

    def _start_inotify(self) -> bool:
        # Probe first: constructing adapters.Inotify when the per-user
        # instance budget is exhausted leaves a half-built object whose
        # __del__ prints a confusing traceback.  The probe keeps logs clean.
        try:
            probe_fd = inotify.calls.inotify_init()
        except Exception:
            logger.exception(
                "inotify failed (fs.inotify.max_user_instances "
                "exhausted?); falling back to polling for live file updates"
            )
            return False
        os.close(probe_fd)

        try:
            inst = inotify.adapters.Inotify(block_duration_s=0.5)
        except Exception:
            logger.warning(
                "inotify unavailable; falling back to polling for live "
                "file updates"
            )
            return False
        with self._lock:
            self._inotify = inst
            for d in list(self._dirs):
                self._watch_dir(d)
        return True

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
        open(fn, "w").close()
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

    # Optional LSP session for this file.
    peer = None
    try:
        fn = _resolve(module, resource)
        language = lsp._language_for_file(fn)
        workspace = lsp.detect_workspace(fn)
    except Exception:
        language = None
        workspace = None

    if language and workspace:
        peer = lsp.get_lsp_peer(language, workspace)

    if peer is not None:
        peer._ws_send_loop = loop
        peer._ws_send_queues.append(send_queue)
        peer._on_message = lambda msg: _ws_send(peer, msg)
        await ws.send_json({"type": "lsp", "status": "connected"})
    else:
        # No LSP support for this file or no workspace detected, but the
        # socket stays open so live file updates keep working.
        await ws.send_json({"type": "lsp", "status": "unavailable"})

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
            elif peer is not None:
                peer.send_client_message(msg)
    except Exception:
        pass
    finally:
        forward_task.cancel()
        manager.unsubscribe_all(send_queue)
        if peer is not None:
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
        wrapped = {"type": "lsp-server", "message": remapped}
        for q in list(peer._ws_send_queues):
            try:
                loop.call_soon_threadsafe(q.put_nowait, wrapped)
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


def _stop_watch_manager() -> None:
    if _watch_manager is not None:
        _watch_manager.stop()


lifespan.at_shutdown(_stop_watch_manager)
