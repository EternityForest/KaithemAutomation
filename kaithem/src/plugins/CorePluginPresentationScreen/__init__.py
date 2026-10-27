# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation screen resource type and PPTX file management.

A ``presentation_screen`` resource owns a FileData folder named
``<resource>.content`` holding plain ``.pptx`` files.  Admin users can
upload, list, edit, and delete those files; viewing may be opened to
guests via the ``view_requires_admin`` setting.

Viewer pages keep a WebSocket open and receive playback commands
(load / stop / next / prev / goto).  Every connected viewer receives the
same command, broadcast through the message bus.
"""

import asyncio
import json
import os
import shutil
import tempfile
from typing import Any, override
from urllib.parse import quote, urlencode

import quart
import structlog
from quart import Blueprint

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


def _view_is_open(data: dict[str, Any]) -> bool:
    return not bool(data.get("view_requires_admin", False))


def _require_view_access(module: str, resource: str) -> dict[str, Any] | None:
    """Allow guests when viewing is open, otherwise require admin."""
    data = _resource_data(module, resource)
    if data is None:
        return None
    if not _view_is_open(data):
        web.require("system_admin")
    return data


def _ws_can_view(module: str, resource: str) -> bool:
    """Permission check usable from a websocket handler.

    ``web.require`` reads ``quart.request``, which is unavailable while
    handling a websocket; pass the ASGI scope explicitly instead.
    """
    data = _resource_data(module, resource)
    if data is None:
        return False
    if _view_is_open(data):
        return True
    scope: Any = quart.websocket.scope
    return web.has_permission("system_admin", asgi=scope)


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
                "view_requires_admin": {
                    "type": "boolean",
                    "title": "Viewing requires admin",
                    "default": False,
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
            "view_requires_admin": False,
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

    @override
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
    def on_delete(
        self,
        module: str,
        resource: str,
        data: modules_state.ResourceDictType,
    ) -> None:
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
    _require_view_access(module, resource)
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
    web.require("system_admin")
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
    if _require_view_access(module, resource) is None:
        return quart.jsonify({"error": "not_found"}), 404

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
    web.require("system_admin")
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
    web.require("system_admin")
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

    return quart.jsonify({"status": "ok"})


@api_bp.route("/config/<module>/<resource>", methods=["GET"])
async def presentation_get_config(module: str, resource: str):
    data = _resource_data(module, resource)
    if data is None:
        return quart.jsonify({"error": "not_found"}), 404
    return quart.jsonify(
        {
            "title": data.get("title", "Presentation Screen"),
            "view_requires_admin": not _view_is_open(data),
        }
    )


@api_bp.route("/config/<module>/<resource>", methods=["POST"])
async def presentation_set_config(module: str, resource: str):
    web.require("system_admin")
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
    if "view_requires_admin" in body:
        result["view_requires_admin"] = bool(body["view_requires_admin"])

    modules_state.raw_insert_resource(module, resource, result)
    return quart.jsonify(
        {
            "status": "ok",
            "title": result["title"],
            "view_requires_admin": result["view_requires_admin"],
        }
    )


@api_bp.route("/status/<module>/<resource>", methods=["GET"])
async def presentation_get_status(module: str, resource: str):
    web.require("system_admin")
    if _resource_data(module, resource) is None:
        return quart.jsonify({"error": "not_found"}), 404
    clients = _connections.get((module, resource), set())
    return quart.jsonify({"connected": len(clients)})


@api_bp.route("/command/<module>/<resource>", methods=["POST"])
async def presentation_send_command(module: str, resource: str):
    web.require("system_admin")
    if _resource_data(module, resource) is None:
        return quart.jsonify({"error": "not_found"}), 404

    body = await quart.request.get_json(force=True, silent=True) or {}
    if not isinstance(body, dict):
        return quart.jsonify({"error": "invalid_body"}), 400

    action = body.get("action")
    if action not in ("load", "stop", "next", "prev", "goto"):
        return quart.jsonify({"error": "invalid_action"}), 400

    payload: dict[str, Any] = {"action": action}

    if action == "load":
        try:
            filename = sanitize_pptx_filename(str(body.get("file", "")))
        except ValueError as exc:
            return quart.jsonify({"error": str(exc)}), 400
        path = os.path.join(_content_dir(module, resource), filename)
        if not os.path.isfile(path):
            return quart.jsonify({"error": "file_not_found"}), 404
        payload["file"] = filename

    if action == "goto":
        slide = body.get("slide")
        if not isinstance(slide, int) or isinstance(slide, bool):
            return quart.jsonify({"error": "invalid_slide"}), 400
        if slide < 0:
            return quart.jsonify({"error": "invalid_slide"}), 400
        payload["slide"] = slide

    _broadcast(module, resource, payload)
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
        await ws.send(json.dumps({"action": "ready"}))
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
