# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import json
import os
from urllib.parse import quote

import quart
import structlog

from kaithem.api.web import dialogs
from kaithem.src import (
    messagebus,
    modules_state,
    pages,
    quart_app,
)

logger = structlog.get_logger(__name__)

plugin_dir = os.path.dirname(__file__)

# WebSocket connections by resource
_websocket_connections = {}


class ProjectionMapperType(modules_state.ResourceType):
    """Resource type for projection mapping configurations"""

    def __init__(self):
        schema = {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "title": "Projection Title",
                    "default": "Untitled Projection",
                },
                "sources": {
                    "type": "array",
                    "title": "Sources",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "title": "ID"},
                            "name": {
                                "type": "string",
                                "title": "Source Name",
                            },
                            "type": {
                                "type": "string",
                                "title": "Source Type",
                                "enum": ["iframe"],
                            },
                            "config": {
                                "type": "object",
                                "title": "Configuration",
                                "properties": {
                                    "url": {
                                        "type": "string",
                                        "title": "URL",
                                    }
                                },
                            },
                            "transform": {
                                "type": "object",
                                "title": "Transform",
                                "properties": {
                                    "corners": {
                                        "type": ["object", "null"],
                                        "title": "Corner Points",
                                    },
                                    "opacity": {
                                        "type": "number",
                                        "title": "Opacity",
                                        "default": 1.0,
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                    "blend_mode": {
                                        "type": "string",
                                        "title": "Blend Mode",
                                        "default": "normal",
                                    },
                                    "rotation": {
                                        "type": "number",
                                        "title": "Rotation",
                                        "default": 0,
                                    },
                                },
                            },
                            "vfx": {
                                "type": "array",
                                "title": "VFX Pipeline",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "shader": {
                                            "type": "string",
                                            "title": "Shader",
                                        },
                                        "params": {
                                            "type": "object",
                                            "title": "Parameters",
                                        },
                                    },
                                },
                            },
                            "visible": {
                                "type": "boolean",
                                "title": "Visible",
                                "default": True,
                            },
                        },
                    },
                },
            },
        }

        super().__init__(
            type="projection_mapper",
            mdi_icon="projector-screen",
            title="Projection Mapper",
            schema=schema,
            priority=50,
        )

    def blurb(
        self, module: str, resource: str, data: modules_state.ResourceDictType
    ) -> str:
        title = data.get("title", "Untitled Projection")
        sources_count = len(data.get("sources", []))

        editor_url = (
            f"/projection-mapper/editor/{quote(module)}/{quote(resource)}"
        )
        viewer_url = (
            f"/projection-mapper/view/{quote(module)}/{quote(resource)}"
        )

        return f"""
        <div>
            <p><strong>{title}</strong></p>
            <p>{sources_count} source(s)</p>
            <a href="{editor_url}" class="btn">Edit</a>
            <a href="{viewer_url}" class="btn" target="_blank">View</a>
        </div>
        """

    def create_page(self, module: str, path: str) -> str:
        d = dialogs.SimpleDialog("New Projection Mapper")
        d.text_input(
            "name",
            title="Resource Name",
        )
        d.text_input(
            "title",
            title="Projection Title",
        )
        d.submit_button("Create")
        return d.render(self.get_create_target(module, path.strip("/")))

    def on_create_request(
        self, module: str, resource: str, kwargs: dict
    ) -> modules_state.ResourceDictType:
        return {
            "resource": {"type": self.type},
            "title": kwargs.get("title", "Untitled Projection"),
            "size": {"width": 1920, "height": 1080},
            "sources": [],
        }

    def edit_page(
        self, module: str, resource: str, data: modules_state.ResourceDictType
    ) -> str:
        # Redirect to full-page editor
        self.set_edit_page_redirect(
            f"/projection-mapper/editor/{quote(module)}/{quote(resource)}"
        )
        return "<p>Redirecting to editor...</p>"

    def on_update_request(
        self,
        module: str,
        resource: str,
        data: modules_state.ResourceDictType,
        kwargs: dict,
    ) -> modules_state.ResourceDictType:
        d = modules_state.mutable_copy_resource(data)
        d.update(kwargs)
        return d


# Register the resource type
_projection_mapper_type = ProjectionMapperType()
modules_state.resource_types["projection_mapper"] = _projection_mapper_type


# Routes
@quart_app.app.route("/projection-mapper/editor/<module>/<resource>")
async def editor_page(module: str, resource: str):
    """Authenticated projection mapper editor"""
    pages.require("system_admin")

    # Load the resource
    try:
        data = modules_state.ActiveModules[module][resource]
    except (KeyError, TypeError):
        return "Resource not found", 404

    template_path = os.path.join(plugin_dir, "html", "editor.html")
    with open(template_path) as f:
        template_content = f.read()

    return await quart.render_template_string(
        template_content,
        module=module,
        resource=resource,
        data=json.dumps(data),
    )


@quart_app.app.route("/projection-mapper/view/<module>/<resource>")
async def viewer_page(module: str, resource: str):
    """Guest-accessible projection mapper viewer"""

    # Load the resource
    try:
        data = modules_state.ActiveModules[module][resource]
    except (KeyError, TypeError):
        return "Resource not found", 404

    template_path = os.path.join(plugin_dir, "html", "viewer.html")
    with open(template_path) as f:
        template_content = f.read()

    return await quart.render_template_string(
        template_content,
        module=module,
        resource=resource,
        data=json.dumps(data),
    )


@quart_app.app.route("/projection-mapper/api/data/<module>/<resource>")
async def api_get_data(module: str, resource: str):
    """Get projection data (guest accessible for viewer)"""
    try:
        data = modules_state.ActiveModules[module][resource]
        return quart.jsonify(data)
    except (KeyError, TypeError):
        return quart.jsonify({"error": "not_found"}), 404


@quart_app.app.route(
    "/projection-mapper/api/save/<module>/<resource>",
    methods=["POST"],
)
async def api_save_data(module: str, resource: str):
    """Save projection data (authenticated)"""
    pages.require("system_admin")

    try:
        data = await quart.request.json
        modules_state.save_resource(module, resource, data)
        return quart.jsonify({"status": "ok"})
    except Exception as e:
        logger.exception("Failed to save projection")
        return (
            quart.jsonify({"error": "save_failed", "message": str(e)}),
            500,
        )


@quart_app.app.websocket("/projection-mapper/ws/<module>/<resource>")
async def ws_transform_sync(module: str, resource: str):
    """WebSocket for real-time transform synchronization"""
    pages.require("system_admin")

    key = (module, resource)

    # Register this connection
    if key not in _websocket_connections:
        _websocket_connections[key] = []

    ws = quart.websocket
    _websocket_connections[key].append(ws)

    topic = f"/projection/{module}/{resource}/transform"

    # Queue for messages from messagebus thread
    message_queue = asyncio.Queue()

    try:
        # Subscribe to messagebus updates for this resource
        def on_transform_update(data):
            try:
                # Queue message safely (thread-safe)
                message_queue.put_nowait(json.dumps(data))
            except asyncio.QueueFull:
                logger.warning("Transform queue full, dropping message")

        messagebus.subscribe(topic, on_transform_update)

        # Listen for messages - either from client or queued
        while True:
            try:
                # Check for queued messages (don't block)
                try:
                    queued_msg = message_queue.get_nowait()
                    await ws.send(queued_msg)
                except asyncio.QueueEmpty:
                    pass

                # Wait for client message (with timeout for
                # checking queue)
                message = await asyncio.wait_for(ws.receive(), timeout=0.1)
                msg_data = json.loads(message)

                # Broadcast to all connected clients via
                # messagebus
                messagebus.post_message(
                    topic,
                    {
                        "type": "transform_update",
                        **msg_data,
                    },
                )
            except TimeoutError:
                # Timeout is normal, just loop back to
                # check queue
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("WebSocket error")
                break

    finally:
        # Cleanup
        try:
            messagebus.unsubscribe(
                topic,
                on_transform_update,  # type: ignore
            )
        except Exception:
            pass

        if key in _websocket_connections:
            try:
                _websocket_connections[key].remove(ws)
            except ValueError:
                pass

        if key in _websocket_connections and not (_websocket_connections[key]):
            del _websocket_connections[key]


@quart_app.app.route("/projection-mapper/static/<path:path>")
async def static_files(path: str):
    """Serve static assets for projection mapper"""
    try:
        return await quart.send_file(os.path.join(plugin_dir, "static", path))
    except FileNotFoundError:
        return "Not found", 404
