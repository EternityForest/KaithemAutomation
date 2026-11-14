# SPDX-License-Identifier: GPL-3.0-or-later
"""Pydantic conversation plugin.

Agentic AI conversations backed by OpenRouter.  Each conversation is a
``conversation`` resource with a global UUID, a WebSocket driven chat UI,
append only LDJSON history, and a single agentic loop shared by all of
its threads.

This module is the web layer: a REST API, one WebSocket per open chat,
the redirect to the Vite page, and a lazy global registry that drops
conversations from memory once nobody is watching them.
"""

from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import quote

import quart
import structlog
from quart import Blueprint

from kaithem.api import web
from kaithem.api.lifespan import at_shutdown
from kaithem.api.web import quart_app

from . import conversation as registry
from . import tools
from .models import ConversationConfig

# Importing the resource type module registers the "conversation" type.
from .resource_type import RESOURCE_TYPE  # noqa: F401

logger = structlog.get_logger(__name__)

api_bp = Blueprint(
    "pydantic_conversation_api",
    __name__,
    url_prefix="/conversations/api",
)

_VITE_PAGE = (
    "/static/vite/kaithem/src/plugins/CorePluginPydanticConversation"
    "/html/index.html"
)


def _current_user(asgi: dict | None = None) -> str:
    """The authenticated user of the current request.

    Threads are namespaced per user, and this is the namespace key.  A
    request always has a caller, but outside a Quart context ``web.user``
    reports ``__no_request__``; that is folded into the guest namespace so
    the key is never empty and never clashes with the internal
    ``__system__`` namespace.
    """
    name = web.user(asgi=asgi)
    if not name or name == "__no_request__":
        return "__guest__"
    return name


def _forbidden() -> tuple[quart.Response, int]:
    return quart.jsonify({"error": "forbidden"}), 403


def _not_found() -> tuple[quart.Response, int]:
    return quart.jsonify({"error": "not_found"}), 404


def _bad_request(message: str) -> tuple[quart.Response, int]:
    return quart.jsonify({"error": "invalid_request", "message": message}), 400


#: Prefix of the id of a conversation that was auto-created for a folder.
WORKSPACE_ID_PREFIX = "admin."


def workspace_conversation_id(workspace: str) -> str:
    """The stable id of the conversation for a server folder.

    It is the URL encoded absolute path with an ``admin.`` prefix, so the
    same folder always maps to the same conversation without a UUID.
    """
    return WORKSPACE_ID_PREFIX + quote(workspace, safe="")


def _open_workspace_conversation(workspace: str):
    """Open, creating if needed, the admin conversation for a folder.

    Only a server admin may do this: the conversation gets file tools
    scoped to the folder, so it can read and edit whatever is in it.
    """
    if not web.has_permission(["system_admin"]):
        return _forbidden()
    path = os.path.realpath(workspace)
    if not os.path.isdir(path):
        return _bad_request(f"Not a folder on the server: {workspace}")
    conversation_id = workspace_conversation_id(path)
    if registry.get_config(conversation_id) is None:
        registry.register_config(
            ConversationConfig(
                id=conversation_id,
                title=os.path.basename(path) or path,
                model="code",
                permissions=["system_admin"],
                workspace=path,
                tools={name: True for name in tools.ADMIN_WORKSPACE_TOOLS},
            )
        )
    return quart.redirect(
        f"{_VITE_PAGE}?uuid={quote(conversation_id, safe='')}"
    )


def _load(
    conversation_id: str, asgi: dict | None = None
) -> tuple[ConversationConfig | None, tuple[quart.Response, int] | None]:
    """Load a config and check the caller's permissions."""
    config = registry.get_config(conversation_id)
    if config is None:
        return None, _not_found()
    if not web.has_permission(config.permissions, asgi=asgi):
        return None, _forbidden()
    return config, None


# -- REST API -------------------------------------------------------------


@api_bp.route("/<conversation_id>", methods=["GET"])
async def conversation_snapshot(conversation_id: str):
    config, error = _load(conversation_id)
    if error:
        return error
    conversation = registry.get_conversation(conversation_id)
    return quart.jsonify(
        {
            "status": "ok",
            "snapshot": conversation.snapshot(_current_user()),
        }
    )


@api_bp.route("/<conversation_id>/threads", methods=["GET"])
async def conversation_threads(conversation_id: str):
    config, error = _load(conversation_id)
    if error:
        return error
    conversation = registry.get_conversation(conversation_id)
    threads = conversation.list_threads(_current_user())
    return quart.jsonify(
        {
            "status": "ok",
            "threads": [t.model_dump() for t in threads],
        }
    )


@api_bp.route("/<conversation_id>/threads", methods=["POST"])
async def conversation_create_thread(conversation_id: str):
    config, error = _load(conversation_id)
    if error:
        return error
    body = await quart.request.get_json(force=True, silent=True) or {}
    title = body.get("title") if isinstance(body, dict) else None
    if not isinstance(title, str):
        return quart.jsonify({"error": "invalid_request"}), 400
    conversation = registry.get_conversation(conversation_id)
    info = conversation.create_thread(title, _current_user())
    return quart.jsonify({"status": "ok", "thread": info.model_dump()})


@api_bp.route("/<conversation_id>/threads/<slug>", methods=["GET"])
async def conversation_entries(conversation_id: str, slug: str):
    config, error = _load(conversation_id)
    if error:
        return error
    conversation = registry.get_conversation(conversation_id)
    try:
        entries = conversation.get_entries(slug, _current_user())
    except KeyError:
        return _not_found()
    return quart.jsonify({"status": "ok", "thread": slug, "entries": entries})


@api_bp.route("/<conversation_id>/threads/<slug>/messages", methods=["POST"])
async def conversation_send(conversation_id: str, slug: str):
    config, error = _load(conversation_id)
    if error:
        return error
    body = await quart.request.get_json(force=True, silent=True) or {}
    text = body.get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        return quart.jsonify({"error": "invalid_request"}), 400
    user = _current_user()
    conversation = registry.get_conversation(conversation_id)
    try:
        await conversation.send(slug, text, author=user, user=user)
    except KeyError:
        return _not_found()
    except (ValueError, RuntimeError) as exc:
        return quart.jsonify({"error": str(exc)}), 400
    return quart.jsonify({"status": "ok"})


@api_bp.route("/<conversation_id>/interrupt", methods=["POST"])
async def conversation_interrupt(conversation_id: str):
    config, error = _load(conversation_id)
    if error:
        return error
    conversation = registry.peek_conversation(conversation_id)
    if conversation is not None:
        conversation.interrupt()
    return quart.jsonify({"status": "ok"})


quart_app.register_blueprint(api_bp)


# -- page redirect and WebSocket -----------------------------------------


@quart_app.route("/conversations")
async def conversations_root():
    """Open the conversation for a server folder, creating it on demand.

    The folder is named by a ``workspace`` query argument, because the
    auto-created conversation's id is the URL encoded path and so cannot
    be a path segment of this route.
    """
    workspace = (quart.request.args.get("workspace") or "").strip()
    if not workspace:
        return _bad_request("Pass ?workspace=/path/on/server")
    return _open_workspace_conversation(workspace)


@quart_app.route("/conversations/<conversation_id>")
async def conversation_page(conversation_id: str):
    config, error = _load(conversation_id)
    if error:
        response, code = error
        return response, code
    target = f"{_VITE_PAGE}?uuid={quote(conversation_id, safe='')}"
    return quart.redirect(target)


async def _send_loop(websocket, queue: asyncio.Queue[str]) -> None:
    while True:
        payload = await queue.get()
        await websocket.send(payload)


async def _receive_loop(websocket, conversation, user, send_event) -> None:
    while True:
        raw = await websocket.receive()
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
        kind = message.get("type")
        if kind == "ping":
            send_event({"type": "pong"})
        elif kind == "subscribe":
            slug = message.get("thread")
            if isinstance(slug, str):
                try:
                    entries = conversation.get_entries(slug, user)
                except KeyError:
                    entries = []
                send_event(
                    {
                        "type": "entries",
                        "thread": slug,
                        "entries": entries,
                    }
                )
        elif kind == "interrupt":
            conversation.interrupt()


@quart_app.websocket("/conversations/ws/<conversation_id>")
async def conversation_websocket(conversation_id: str):
    scope = quart.websocket.scope
    config, error = _load(conversation_id, asgi=scope)
    if error or config is None:
        await quart.websocket.close(1008)
        return

    user = _current_user(asgi=scope)
    conversation = registry.get_conversation(conversation_id)
    websocket = quart.websocket
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)

    def send_event(event: dict) -> None:
        try:
            queue.put_nowait(json.dumps(event))
        except asyncio.QueueFull:
            logger.warning("Conversation WebSocket queue full")

    def on_event(event: dict) -> None:
        try:
            loop.call_soon_threadsafe(send_event, event)
        except RuntimeError:
            pass

    conversation.add_listener(user, on_event)
    try:
        send_event(
            {"type": "snapshot", "snapshot": conversation.snapshot(user)}
        )
        send_task = asyncio.create_task(_send_loop(websocket, queue))
        receive_task = asyncio.create_task(
            _receive_loop(websocket, conversation, user, send_event)
        )
        try:
            await asyncio.wait(
                {send_task, receive_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (send_task, receive_task):
                task.cancel()
            await asyncio.gather(
                send_task, receive_task, return_exceptions=True
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Conversation WebSocket failed")
    finally:
        conversation.remove_listener(user, on_event)
        conversation.maybe_unload()


def _shutdown() -> None:
    for config in registry.list_configs():
        registry.unload(config.id)


at_shutdown(_shutdown)
