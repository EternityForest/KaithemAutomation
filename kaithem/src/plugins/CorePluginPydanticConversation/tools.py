# SPDX-License-Identifier: GPL-3.0-or-later
"""Registry of tools a conversation can be given by name.

A conversation stores a ``tools: dict[str, bool]`` selection.  The registry
here maps each known tool name to a factory that builds the pydantic-ai
object -- a ``Tool`` or a capability -- the agent actually runs.  Keeping the
selection as names keeps it serializable, so a resource editor can show
checkboxes, while ``register_capabilities`` still lets an embedding app hand
a conversation live objects directly.

Every factory is given a :class:`ToolContext`, so a tool that writes files
knows the workspace it may write into and a tool that talks to a provider
knows the API base and key.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import structlog
from pydantic_ai import Tool
from pydantic_ai.exceptions import ModelRetry

from kaithem.api import ai

logger = structlog.get_logger(__name__)

#: Tools every conversation gets unless its selection overrides the list.
DEFAULT_TOOLS: tuple[str, ...] = ("time", "code_mode")

#: Tools the auto-created admin workspace conversations get.  This is the
#: central list of what a file-scoped admin agent is handed by default.
ADMIN_WORKSPACE_TOOLS: tuple[str, ...] = (
    "time",
    "image_gen",
    "speech",
    "web_search",
)

#: How long a media generation request may take, in seconds.
_MEDIA_TIMEOUT = 180.0


@dataclass
class ToolContext:
    """What a tool factory needs that is not part of the selection."""

    api_base: str = ""
    api_key: str = ""
    #: Absolute path of the folder the conversation may write files into.
    workspace: str = ""

    @property
    def can_write_files(self) -> bool:
        return bool(self.workspace)


#: A factory turns a context into the pydantic-ai object for one tool.
ToolFactory = Callable[[ToolContext], Any]


@dataclass
class ToolSpec:
    """One named tool: how it is shown in an editor and how it is built."""

    name: str
    label: str
    description: str
    factory: ToolFactory


_registry: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> None:
    """Add or replace a tool in the global registry."""
    if not spec.name:
        raise ValueError("A tool must have a name")
    _registry[spec.name] = spec


def get_spec(name: str) -> ToolSpec | None:
    return _registry.get(name)


def all_specs() -> list[ToolSpec]:
    """Every registered tool, in registration order."""
    return list(_registry.values())


def known_tools() -> list[str]:
    return list(_registry)


def resolve_tool_names(selection: dict[str, bool] | None) -> list[str]:
    """The tool names a conversation should build.

    The default list always applies, then the selection turns individual
    tools on or off.  Unknown names are ignored, so a config that requests a
    tool this build does not know still validates and runs.
    """
    names = set(DEFAULT_TOOLS)
    for name, enabled in (selection or {}).items():
        if enabled:
            names.add(name)
        else:
            names.discard(name)
    return [name for name in _registry if name in names]


def build_tools(
    selection: dict[str, bool] | None, context: ToolContext
) -> list[Any]:
    """Build the pydantic-ai objects for a conversation's tool selection.

    A factory that fails (for example a capability whose optional dependency
    is not installed) is logged and skipped rather than failing the run.
    """
    extras: list[Any] = []
    for name in resolve_tool_names(selection):
        spec = _registry.get(name)
        if spec is None:
            continue
        try:
            extras.append(spec.factory(context))
        except Exception:
            logger.exception("Could not build tool %s", name)
    return extras


# -- shared helpers -------------------------------------------------------


def _headers(context: ToolContext) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if context.api_key:
        headers["Authorization"] = f"Bearer {context.api_key}"
    return headers


def _unique_path(directory: str, filename: str) -> str:
    """A path inside ``directory`` that does not exist yet."""
    os.makedirs(directory, exist_ok=True)
    stem, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    index = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{stem}-{index}{ext}")
        index += 1
    return candidate


def _write_bytes(directory: str, filename: str, data: bytes) -> str:
    path = _unique_path(directory, filename)
    with open(path, "wb") as handle:
        handle.write(data)
    return os.path.relpath(path, directory)


async def _post_json(
    context: ToolContext, path: str, payload: dict[str, Any]
) -> Any:
    url = context.api_base + path
    async with httpx.AsyncClient(timeout=_MEDIA_TIMEOUT) as client:
        response = await client.post(
            url, json=payload, headers=_headers(context)
        )
    if response.status_code >= 400:
        raise ModelRetry(
            f"Request to {path} failed ({response.status_code}): "
            f"{response.text[:500]}"
        )
    return response.json()


async def _post_bytes(
    context: ToolContext, path: str, payload: dict[str, Any]
) -> bytes:
    url = context.api_base + path
    async with httpx.AsyncClient(timeout=_MEDIA_TIMEOUT) as client:
        response = await client.post(
            url, json=payload, headers=_headers(context)
        )
    if response.status_code >= 400:
        raise ModelRetry(
            f"Request to {path} failed ({response.status_code}): "
            f"{response.text[:500]}"
        )
    return response.content


def _require_workspace(context: ToolContext) -> None:
    if not context.can_write_files:
        raise ModelRetry(
            "This conversation has no workspace folder, so it cannot save "
            "generated files.  Give the conversation a workspace to use "
            "file producing tools."
        )


# -- time -----------------------------------------------------------------


def _time_payload(tz_name: str) -> dict[str, str]:
    """The current time as the fields the time tool reports."""
    tz_name = tz_name.strip()
    if tz_name:
        try:
            zone = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ModelRetry(
                f"Unknown timezone {tz_name!r}; use an IANA name such as "
                "'America/Denver'."
            ) from exc
        now = datetime.now(zone)
        name = tz_name
    else:
        now = datetime.now().astimezone()
        name = now.tzname() or "local"
    utc = now.astimezone(UTC)
    hour12 = now.hour % 12 or 12
    ampm = "AM" if now.hour < 12 else "PM"
    human = (
        f"{now.strftime('%A, %B')} {now.day}, {now.year} at "
        f"{hour12}:{now.minute:02d} {ampm} {now.strftime('%Z')}"
    )
    return {
        "utc_iso": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "local_iso": now.isoformat(timespec="seconds"),
        "timezone": name,
        "day_of_week": now.strftime("%A"),
        "human_readable": human,
    }


def _build_time(context: ToolContext) -> Tool:
    def get_time(timezone: str = "") -> str:
        """Return the current time.

        Args:
            timezone: An IANA timezone name such as "America/Denver", or an
                empty string for the server's own local time.
        """
        return json.dumps(_time_payload(timezone))

    return Tool(
        get_time,
        name="time",
        description="Return the current time, optionally for a named timezone.",
    )


# -- image generation -----------------------------------------------------


def _reference_part(context: ToolContext, reference: str) -> dict[str, Any]:
    """Turn a reference path or URL into an image content part."""
    reference = reference.strip()
    if reference.startswith(("http://", "https://")):
        url = reference
    else:
        path = (
            reference
            if os.path.isabs(reference)
            else os.path.join(context.workspace, reference)
        )
        with open(path, "rb") as handle:
            raw = handle.read()
        mime = mimetypes.guess_type(path)[0] or "image/png"
        encoded = base64.b64encode(raw).decode("ascii")
        url = f"data:{mime};base64,{encoded}"
    return {"type": "image_url", "image_url": {"url": url}}


async def _decode_image(context: ToolContext, data: Any) -> bytes:
    items = (data or {}).get("data") or []
    if not items:
        raise ModelRetry("The image model returned no image.")
    item = items[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    url = item.get("url")
    if url:
        async with httpx.AsyncClient(timeout=_MEDIA_TIMEOUT) as client:
            response = await client.get(url)
        response.raise_for_status()
        return response.content
    raise ModelRetry("The image model returned an unrecognized response.")


def _build_image_gen(context: ToolContext) -> Tool:
    async def generate_image(
        prompt: str,
        reference_images: list[str] | None = None,
        output_format: str = "png",
    ) -> str:
        """Generate an image from a text prompt and save it in the workspace.

        Args:
            prompt: Text description of the image to generate.
            reference_images: Optional reference images for image-to-image
                generation, as workspace relative paths or HTTP(S) URLs.
            output_format: Encoding of the result, such as "png" or "jpeg".
        """
        _require_workspace(context)
        model = ai.resolve_model("image")
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "output_format": output_format,
        }
        references = [
            _reference_part(context, reference)
            for reference in (reference_images or [])
        ]
        if references:
            payload["input_references"] = references
        data = await _post_json(context, "/images", payload)
        image = await _decode_image(context, data)
        extension = output_format.strip().lstrip(".") or "png"
        path = _write_bytes(context.workspace, f"image.{extension}", image)
        return json.dumps({"path": path, "model": model})

    return Tool(
        generate_image,
        name="generate_image",
        description=(
            "Generate an image from a prompt and save it into the workspace."
        ),
    )


# -- speech and sound effects ---------------------------------------------


def _build_speech(context: ToolContext) -> Tool:
    async def generate_audio(
        text: str,
        mode: Literal["speech", "sound_effects"] = "speech",
        voice: str = "",
        response_format: str = "mp3",
    ) -> str:
        """Generate spoken audio or a sound effect and save it.

        Args:
            text: The words to speak, or a description of the sound effect.
            mode: "speech" for spoken words, "sound_effects" for a described
                sound.
            voice: Optional provider specific voice identifier.
            response_format: Audio encoding, "mp3" or "pcm".
        """
        _require_workspace(context)
        model = ai.resolve_model(
            mode if mode in ("speech", "sound_effects") else "speech"
        )
        payload: dict[str, Any] = {
            "input": text,
            "model": model,
            "response_format": response_format,
        }
        if voice:
            payload["voice"] = voice
        audio = await _post_bytes(context, "/audio/speech", payload)
        extension = response_format.strip().lstrip(".") or "mp3"
        path = _write_bytes(context.workspace, f"audio.{extension}", audio)
        return json.dumps({"path": path, "model": model, "mode": mode})

    return Tool(
        generate_audio,
        name="generate_audio",
        description=(
            "Generate speech or a sound effect and save it into the workspace."
        ),
    )


# -- pydantic-ai provided tools -------------------------------------------


def _build_web_search(context: ToolContext) -> Any:
    from pydantic_ai.capabilities import WebSearch

    return WebSearch(local="duckduckgo")


def _build_web_fetch(context: ToolContext) -> Any:
    from pydantic_ai.capabilities import WebFetch

    return WebFetch(local=True)


def _build_code_mode(context: ToolContext) -> Any:
    from pydantic_ai_harness import CodeMode

    return CodeMode()


# -- the registry ---------------------------------------------------------

register_tool(
    ToolSpec(
        name="time",
        label="Time",
        description="Report the current time, optionally for a named timezone.",
        factory=_build_time,
    )
)
register_tool(
    ToolSpec(
        name="image_gen",
        label="Image generation",
        description="Generate images and save them in the workspace.",
        factory=_build_image_gen,
    )
)
register_tool(
    ToolSpec(
        name="speech",
        label="Speech and sound effects",
        description="Generate spoken audio or sound effects as files.",
        factory=_build_speech,
    )
)
register_tool(
    ToolSpec(
        name="web_search",
        label="Web search",
        description="Search the web with DuckDuckGo.",
        factory=_build_web_search,
    )
)
register_tool(
    ToolSpec(
        name="web_fetch",
        label="Web fetch",
        description="Fetch and read the contents of a URL.",
        factory=_build_web_fetch,
    )
)
register_tool(
    ToolSpec(
        name="code_mode",
        label="Code mode",
        description="Run the agent's tools from a sandboxed Python snippet.",
        factory=_build_code_mode,
    )
)
