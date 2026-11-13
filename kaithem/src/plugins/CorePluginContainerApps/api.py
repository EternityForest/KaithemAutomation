# SPDX-License-Identifier: GPL-3.0-or-later
"""REST and websocket API for the container app resources.

Two management surfaces share this module:

``app``
    The development view of a ``container_app``.  It can build, run the
    project in throwaway dev mode, run named action scripts, and copy the
    starter template.

``instance``
    The admin view of a ``container_app_instance``.  It can start and
    stop the running app and show its output.

Every endpoint is admin only: these pages manage the app, they are not
the app itself.  The app is reached through its path proxy under
``/apps/<name>``.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import quart
import structlog
from quart import Blueprint

from kaithem.api import web
from kaithem.api.web import quart_app
from kaithem.src import modules_state

from .constants import APP_RESOURCE_TYPE, INSTANCE_RESOURCE_TYPE

if TYPE_CHECKING:
    from . import ContainerAppInstanceResource, ContainerAppResource

logger = structlog.get_logger(__name__)

api_bp = Blueprint(
    "container_apps_api",
    __name__,
    url_prefix="/containerapps/api",
)

#: Vite build of the admin front end.
PAGE_URL = "/static/vite/kaithem/src/plugins/CorePluginContainerApps/index.html"


# -- Lookup helpers -----------------------------------------------------


def _get_app(module: str, resource: str) -> ContainerAppResource | None:
    resource_type = modules_state.resource_types.get(APP_RESOURCE_TYPE)
    if resource_type is None:
        return None
    return resource_type.runtime_objects.get((module, resource))


def _get_instance(
    module: str, resource: str
) -> ContainerAppInstanceResource | None:
    resource_type = modules_state.resource_types.get(INSTANCE_RESOURCE_TYPE)
    if resource_type is None:
        return None
    return resource_type.runtime_objects.get((module, resource))


def _require_admin() -> tuple[quart.Response, int] | None:
    if web.has_permission("system_admin"):
        return None
    return quart.jsonify({"error": "forbidden"}), 403


def _error(message: str, status: int = 400):
    return quart.jsonify({"error": message}), status


# -- Snapshots ----------------------------------------------------------


def _app_snapshot(app: ContainerAppResource) -> dict[str, Any]:
    runtime = app.runtime
    return {
        "type": "app",
        "module": app.module,
        "resource": app.resource,
        "title": app.title,
        "status": app.status,
        "error": app.error,
        "dev": app.is_dev,
        "built": app.is_built(),
        "empty": app.is_empty(),
        "kind": app.app_kind,
        "scripts": app.scripts,
        "dev_url": app.dev_prefix,
        "build_image": runtime.build_image if runtime else None,
        "run_image": runtime.run_image if runtime else None,
        "log": app.get_log(),
        "environment": app.get_environment(),
    }


def _instance_snapshot(
    instance: ContainerAppInstanceResource,
) -> dict[str, Any]:
    runtime = instance.runtime
    app_ref = ""
    if instance.app_module is not None:
        app_ref = f"{instance.app_module}:{instance.app_resource}"
    return {
        "type": "instance",
        "module": instance.module,
        "resource": instance.resource,
        "title": instance.data.get("title") or instance.name,
        "name": instance.name,
        "status": instance.status,
        "error": instance.error,
        "running": instance.is_running(),
        "built": instance.is_built(),
        "kind": instance.app_kind,
        "app": app_ref,
        "url": instance.base_path,
        "build_image": runtime.build_image if runtime else None,
        "run_image": runtime.run_image if runtime else None,
        "log": instance.get_log(),
        "environment": instance.get_environment(),
    }


# -- Actions ------------------------------------------------------------


def _script_name(body: dict[str, Any]) -> str:
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("'name' must be a script name")
    return name.strip()


APP_ACTIONS: dict[str, Any] = {
    "build": lambda app, body: app.build(),
    "dev": lambda app, body: app.start_dev(),
    "stop-dev": lambda app, body: app.stop_dev(),
    "reload": lambda app, body: app.reload(),
    "clean": lambda app, body: app.clean(),
    "delete-runtime": lambda app, body: app.delete_runtime(),
    "copy-template": lambda app, body: app.copy_template(),
    "run-script": lambda app, body: app.run_script(_script_name(body)),
}

INSTANCE_ACTIONS: dict[str, Any] = {
    "start": lambda instance, body: instance.start(),
    "stop": lambda instance, body: instance.stop(),
    "reload": lambda instance, body: instance.reload(),
    "delete-runtime": lambda instance, body: instance.delete_runtime(),
}


async def _read_body() -> dict[str, Any]:
    """Return the JSON request body, or an empty dict if there is none."""
    raw = await quart.request.get_data()
    if not raw:
        return {}
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("Body must be valid JSON") from None
    if not isinstance(body, dict):
        raise ValueError("Body must be a JSON object")
    return body


async def _run_action(handler, target, action: str):
    try:
        body = await _read_body()
    except ValueError as exc:
        return _error(str(exc), 400)
    try:
        await asyncio.to_thread(handler, target, body)
    except KeyError as exc:
        return _error(str(exc), 404)
    except Exception as exc:
        logger.exception("Container app action %r failed", action)
        return _error(str(exc), 500)
    return None


# -- App endpoints ------------------------------------------------------


@api_bp.route("/app/<module>/<resource>", methods=["GET"])
async def get_app(module: str, resource: str):
    error = _require_admin()
    if error is not None:
        return error
    app = _get_app(module, resource)
    if app is None:
        return _error("not_found", 404)
    return quart.jsonify(_app_snapshot(app))


@api_bp.route("/app/<module>/<resource>/<action>", methods=["POST"])
async def app_action(module: str, resource: str, action: str):
    error = _require_admin()
    if error is not None:
        return error
    app = _get_app(module, resource)
    if app is None:
        return _error("not_found", 404)
    handler = APP_ACTIONS.get(action)
    if handler is None:
        return _error("unknown_action", 404)
    failure = await _run_action(handler, app, action)
    if failure is not None:
        return failure
    return quart.jsonify(_app_snapshot(app))


# -- Instance endpoints -------------------------------------------------


@api_bp.route("/instance/<module>/<resource>", methods=["GET"])
async def get_instance(module: str, resource: str):
    error = _require_admin()
    if error is not None:
        return error
    instance = _get_instance(module, resource)
    if instance is None:
        return _error("not_found", 404)
    return quart.jsonify(_instance_snapshot(instance))


@api_bp.route("/instance/<module>/<resource>/<action>", methods=["POST"])
async def instance_action(module: str, resource: str, action: str):
    error = _require_admin()
    if error is not None:
        return error
    instance = _get_instance(module, resource)
    if instance is None:
        return _error("not_found", 404)
    handler = INSTANCE_ACTIONS.get(action)
    if handler is None:
        return _error("unknown_action", 404)
    failure = await _run_action(handler, instance, action)
    if failure is not None:
        return failure
    return quart.jsonify(_instance_snapshot(instance))


# -- Websocket monitor --------------------------------------------------


async def _monitor(target, snapshot_fn) -> None:
    """Stream a target's log and status changes over the websocket."""
    runtime = target.runtime
    ws = quart.websocket
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)

    def push(payload: dict[str, Any]) -> None:
        text = json.dumps(payload)

        def _put() -> None:
            try:
                queue.put_nowait(text)
            except asyncio.QueueFull:
                logger.warning("Container app log queue full, dropping")

        loop.call_soon_threadsafe(_put)

    def on_log(line: str) -> None:
        push({"event": "log", "line": line})

    def on_status(status: str) -> None:
        push({"event": "status", "status": status})

    if runtime is not None:
        runtime.add_log_callback(on_log)
        runtime.add_status_callback(on_status)

    try:
        await ws.send(
            json.dumps({"event": "snapshot", "snapshot": snapshot_fn()})
        )
        while True:
            try:
                while True:
                    await ws.send(queue.get_nowait())
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
    except Exception:
        logger.debug("Container app websocket closed", exc_info=True)
    finally:
        if runtime is not None:
            runtime.remove_log_callback(on_log)
            runtime.remove_status_callback(on_status)


def _authorized_ws() -> bool:
    return web.has_permission("system_admin", asgi=quart.websocket.scope)


@quart_app.websocket("/containerapps/ws/app/<module>/<resource>")
async def app_websocket(module: str, resource: str):
    if not _authorized_ws():
        await quart.websocket.close(1008)
        return
    app = _get_app(module, resource)
    if app is None:
        await quart.websocket.close(1008)
        return
    await _monitor(app, lambda: _app_snapshot(app))


@quart_app.websocket("/containerapps/ws/instance/<module>/<resource>")
async def instance_websocket(module: str, resource: str):
    if not _authorized_ws():
        await quart.websocket.close(1008)
        return
    instance = _get_instance(module, resource)
    if instance is None:
        await quart.websocket.close(1008)
        return
    await _monitor(instance, lambda: _instance_snapshot(instance))


# -- Page redirects -----------------------------------------------------


def _page_redirect(*, kind: str, module: str, resource: str):
    web.require("system_admin")
    query = (
        f"type={kind}"
        f"&module={quote(module, safe='')}"
        f"&resource={quote(resource, safe='')}"
    )
    return quart.redirect(f"{PAGE_URL}?{query}")


@quart_app.route("/containerapps/app/<module>/<resource>")
async def container_app_page(module: str, resource: str):
    return _page_redirect(kind="app", module=module, resource=resource)


@quart_app.route("/containerapps/instance/<module>/<resource>")
async def container_instance_page(module: str, resource: str):
    return _page_redirect(kind="instance", module=module, resource=resource)


quart_app.register_blueprint(api_bp)
