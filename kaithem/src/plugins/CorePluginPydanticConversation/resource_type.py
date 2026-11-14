# SPDX-License-Identifier: GPL-3.0-or-later
"""``conversation`` resource type.

A ``conversation`` resource owns one agentic conversation.  The resource
data holds the conversation id (a UUID), the model tag, the permissions
required to read and write it, and whether history is persisted.

Creating the resource generates the id and registers the config with the
conversation registry.  Deleting the resource deletes the conversation's
persistent history.
"""

from __future__ import annotations

import html
import uuid
from typing import Any

import structlog

from kaithem.api import ai, resource_types
from kaithem.api.web import dialogs

from . import conversation as conversation_registry
from .models import ConversationConfig

logger = structlog.get_logger(__name__)

RESOURCE_TYPE = "conversation"

_SEPARATORS = ", \t\n"


def parse_permissions(value: Any) -> list[str]:
    """Parse a permissions field into an ordered list of strings."""
    if value is None:
        return ["system_admin"]
    if isinstance(value, str):
        parts = value.replace(",", " ").split()
    elif isinstance(value, list | tuple):
        parts = []
        for item in value:
            parts.extend(str(item).replace(",", " ").split())
    else:
        parts = [str(value)]
    result: list[str] = []
    for part in parts:
        part = part.strip().strip(_SEPARATORS)
        if part and part not in result:
            result.append(part)
    return result or ["system_admin"]


def _model_suggestions() -> list[tuple[str, str]]:
    return [(tag, f"{tag} (globally configured)") for tag in ai.MODEL_TAGS]


class ConversationType(resource_types.ResourceType):
    """The ``conversation`` resource type."""

    def __init__(self) -> None:
        super().__init__(RESOURCE_TYPE, mdi_icon="chat-outline", priority=45.0)
        self._by_module: dict[str, set[str]] = {}

    # -- helpers ----------------------------------------------------------

    def _config(
        self, module: str, resource: str, data: Any
    ) -> ConversationConfig:
        raw = dict(data.get("data") or {})
        if not raw.get("id"):
            raw["id"] = uuid.uuid4().hex
            updated = dict(data)
            updated["data"] = raw
            try:
                self.save_resource(module, resource, updated)
            except Exception:
                logger.exception(
                    "Could not persist conversation id for %s/%s",
                    module,
                    resource,
                )
        self._by_module.setdefault(module, set()).add(str(raw["id"]))
        return ConversationConfig(
            id=str(raw["id"]),
            title=str(raw.get("title") or ""),
            model=str(raw.get("model") or "chat"),
            permissions=parse_permissions(raw.get("permissions")),
            persistent=bool(raw.get("persistent", True)),
            system_prompt=str(raw.get("system_prompt") or ""),
            workspace=str(raw.get("workspace") or "").strip(),
        )

    # -- lifecycle --------------------------------------------------------

    def on_load(self, module, resource, data):
        config = self._config(module, resource, data)
        conversation_registry.register_config(config)

    def on_update(self, module, resource, data):
        self.on_load(module, resource, data)

    def on_unload(self, module, resource, data):
        config = self._config(module, resource, data)
        conversation_registry.unregister_config(config.id)

    def on_delete(self, module, resource, data):
        config = self._config(module, resource, data)
        self._by_module.get(module, set()).discard(config.id)
        conversation_registry.delete_conversation(config.id)

    def on_delete_module(self, module: str):
        for conversation_id in list(self._by_module.get(module, set())):
            conversation_registry.delete_conversation(conversation_id)
        self._by_module.pop(module, None)

    def on_move(self, module, resource, to_module, to_resource, data):
        config = self._config(module, resource, data)
        self._by_module.get(module, set()).discard(config.id)
        self._by_module.setdefault(to_module, set()).add(config.id)

    # -- editor -----------------------------------------------------------

    def create_page(self, module, path):
        d = dialogs.SimpleDialog("New Conversation")
        d.text_input("name", title="Resource Name")
        d.text_input("title", title="Conversation Title")
        d.text_input(
            "model",
            title="Model",
            default="chat",
            suggestions=_model_suggestions(),
        )
        d.text_input(
            "permissions",
            title="Permissions",
            default="system_admin",
            suggestions=[
                ("system_admin", "system_admin"),
                ("__guest__", "__guest__ (anyone)"),
            ],
        )
        d.checkbox("persistent", title="Keep history on disk", default=True)
        d.text_input(
            "workspace",
            title="Workspace Folder",
            default="",
            suggestions=[("", "none (chat only)")],
        )
        d.text_input("system_prompt", title="System Prompt", multiline=True)
        d.submit_button("Save")
        return d.render(self.get_create_target(module, path))

    def edit_page(self, module, resource, data):
        raw = dict(data.get("data") or {})
        d = dialogs.SimpleDialog("Editing Conversation")
        d.text_input(
            "model",
            title="Model",
            default=str(raw.get("model") or "chat"),
            suggestions=_model_suggestions(),
        )
        d.text_input(
            "permissions",
            title="Permissions",
            default=" ".join(parse_permissions(raw.get("permissions"))),
            suggestions=[
                ("system_admin", "system_admin"),
                ("__guest__", "__guest__ (anyone)"),
            ],
        )
        d.checkbox(
            "persistent",
            title="Keep history on disk",
            default=bool(raw.get("persistent", True)),
        )
        d.text_input(
            "workspace",
            title="Workspace Folder",
            default=str(raw.get("workspace") or ""),
            suggestions=[("", "none (chat only)")],
        )
        d.text_input(
            "system_prompt",
            title="System Prompt",
            default=str(raw.get("system_prompt") or ""),
            multiline=True,
        )
        conversation_id = str(raw.get("id") or "")
        if conversation_id:
            d.link("Open Chat", f"/conversations/{conversation_id}")
        d.submit_button("Save")
        return d.render(self.get_update_target(module, resource))

    def _request_data(
        self, existing: Any, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        kwargs = dict(kwargs)
        raw = dict((existing or {}).get("data") or {})
        raw["id"] = str(raw.get("id") or uuid.uuid4().hex)
        raw["title"] = str(
            kwargs.get("title") or kwargs.get("name") or raw.get("title") or ""
        ).strip()
        raw["model"] = (
            str(kwargs.get("model") or raw.get("model") or "chat").strip()
            or "chat"
        )
        if "permissions" in kwargs:
            raw["permissions"] = parse_permissions(kwargs["permissions"])
        else:
            raw["permissions"] = parse_permissions(raw.get("permissions"))
        raw["persistent"] = bool(kwargs.get("persistent"))
        raw["system_prompt"] = str(kwargs.get("system_prompt") or "").strip()
        raw["workspace"] = str(kwargs.get("workspace") or "").strip()
        return raw

    def on_create_request(self, module, resource, kwargs):
        raw = self._request_data({}, kwargs)
        return {"resource": {"type": self.type}, "data": raw}

    def on_update_request(self, module, resource, data, kwargs):
        new_data = resource_types.mutable_copy_resource(data)
        new_data["data"] = self._request_data(data, kwargs)
        return new_data

    def blurb(self, module, resource, data):
        raw = dict(data.get("data") or {})
        conversation_id = str(raw.get("id") or "")
        title = str(raw.get("title") or resource)
        model = str(raw.get("model") or "chat")
        if not conversation_id:
            return (
                f'<div class="error" data-testid="conversation-error-'
                f'{html.escape(resource)}">Conversation id is missing</div>'
            )
        return (
            f'<div data-testid="conversation-blurb-'
            f'{html.escape(resource)}">'
            f"<p><strong>{html.escape(title)}</strong></p>"
            f"<p>Model: <code>{html.escape(model)}</code></p>"
            f'<a href="/conversations/{html.escape(conversation_id)}" '
            f'class="btn" data-testid="open-conversation">Open Chat</a>'
            f"</div>"
        )


resource_types.register_resource_type(ConversationType())
