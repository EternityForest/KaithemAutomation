# SPDX-License-Identifier: GPL-3.0-or-later
"""Bluetooth console plugin.

The BlueZ D-Bus wrapper lives in :mod:`bluez` and has no web dependencies.
This module is the web layer: REST endpoints, a WebSocket that streams live
state and pairing prompts, the Vite page redirect, and the apps-page entry.

Pairing prompts (PIN, passkey, confirmation, service authorization) are
delivered to the browser as WebSocket ``agent_request`` events and resolved
with ``agent_response`` messages.
"""

import asyncio
import json
import logging

import quart
from quart import Blueprint

import kaithem.api.apps_page
from kaithem.api import web
from kaithem.api.lifespan import at_shutdown
from kaithem.api.web import quart_app

from .bluez import BluezError, BluezManager, BluezUnavailableError

logger = logging.getLogger(__name__)

manager = BluezManager()

at_shutdown(manager.stop)

api_bp = Blueprint(
    "bluetooth_console_api",
    __name__,
    url_prefix="/bluetooth/api",
)


def _check_admin() -> tuple[quart.Response, int] | None:
    """Return a deterministic 403 response for non-admin API callers."""
    if web.has_permission("system_admin"):
        return None
    return quart.jsonify({"error": "forbidden"}), 403


def _check_ws_admin() -> bool:
    return web.has_permission("system_admin", asgi=quart.websocket.scope)


def _error_response(exc: BluezError) -> tuple[quart.Response, int]:
    if isinstance(exc, BluezUnavailableError):
        return quart.jsonify(exc.to_dict()), 503
    return quart.jsonify(exc.to_dict()), 400


def _ok(snapshot: dict) -> quart.Response:
    return quart.jsonify({"status": "ok", "snapshot": snapshot})


@api_bp.route("/snapshot", methods=["GET"])
async def bluetooth_snapshot():
    error = _check_admin()
    if error is not None:
        return error
    snapshot = await asyncio.to_thread(manager.snapshot)
    return quart.jsonify(
        {
            "status": "ok",
            "snapshot": snapshot,
            "agent_requests": manager.pending_agent_requests(),
        }
    )


@api_bp.route("/refresh", methods=["POST"])
async def bluetooth_refresh():
    error = _check_admin()
    if error is not None:
        return error
    try:
        snapshot = await asyncio.to_thread(manager.refresh)
    except BluezError as exc:
        return _error_response(exc)
    return _ok(snapshot)


@api_bp.route("/discovering", methods=["POST"])
async def bluetooth_set_discovering():
    error = _check_admin()
    if error is not None:
        return error
    body = await quart.request.get_json(force=True, silent=True) or {}
    if not isinstance(body, dict) or not isinstance(
        body.get("discovering"), bool
    ):
        return quart.jsonify({"error": "invalid_request"}), 400
    try:
        snapshot = await asyncio.to_thread(
            manager.set_discovering, body["discovering"]
        )
    except BluezError as exc:
        return _error_response(exc)
    return _ok(snapshot)


@api_bp.route("/devices/<address>/pair", methods=["POST"])
async def bluetooth_pair(address: str):
    error = _check_admin()
    if error is not None:
        return error
    try:
        snapshot = await asyncio.to_thread(manager.pair, address)
    except BluezError as exc:
        return _error_response(exc)
    return _ok(snapshot)


@api_bp.route("/devices/<address>/connect", methods=["POST"])
async def bluetooth_connect(address: str):
    error = _check_admin()
    if error is not None:
        return error
    try:
        snapshot = await asyncio.to_thread(manager.connect, address)
    except BluezError as exc:
        return _error_response(exc)
    return _ok(snapshot)


@api_bp.route("/devices/<address>/disconnect", methods=["POST"])
async def bluetooth_disconnect(address: str):
    error = _check_admin()
    if error is not None:
        return error
    try:
        snapshot = await asyncio.to_thread(manager.disconnect, address)
    except BluezError as exc:
        return _error_response(exc)
    return _ok(snapshot)


@api_bp.route("/devices/<address>/trust", methods=["POST"])
async def bluetooth_set_trusted(address: str):
    error = _check_admin()
    if error is not None:
        return error
    body = await quart.request.get_json(force=True, silent=True) or {}
    if not isinstance(body, dict) or not isinstance(body.get("trusted"), bool):
        return quart.jsonify({"error": "invalid_request"}), 400
    try:
        snapshot = await asyncio.to_thread(
            manager.set_trusted, address, body["trusted"]
        )
    except BluezError as exc:
        return _error_response(exc)
    return _ok(snapshot)


@api_bp.route("/devices/<address>/forget", methods=["POST"])
async def bluetooth_forget(address: str):
    error = _check_admin()
    if error is not None:
        return error
    try:
        snapshot = await asyncio.to_thread(manager.forget, address)
    except BluezError as exc:
        return _error_response(exc)
    return _ok(snapshot)


quart_app.register_blueprint(api_bp)


@quart_app.route("/bluetooth")
async def bluetooth_page():
    web.require("system_admin")
    return quart.redirect(
        "/static/vite/kaithem/src/plugins/CorePluginBluetooth/html/index.html"
    )


@quart_app.websocket("/bluetooth/ws")
async def bluetooth_websocket():
    if not _check_ws_admin():
        await quart.websocket.close(1008)
        return

    ws = quart.websocket
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=200)

    def put_event(event: dict) -> None:
        try:
            queue.put_nowait(json.dumps(event))
        except asyncio.QueueFull:
            logger.warning("Bluetooth WebSocket queue full, dropping event")

    def on_event(event: dict) -> None:
        try:
            loop.call_soon_threadsafe(put_event, event)
        except RuntimeError:
            pass

    manager.add_listener(on_event)
    try:
        snapshot = await asyncio.to_thread(manager.snapshot)
        await ws.send(
            json.dumps(
                {
                    "type": "snapshot",
                    "snapshot": snapshot,
                    "agent_requests": manager.pending_agent_requests(),
                }
            )
        )

        async def send_loop() -> None:
            while True:
                payload = await queue.get()
                await ws.send(payload)

        async def receive_loop() -> None:
            while True:
                raw = await ws.receive()
                if raw is None:
                    break
                if not isinstance(raw, str):
                    continue
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(message, dict):
                    continue
                message_type = message.get("type")
                if message_type == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
                elif message_type == "agent_response":
                    request_id = message.get("id")
                    if not isinstance(request_id, str):
                        continue
                    resolved = manager.respond_to_agent_request(
                        request_id,
                        bool(message.get("accepted")),
                        message.get("value")
                        if isinstance(message.get("value"), str)
                        else None,
                    )
                    if not resolved:
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "error",
                                    "error": "unknown_agent_request",
                                    "id": request_id,
                                }
                            )
                        )

        send_task = asyncio.create_task(send_loop())
        receive_task = asyncio.create_task(receive_loop())
        done, pending = await asyncio.wait(
            {send_task, receive_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None:
                logger.debug("Bluetooth WebSocket closed: %s", exc)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Bluetooth WebSocket failed")
    finally:
        manager.remove_listener(on_event)


app = kaithem.api.apps_page.App(
    "coreplugins_bluetooth",
    title="Bluetooth",
    url="/bluetooth",
)
app.icon = "/static/img/16x9/ultraviolet-light-bulb.avif"

kaithem.api.apps_page.add_app(app)
