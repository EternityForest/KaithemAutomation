# SPDX-License-Identifier: GPL-3.0-or-later
"""Registry of tools the agentic loop can call.

Tools are plain Python callables registered globally by name.  The loop
turns them into OpenAI tool definitions and routes model tool calls back
to the callable.  No tool is registered by default yet: the registry
exists so modules and future work have a stable place to plug in.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

ToolFunction = Callable[[dict[str, Any]], Awaitable[str] | str]

_EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


@dataclass
class Tool:
    """A function the model is allowed to call."""

    name: str
    description: str
    function: ToolFunction
    parameters: dict[str, Any] = field(
        default_factory=lambda: dict(_EMPTY_SCHEMA)
    )

    def openai_spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_tools: dict[str, Tool] = {}


def register_tool(tool: Tool) -> None:
    """Add or replace a tool in the global registry."""
    if not tool.name:
        raise ValueError("A tool must have a name")
    _tools[tool.name] = tool


def get_tool(name: str) -> Tool | None:
    return _tools.get(name)


def all_tools() -> list[Tool]:
    return sorted(_tools.values(), key=lambda tool: tool.name)


def openai_tools(names: list[str] | None = None) -> list[dict[str, Any]]:
    """Tool definitions for the API, optionally limited to some names."""
    if names:
        selected = [t for t in all_tools() if t.name in names]
    else:
        selected = all_tools()
    return [tool.openai_spec() for tool in selected]


async def call_tool(name: str, arguments: dict[str, Any]) -> str:
    """Run a tool and return its string result.

    Raises :class:`KeyError` for an unknown tool and re-raises anything
    the tool itself raises; the agentic loop converts both into a tool
    message so the model can recover.
    """
    tool = _tools.get(name)
    if tool is None:
        raise KeyError(f"Unknown tool {name!r}")
    result = tool.function(arguments)
    if inspect.isawaitable(result):
        result = await result
    return str(result)
