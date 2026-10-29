# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation screen resource type and PPTX file management.

A ``presentation_screen`` resource owns a FileData folder named
``<resource>.content`` holding plain ``.pptx`` files.  Admin users can
upload, list, edit, and delete those files; viewing may be opened to
guests by leaving the ``view_permission`` setting empty, or restricted to
viewers holding an arbitrary permission by naming it there.

The server holds one playback state per screen (which file and which
slide).  Viewer pages keep a WebSocket open and mirror that state, so every
connected viewer shows the same slide.  Admins replace the whole state
through the REST API and the new state is broadcast through the message
bus; viewers never write state back.

Each screen also stores a default start state in its resource data, which
is used until an admin sets a live state (and again after a restart).

Beyond that, a screen may hold any number of bookmarked states, stored in
the resource as ``bookmarks: {name: {"state": ..., "meta": ...}}``.  The
``meta`` sub-dict never becomes part of the played state, so a bookmark can
carry a ``shortcut`` code without polluting the state.  Each bookmark whose
meta has a shortcut registers a Chandler ``ShortcutCodeListener`` that jumps
to (publishes) the bookmark's state; the live listeners are tracked in
``_bookmark_listeners`` and rebuilt whenever a bookmark's meta changes.
"""

import asyncio
import json
import os
import shutil
import tempfile
import threading
from typing import Any, override
from urllib.parse import quote, urlencode

import quart
import structlog
from quart import Blueprint

from kaithem.api import chandler as chandler_api
from kaithem.api import modules, resource_types, web
from kaithem.api.web import quart_app
from kaithem.api.web.dialogs import SimpleDialog
from kaithem.src import messagebus, modules_state

logger = structlog.get_logger(__name__)

CONTENT_SUFFIX = ".content"
PPTX_MIME = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

# (module, resource) -> set of connected viewer websockets
_connections: dict[tuple[str, str], set[Any]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _command_topic(module: str, resource: str) -> str:
    return f"/presentation-screen/{module}/{resource}/cmd"


def _content_dir(module: str, resource: str) -> str:
    return modules.filename_for_file_resource(module, resource + CONTENT_SUFFIX)


def _ensure_content_dir(module: str, resource: str) -> str:
    path = _content_dir(module, resource)
    os.makedirs(path, exist_ok=True)
    return path


def _resource_data(module: str, resource: str) -> dict[str, Any] | None:
    try:
        return dict(modules_state.ActiveModules[module][resource])
    except (KeyError, TypeError):
        return None


def _view_permission(data: dict[str, Any]) -> str:
    """The permission required to watch a screen, or ``""`` for guest view.

    Legacy screens stored a boolean ``view_requires_admin``; treat it as
    requiring ``system_admin`` so they keep their previous access rules.
    """
    permission = data.get("view_permission")
    if isinstance(permission, str) and permission.strip():
        return permission.strip()
    if data.get("view_requires_admin"):
        return "system_admin"
    return ""


def _check_admin() -> tuple[Any, int] | None:
    """Return a 403 response unless the caller is a system admin."""
    if web.has_permission("system_admin"):
        return None
    return quart.jsonify({"error": "forbidden"}), 403


def _check_view_access(
    module: str,
    resource: str,
) -> tuple[dict[str, Any] | None, tuple[Any, int] | None]:
    """Return the resource data, or an error response if access is denied.

    Unlike ``web.require`` this never redirects to the login page; API and
    page callers get an explicit 403/404 so failures are unambiguous.
    """
    data = _resource_data(module, resource)
    if data is None:
        return None, (quart.jsonify({"error": "not_found"}), 404)
    permission = _view_permission(data)
    if permission and not web.has_permission(permission):
        return None, (quart.jsonify({"error": "forbidden"}), 403)
    return data, None


def _ws_can_view(module: str, resource: str) -> bool:
    """Permission check usable from a websocket handler.

    ``web.require`` reads ``quart.request``, which is unavailable while
    handling a websocket; pass the ASGI scope explicitly instead.
    """
    data = _resource_data(module, resource)
    if data is None:
        return False
    permission = _view_permission(data)
    if not permission:
        return True
    scope: Any = quart.websocket.scope
    return web.has_permission(permission, asgi=scope)


def sanitize_pptx_filename(name: str) -> str:
    """Return a safe bare ``.pptx`` filename or raise ``ValueError``."""
    if not name:
        raise ValueError("Filename is empty")
    if "\x00" in name:
        raise ValueError("Filename contains a null byte")
    if name != os.path.basename(name):
        raise ValueError("Filename must not contain a path")
    if name in (".", ".."):
        raise ValueError("Invalid filename")
    if name.startswith("."):
        raise ValueError("Filename must not start with a dot")
    if not name.lower().endswith(".pptx"):
        raise ValueError("Only .pptx files are supported")
    if len(name) > 255:
        raise ValueError("Filename is too long")
    return name


def _file_path(module: str, resource: str, filename: str) -> str:
    return os.path.join(
        _content_dir(module, resource),
        sanitize_pptx_filename(filename),
    )


def _atomic_write(path: str, data: bytes) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _broadcast(module: str, resource: str, payload: dict[str, Any]) -> None:
    messagebus.post_message(_command_topic(module, resource), payload)


# ---------------------------------------------------------------------------
# Playback state
# ---------------------------------------------------------------------------

# (module, resource) -> current state.  A missing entry means "use the
# resource's default_state", so a restart falls back to the configured start.
_current_states: dict[tuple[str, str], dict[str, Any]] = {}


def _empty_state() -> dict[str, Any]:
    return {"type": "none"}


def _parse_pptx_state(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate the ``pptx`` members of a state object."""
    try:
        filename = sanitize_pptx_filename(str(raw.get("file", "")))
    except ValueError as exc:
        raise ValueError("State needs a valid .pptx file") from exc

    slide = raw.get("slide", 0)
    if isinstance(slide, bool) or not isinstance(slide, int) or slide < 0:
        raise ValueError("Slide must be a non-negative integer")
    return {"type": "pptx", "file": filename, "slide": slide}


def _normalize_state(module: str, resource: str, raw: Any) -> dict[str, Any]:
    """Turn client input into a state, or raise ``ValueError``.

    The file must exist: the viewer would otherwise sit on a broken state.
    """
    if not isinstance(raw, dict):
        raise TypeError("State must be an object")

    state_type = raw.get("type", "none")
    if state_type == "none":
        return _empty_state()
    if state_type != "pptx":
        raise ValueError("Unknown state type")

    state = _parse_pptx_state(raw)
    if not os.path.isfile(_file_path(module, resource, state["file"])):
        raise FileNotFoundError(state["file"])
    return state


def _default_state(data: dict[str, Any]) -> dict[str, Any]:
    """The start state stored in the resource, or ``{"type": "none"}``."""
    return _coerce_state(data.get("default_state"))


def _coerce_state(raw: Any) -> dict[str, Any]:
    """Best-effort conversion of stored state data to a valid state.

    Unlike ``_normalize_state`` this never raises: stored bookmarks may
    reference a file that has since been deleted, and the list view must
    still render them.
    """
    if not isinstance(raw, dict) or raw.get("type") != "pptx":
        return _empty_state()
    try:
        return _parse_pptx_state(raw)
    except ValueError:
        return _empty_state()


def sanitize_bookmark_name(name: str) -> str:
    """Return a safe, non-empty bookmark key or raise ``ValueError``."""
    if not isinstance(name, str):
        raise ValueError("Bookmark name must be text")
    stripped = name.strip()
    if not stripped:
        raise ValueError("Bookmark name is empty")
    if len(stripped) > 64:
        raise ValueError("Bookmark name is too long")
    if any(ord(char) < 32 or ord(char) == 127 for char in stripped):
        raise ValueError("Bookmark name contains control characters")
    if "/" in stripped or "\\" in stripped:
        raise ValueError("Bookmark name must not contain a path")
    return stripped


def _bookmarks(data: dict[str, Any]) -> dict[str, Any]:
    """The well-formed bookmarks stored in a resource, keyed by name."""
    raw = data.get("bookmarks", {})
    if not isinstance(raw, dict):
        return {}
    return {
        name: bookmark
        for name, bookmark in raw.items()
        if isinstance(name, str) and isinstance(bookmark, dict)
    }


def _bookmark_meta(bookmark: Any) -> dict[str, Any]:
    """The ``meta`` sub-dict of a bookmark, or an empty dict."""
    if not isinstance(bookmark, dict):
        return {}
    meta = bookmark.get("meta")
    return dict(meta) if isinstance(meta, dict) else {}


def _shortcut_of(meta: dict[str, Any]) -> str:
    """The normalized shortcut code stored in a bookmark's meta, or ``""``."""
    shortcut = meta.get("shortcut")
    if not isinstance(shortcut, str):
        return ""
    return shortcut.strip()


# ---------------------------------------------------------------------------
# Bookmark shortcut listeners
# ---------------------------------------------------------------------------

# (module, resource, bookmark name) -> ShortcutCodeListener.  Only bookmarks
# whose meta carries a non-empty "shortcut" appear here.
_bookmark_listeners: dict[tuple[str, str, str], Any] = {}
_bookmark_lock = threading.Lock()


def _make_bookmark_callback(module: str, resource: str, name: str):
    """Build the shortcut callback for a bookmark.

    The callback re-reads the bookmark at trigger time so that overwriting a
    bookmark with a new state takes effect without touching the listener.
    """

    def callback(code: str, t: float, props: dict[str, Any]) -> None:
        data = _resource_data(module, resource)
        if data is None:
            return
        bookmark = _bookmarks(data).get(name)
        if bookmark is None:
            return
        _publish_state(module, resource, _coerce_state(bookmark.get("state")))

    return callback


def _close_bookmark_listener(module: str, resource: str, name: str) -> None:
    with _bookmark_lock:
        listener = _bookmark_listeners.pop((module, resource, name), None)
    if listener is not None:
        try:
            listener.close()
        except Exception:
            logger.debug(
                "Could not close bookmark shortcut listener",
                exc_info=True,
            )


def _sync_bookmark_listener(
    module: str, resource: str, name: str, meta: dict[str, Any]
) -> None:
    """(Re)register the shortcut listener for one bookmark from its meta.

    Any previously registered listener is closed first, so this is the
    bookmark "change handler" that runs whenever meta changes.
    """
    _close_bookmark_listener(module, resource, name)
    shortcut = _shortcut_of(meta)
    if not shortcut:
        return
    try:
        listener = chandler_api.ShortcutCodeListener(
            shortcut,
            _make_bookmark_callback(module, resource, name),
            description=f"Presentation bookmark {name}",
        )
    except Exception:
        logger.exception(
            "Could not register shortcut for bookmark %s/%s/%s",
            module,
            resource,
            name,
        )
        return
    with _bookmark_lock:
        _bookmark_listeners[(module, resource, name)] = listener


def _sync_bookmark_listeners(
    module: str, resource: str, bookmarks: dict[str, Any]
) -> None:
    """Reconcile every listener for a resource with its stored bookmarks."""
    keep: set[str] = set()
    for name, bookmark in bookmarks.items():
        meta = _bookmark_meta(bookmark)
        if _shortcut_of(meta):
            keep.add(name)
        _sync_bookmark_listener(module, resource, name, meta)

    with _bookmark_lock:
        stale = [
            key
            for key in _bookmark_listeners
            if key[0] == module and key[1] == resource and key[2] not in keep
        ]
    for key in stale:
        _close_bookmark_listener(*key)


def _close_all_bookmark_listeners(module: str, resource: str | None = None):
    """Close every listener for a resource, or a whole module."""
    with _bookmark_lock:
        keys = [
            key
            for key in _bookmark_listeners
            if key[0] == module and (resource is None or key[1] == resource)
        ]
    for key in keys:
        _close_bookmark_listener(*key)


def _effective_state(
    module: str, resource: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Current state if one was set, else the resource's default."""
    state = _current_states.get((module, resource))
    return dict(state) if state is not None else _default_state(data)


def _publish_state(module: str, resource: str, state: dict[str, Any]) -> None:
    """Make ``state`` the current state and push it to every viewer."""
    _current_states[(module, resource)] = state
    _broadcast(module, resource, {"action": "state", "state": state})


# ---------------------------------------------------------------------------
# Resource type
# ---------------------------------------------------------------------------


class PresentationScreenType(resource_types.ResourceType):
    """A screen that shows PowerPoint files from its ``.content`` folder."""

    def __init__(self):
        schema = {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "title": "Title",
                    "default": "Presentation Screen",
                },
                "view_permission": {
                    "type": "string",
                    "title": "Viewing permission",
                    "description": (
                        "Permission a viewer must hold to watch.  Leave "
                        "empty to allow guests."
                    ),
                    "default": "",
                },
                "default_state": {
                    "type": "object",
                    "title": "Default start state",
                    "default": {"type": "none"},
                },
                "bookmarks": {
                    "type": "object",
                    "title": "Bookmarked states",
                    "description": (
                        "Named states, each {name: {state, meta}}.  meta "
                        "never becomes part of the played state."
                    ),
                    "default": {},
                },
            },
        }
        super().__init__(
            type="presentation_screen",
            mdi_icon="presentation",
            title="Presentation Screen",
            schema=schema,
            priority=50,
        )

    def _admin_url(self, module: str, resource: str) -> str:
        return f"/presentation-screen/admin/{quote(module)}/{quote(resource)}"

    @override
    def blurb(
        self,
        module: str,
        resource: str,
        data: modules_state.ResourceDictType,
    ) -> str:
        title = data.get("title", "Presentation Screen")
        admin_url = self._admin_url(module, resource)
        return f"""
        <div data-testid="presentation-screen-blurb-{quote(resource)}">
            <p><strong>{title}</strong></p>
            <a href="{admin_url}" class="btn"
               data-testid="edit-presentation-screen">Manage</a>
        </div>
        """  # noqa: E501

    @override
    def create_page(self, module: str, path: str) -> str:
        dialog = SimpleDialog("New Presentation Screen")
        dialog.text_input("name", title="Resource Name")
        dialog.text_input("title", title="Title")
        dialog.submit_button("Create")
        return dialog.render(self.get_create_target(module, path.strip("/")))

    @override
    def on_create_request(
        self, module: str, resource: str, kwargs: dict[str, Any]
    ) -> modules_state.ResourceDictType:
        return {
            "resource": {"type": self.type},
            "title": kwargs.get("title") or "Presentation Screen",
            "view_permission": "",
            "default_state": _empty_state(),
            "bookmarks": {},
        }

    @override
    def on_load(
        self,
        module: str,
        resource: str,
        data: modules_state.ResourceDictType,
    ) -> None:
        try:
            _ensure_content_dir(module, resource)
        except Exception:
            logger.exception(
                "Could not create presentation content dir for %s/%s",
                module,
                resource,
            )
        _sync_bookmark_listeners(module, resource, _bookmarks(data))

    @override
    def on_update(
        self,
        module: str,
        resource: str,
        data: modules_state.ResourceDictType,
    ) -> None:
        _sync_bookmark_listeners(module, resource, _bookmarks(data))

    @override
    def edit_page(
        self,
        module: str,
        resource: str,
        data: modules_state.ResourceDictType,
    ):
        return quart.redirect(self._admin_url(module, resource))

    @override
    def on_update_request(
        self,
        module: str,
        resource: str,
        data: modules_state.ResourceDictType,
        kwargs: dict[str, Any],
    ) -> modules_state.ResourceDictType:
        result = modules.mutable_copy_resource(data)
        result.update(kwargs)
        return result

    @override
    def on_unload(
        self,
        module: str,
        resource: str,
        data: modules_state.ResourceDictType,
    ) -> None:
        _close_all_bookmark_listeners(module, resource)

    @override
    def on_delete_module(self, module: str) -> None:
        _close_all_bookmark_listeners(module)

    @override
    def on_delete(
        self,
        module: str,
        resource: str,
        data: modules_state.ResourceDictType,
    ) -> None:
        _current_states.pop((module, resource), None)
        _close_all_bookmark_listeners(module, resource)
        try:
            path = _content_dir(module, resource)
            if os.path.isdir(path):
                shutil.rmtree(path)
        except Exception:
            logger.exception(
                "Error removing presentation content for %s/%s",
                module,
                resource,
            )


presentation_screen_type = PresentationScreenType()
modules_state.resource_types["presentation_screen"] = presentation_screen_type


# ---------------------------------------------------------------------------
# Page routes (redirect into the Vite apps)
# ---------------------------------------------------------------------------


@quart_app.route("/presentation-screen/admin/<module>/<resource>")
async def admin_page(module: str, resource: str):
    web.require("system_admin")
    return quart.redirect(
        "/static/vite/kaithem/src/plugins/"
        "CorePluginPresentationScreen/html/admin.html"
        f"?module={quote(module)}&resource={quote(resource)}"
    )


@quart_app.route("/presentation-screen/editor/<module>/<resource>")
async def presentation_editor_page(module: str, resource: str):
    web.require("system_admin")
    params = {"module": module, "resource": resource}
    requested = quart.request.args.get("file")
    if requested:
        params["file"] = requested
    return quart.redirect(
        "/static/vite/kaithem/src/plugins/"
        "CorePluginPresentationScreen/html/editor.html?" + urlencode(params)
    )


@quart_app.route("/presentation-screen/viewer/<module>/<resource>")
async def presentation_viewer_page(module: str, resource: str):
    _data, error = _check_view_access(module, resource)
    if error is not None:
        return error
    return quart.redirect(
        "/static/vite/kaithem/src/plugins/"
        "CorePluginPresentationScreen/html/viewer.html"
        f"?module={quote(module)}&resource={quote(resource)}"
    )


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

api_bp = Blueprint(
    "presentation_screen_api",
    __name__,
    url_prefix="/presentation-screen/api",
)


@api_bp.route("/files/<module>/<resource>", methods=["GET"])
async def presentation_list_files(module: str, resource: str):
    error = _check_admin()
    if error is not None:
        return error
    if _resource_data(module, resource) is None:
        return quart.jsonify({"error": "not_found"}), 404

    directory = _content_dir(module, resource)
    files: list[dict[str, Any]] = []
    try:
        for name in os.listdir(directory):
            if not name.lower().endswith(".pptx"):
                continue
            full = os.path.join(directory, name)
            if not os.path.isfile(full):
                continue
            stat = os.stat(full)
            files.append(
                {
                    "name": name,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
            )
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not list presentation files")
        return quart.jsonify({"error": "list_failed"}), 500

    files.sort(key=lambda item: item["name"])
    return quart.jsonify({"files": files})


@api_bp.route("/file/<module>/<resource>/<filename>", methods=["GET"])
async def presentation_get_file(module: str, resource: str, filename: str):
    _data, error = _check_view_access(module, resource)
    if error is not None:
        return error

    try:
        path = _file_path(module, resource, filename)
    except ValueError as exc:
        return quart.jsonify({"error": str(exc)}), 400

    if not os.path.isfile(path):
        return quart.jsonify({"error": "not_found"}), 404

    response = await quart.send_file(path, mimetype=PPTX_MIME)
    response.headers["Cache-Control"] = "no-store"
    return response


@api_bp.route(
    "/save/<module>/<resource>/<filename>",
    methods=["POST"],
)
async def presentation_save_file(module: str, resource: str, filename: str):
    error = _check_admin()
    if error is not None:
        return error
    if _resource_data(module, resource) is None:
        return quart.jsonify({"error": "not_found"}), 404

    try:
        safe_name = sanitize_pptx_filename(filename)
    except ValueError as exc:
        return quart.jsonify({"error": str(exc)}), 400

    data = await quart.request.get_data()
    if not data:
        return quart.jsonify({"error": "empty_body"}), 400
    if len(data) > MAX_UPLOAD_BYTES:
        return quart.jsonify({"error": "file_too_large"}), 413
    if not (isinstance(data, bytes) and data.startswith(b"PK")):
        return quart.jsonify({"error": "not_a_pptx"}), 400

    path = os.path.join(_ensure_content_dir(module, resource), safe_name)
    try:
        _atomic_write(path, data)
    except OSError:
        logger.exception("Could not save presentation file")
        return quart.jsonify({"error": "save_failed"}), 500

    return quart.jsonify({"status": "ok", "name": safe_name})


@api_bp.route(
    "/delete/<module>/<resource>/<filename>",
    methods=["POST"],
)
async def presentation_delete_file(module: str, resource: str, filename: str):
    error = _check_admin()
    if error is not None:
        return error
    if _resource_data(module, resource) is None:
        return quart.jsonify({"error": "not_found"}), 404

    try:
        path = _file_path(module, resource, filename)
    except ValueError as exc:
        return quart.jsonify({"error": str(exc)}), 400

    if not os.path.isfile(path):
        return quart.jsonify({"error": "not_found"}), 404

    try:
        os.unlink(path)
    except OSError:
        logger.exception("Could not delete presentation file")
        return quart.jsonify({"error": "delete_failed"}), 500

    key = (module, resource)
    state = _current_states.get(key)
    if state is not None and state.get("file") == os.path.basename(path):
        fallback = _default_state(_resource_data(module, resource) or {})
        _publish_state(module, resource, fallback)

    return quart.jsonify({"status": "ok"})


@api_bp.route("/config/<module>/<resource>", methods=["GET"])
async def presentation_get_config(module: str, resource: str):
    data = _resource_data(module, resource)
    if data is None:
        return quart.jsonify({"error": "not_found"}), 404
    return quart.jsonify(
        {
            "title": data.get("title", "Presentation Screen"),
            "view_permission": _view_permission(data),
        }
    )


@api_bp.route("/config/<module>/<resource>", methods=["POST"])
async def presentation_set_config(module: str, resource: str):
    error = _check_admin()
    if error is not None:
        return error
    data = _resource_data(module, resource)
    if data is None:
        return quart.jsonify({"error": "not_found"}), 404

    body = await quart.request.get_json(force=True, silent=True) or {}
    if not isinstance(body, dict):
        return quart.jsonify({"error": "invalid_body"}), 400

    result = modules.mutable_copy_resource(data)
    if "title" in body:
        title = body["title"]
        if not isinstance(title, str) or not title.strip():
            return quart.jsonify({"error": "invalid_title"}), 400
        if len(title) > 200:
            return quart.jsonify({"error": "title_too_long"}), 400
        result["title"] = title.strip()
    if "view_permission" in body:
        permission = body["view_permission"]
        if not isinstance(permission, str):
            return quart.jsonify({"error": "invalid_view_permission"}), 400
        permission = permission.strip()
        if len(permission) > 100:
            return quart.jsonify({"error": "view_permission_too_long"}), 400
        result["view_permission"] = permission
        result.pop("view_requires_admin", None)

    modules_state.raw_insert_resource(module, resource, result)
    return quart.jsonify(
        {
            "status": "ok",
            "title": result["title"],
            "view_permission": _view_permission(result),
        }
    )


@api_bp.route("/status/<module>/<resource>", methods=["GET"])
async def presentation_get_status(module: str, resource: str):
    error = _check_admin()
    if error is not None:
        return error
    if _resource_data(module, resource) is None:
        return quart.jsonify({"error": "not_found"}), 404
    clients = _connections.get((module, resource), set())
    return quart.jsonify({"connected": len(clients)})


@api_bp.route("/state/<module>/<resource>", methods=["GET"])
async def presentation_get_state(module: str, resource: str):
    data, error = _check_view_access(module, resource)
    if error is not None:
        return error
    return quart.jsonify(
        {
            "state": _effective_state(module, resource, data),
            "default_state": _default_state(data),
        }
    )


@api_bp.route("/state/<module>/<resource>", methods=["POST"])
async def presentation_set_state(module: str, resource: str):
    """Replace the whole current state; this is the only way to change it."""
    error = _check_admin()
    if error is not None:
        return error
    if _resource_data(module, resource) is None:
        return quart.jsonify({"error": "not_found"}), 404

    body = await quart.request.get_json(force=True, silent=True) or {}
    try:
        state = _normalize_state(module, resource, body)
    except FileNotFoundError:
        return quart.jsonify({"error": "file_not_found"}), 404
    except (TypeError, ValueError) as exc:
        return quart.jsonify({"error": str(exc)}), 400

    _publish_state(module, resource, state)
    return quart.jsonify({"status": "ok", "state": state})


@api_bp.route("/state-default/<module>/<resource>", methods=["POST"])
async def presentation_set_default_state(module: str, resource: str):
    """Copy the current state into the resource as its start state."""
    error = _check_admin()
    if error is not None:
        return error
    data = _resource_data(module, resource)
    if data is None:
        return quart.jsonify({"error": "not_found"}), 404

    default_state = _effective_state(module, resource, data)
    result = modules.mutable_copy_resource(data)
    result["default_state"] = default_state
    modules_state.raw_insert_resource(module, resource, result)
    return quart.jsonify({"status": "ok", "default_state": default_state})


@api_bp.route("/bookmarks/<module>/<resource>", methods=["GET"])
async def presentation_list_bookmarks(module: str, resource: str):
    """Every bookmark on a screen: its state and its meta."""
    error = _check_admin()
    if error is not None:
        return error
    data = _resource_data(module, resource)
    if data is None:
        return quart.jsonify({"error": "not_found"}), 404

    bookmarks = {
        name: {
            "state": _coerce_state(bookmark.get("state")),
            "meta": _bookmark_meta(bookmark),
        }
        for name, bookmark in _bookmarks(data).items()
    }
    return quart.jsonify({"bookmarks": bookmarks})


def _write_bookmarks(
    module: str, resource: str, data: dict[str, Any], bookmarks: dict[str, Any]
) -> None:
    result = modules.mutable_copy_resource(data)
    result["bookmarks"] = bookmarks
    modules_state.raw_insert_resource(module, resource, result)


@api_bp.route("/bookmarks/<module>/<resource>/<name>/save", methods=["POST"])
async def presentation_save_bookmark(module: str, resource: str, name: str):
    """Store the current state under ``name``; existing meta is kept."""
    error = _check_admin()
    if error is not None:
        return error
    data = _resource_data(module, resource)
    if data is None:
        return quart.jsonify({"error": "not_found"}), 404

    try:
        clean_name = sanitize_bookmark_name(name)
    except ValueError as exc:
        return quart.jsonify({"error": str(exc)}), 400

    state = _effective_state(module, resource, data)
    bookmarks = dict(_bookmarks(data))
    existing = bookmarks.get(clean_name)
    meta = _bookmark_meta(existing) if existing is not None else {}
    bookmarks[clean_name] = {"state": state, "meta": meta}
    _write_bookmarks(module, resource, data, bookmarks)
    return quart.jsonify({"status": "ok", "bookmark": bookmarks[clean_name]})


@api_bp.route("/bookmarks/<module>/<resource>/<name>/goto", methods=["POST"])
async def presentation_goto_bookmark(module: str, resource: str, name: str):
    """Publish the state stored in a bookmark, excluding its meta."""
    error = _check_admin()
    if error is not None:
        return error
    data = _resource_data(module, resource)
    if data is None:
        return quart.jsonify({"error": "not_found"}), 404

    try:
        clean_name = sanitize_bookmark_name(name)
    except ValueError as exc:
        return quart.jsonify({"error": str(exc)}), 400

    bookmark = _bookmarks(data).get(clean_name)
    if bookmark is None:
        return quart.jsonify({"error": "not_found"}), 404

    try:
        state = _normalize_state(module, resource, bookmark.get("state"))
    except FileNotFoundError:
        return quart.jsonify({"error": "file_not_found"}), 404
    except (TypeError, ValueError) as exc:
        return quart.jsonify({"error": str(exc)}), 400

    _publish_state(module, resource, state)
    return quart.jsonify({"status": "ok", "state": state})


@api_bp.route("/bookmarks/<module>/<resource>/<name>/meta", methods=["POST"])
async def presentation_set_bookmark_meta(module: str, resource: str, name: str):
    """Replace a bookmark's meta and re-run its change handlers."""
    error = _check_admin()
    if error is not None:
        return error
    data = _resource_data(module, resource)
    if data is None:
        return quart.jsonify({"error": "not_found"}), 404

    try:
        clean_name = sanitize_bookmark_name(name)
    except ValueError as exc:
        return quart.jsonify({"error": str(exc)}), 400

    bookmarks = dict(_bookmarks(data))
    bookmark = bookmarks.get(clean_name)
    if bookmark is None:
        return quart.jsonify({"error": "not_found"}), 404

    body = await quart.request.get_json(force=True, silent=True) or {}
    meta = body.get("meta") if isinstance(body, dict) else None
    if not isinstance(meta, dict):
        return quart.jsonify({"error": "invalid_meta"}), 400

    shortcut = _shortcut_of(meta)
    if len(shortcut) > 64:
        return quart.jsonify({"error": "shortcut_too_long"}), 400

    bookmarks[clean_name] = {
        "state": _coerce_state(bookmark.get("state")),
        "meta": dict(meta),
    }
    _write_bookmarks(module, resource, data, bookmarks)
    _sync_bookmark_listener(module, resource, clean_name, dict(meta))
    return quart.jsonify({"status": "ok", "bookmark": bookmarks[clean_name]})


@api_bp.route("/bookmarks/<module>/<resource>/<name>/delete", methods=["POST"])
async def presentation_delete_bookmark(module: str, resource: str, name: str):
    """Remove a bookmark and tear down its shortcut listener."""
    error = _check_admin()
    if error is not None:
        return error
    data = _resource_data(module, resource)
    if data is None:
        return quart.jsonify({"error": "not_found"}), 404

    try:
        clean_name = sanitize_bookmark_name(name)
    except ValueError as exc:
        return quart.jsonify({"error": str(exc)}), 400

    bookmarks = dict(_bookmarks(data))
    if clean_name not in bookmarks:
        return quart.jsonify({"error": "not_found"}), 404

    del bookmarks[clean_name]
    _write_bookmarks(module, resource, data, bookmarks)
    _close_bookmark_listener(module, resource, clean_name)
    return quart.jsonify({"status": "ok"})


quart_app.register_blueprint(api_bp)


@quart_app.websocket("/presentation-screen/ws/<module>/<resource>")
async def presentation_ws_viewer(module: str, resource: str):
    if not _ws_can_view(module, resource):
        await quart.websocket.close(1008)
        return

    key = (module, resource)
    ws = quart.websocket
    connections = _connections.setdefault(key, set())
    connections.add(ws)

    topic = _command_topic(module, resource)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)

    def on_command(data: Any) -> None:
        payload = json.dumps(data)

        def _put() -> None:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("Presentation command queue full, dropping")

        loop.call_soon_threadsafe(_put)

    messagebus.subscribe(topic, on_command)

    try:
        # Every new connection starts from the server's state, so a refresh
        # picks the show back up where the server says it is.
        data = _resource_data(module, resource) or {}
        initial = {
            "action": "state",
            "state": _effective_state(module, resource, data),
        }
        await ws.send(json.dumps(initial))
        while True:
            try:
                queued = queue.get_nowait()
                await ws.send(queued)
            except asyncio.QueueEmpty:
                pass

            try:
                message = await asyncio.wait_for(ws.receive(), timeout=0.1)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if message is None:
                break

            # Viewers never drive the show; acknowledge keepalives only.
            try:
                parsed = json.loads(message)
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict) and parsed.get("action") == "ping":
                await ws.send(json.dumps({"action": "pong"}))
    except Exception:
        logger.debug("Presentation websocket closed", exc_info=True)
    finally:
        try:
            messagebus.unsubscribe(topic, on_command)
        except Exception:
            logger.debug("Could not unsubscribe presentation socket")
        connections.discard(ws)
        if not connections:
            _connections.pop(key, None)
