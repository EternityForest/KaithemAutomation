# SPDX-License-Identifier: GPL-3.0-or-later
"""Ephemeral agent queries: ask a configured agent one question.

A conversation resource owns a persistent, threaded chat.  This module is
the other half: a one shot query against the same agent, using the very
settings the resource was configured with, without any of the history.
Nothing about the call is written to disk, so it is safe to fire from an
event handler, a tag script, or a webhook; the file tools still work, so
an agent with a workspace can read and edit its files as usual.

The public entry point is re-exported as :func:`kaithem.api.ai.agent_query`.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import pydantic_ai.agent
import structlog

from kaithem.api import ai
from kaithem.src import quart_app as _quart_app

from .agent import build_agent, usage_from
from .conversation import get_capabilities, get_config
from .models import Usage
from .tools import ToolContext, build_tools

logger = structlog.get_logger(__name__)


@dataclass
class AgentRunInfo:
    """What a query reports about the run it performed.

    ``output`` is the model's answer and ``info`` carries the bookkeeping:
    which agent and model ran, what it cost, and, when the run failed,
    what went wrong.
    """

    agent_id: str
    model: str = ""
    usage: Usage | None = None
    #: The error message when the run failed, else None.
    error: str | None = None


#: A query callback receives the model output and the run info.  It is
#: called on the worker thread that ran the query, not the caller's.
QueryCallback = Callable[[Any, AgentRunInfo], None]


def _build_ephemeral(
    agent_id: str, output_type: Any
) -> tuple[pydantic_ai.agent.Agent[Any, Any], str]:
    """Build a throwaway pydantic-ai agent from a stored config.

    The agent is assembled exactly as a live conversation would build it
    -- same model, prompt, tools, capabilities and workspace -- but no
    history is read and nothing is written back.
    """
    config = get_config(agent_id)
    if config is None:
        raise KeyError(f"Unknown agent {agent_id!r}")
    api_base = ai.get_api_base()
    api_key = ai.get_api_key()
    model_id = ai.resolve_model(config.model)
    workspace = config.workspace
    context = ToolContext(
        api_base=api_base, api_key=api_key, workspace=workspace
    )
    extras = build_tools(config.tools, context)
    extras.extend(get_capabilities(agent_id))
    agent = build_agent(
        model_id=model_id,
        api_base=api_base,
        api_key=api_key,
        system_prompt=config.system_prompt,
        workspace=workspace,
        extras=extras,
        output_type=output_type,
    )
    return agent, model_id


async def _discard_events(ctx: Any, events: AsyncIterable[Any]) -> None:
    """Consume a run's stream events, which a query has no use for.

    Attaching an event handler is also what makes pydantic-ai stream the
    response, which is how a live conversation runs and what keeps the
    two paths behaving the same.
    """
    async for _event in events:
        pass


async def _query(
    agent_id: str, prompt: str, output_type: Any
) -> tuple[Any, AgentRunInfo]:
    """Run one ephemeral query and return its output and run info."""
    agent, model_id = _build_ephemeral(agent_id, output_type)
    result = await agent.run(prompt, event_stream_handler=_discard_events)
    info = AgentRunInfo(
        agent_id=agent_id,
        model=model_id,
        usage=usage_from(result.usage),
    )
    return result.output, info


# -- running a coroutine from synchronous code ----------------------------


def _main_loop() -> asyncio.AbstractEventLoop | None:
    """The server's running event loop, or None outside a server."""
    loop = getattr(_quart_app, "main_web_loop", None)
    if loop is not None and loop.is_running():
        return loop
    return None


def _running_loop() -> asyncio.AbstractEventLoop | None:
    """The event loop of the current thread, if one is running."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _run_in_thread(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine to completion on a private loop in a new thread.

    This is the fallback that keeps a query callable from anywhere: from
    a plain thread, from inside a running loop, or from a process that
    never started the server.
    """
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["result"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - re-raised in caller
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True, name="agent-query")
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _run_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine from synchronous code and return its result.

    The server's main event loop is preferred when it is available and
    the caller is not itself inside a loop, so anything loop bound stays
    on it.  Otherwise the coroutine runs on a private loop in a worker
    thread, which keeps a call made from inside an event loop from
    deadlocking.
    """
    if _running_loop() is not None:
        return _run_in_thread(coro)
    loop = _main_loop()
    if loop is not None:
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    return _run_in_thread(coro)


def _report(
    agent_id: str,
    prompt: str,
    output_type: Any,
    callback: QueryCallback,
) -> None:
    """Run a query in the background and hand the result to a callback."""
    output: Any = None
    info = AgentRunInfo(agent_id=agent_id)
    try:
        output, info = asyncio.run(_query(agent_id, prompt, output_type))
    except Exception as exc:
        logger.exception("Ephemeral query for agent %s failed", agent_id)
        info = AgentRunInfo(agent_id=agent_id, error=str(exc))
    try:
        callback(output, info)
    except Exception:
        logger.exception("Ephemeral query callback raised")


def agent_query(
    agent_id: str,
    prompt: str,
    output_type: Any = None,
    callback: QueryCallback | None = None,
) -> Any:
    """Ask a configured agent one question, with no persisted history.

    ``agent_id`` names a ``conversation`` resource.  The query runs on an
    ephemeral agent built from that resource's settings, so it does not
    create a conversation, does not read or write any thread, and leaves
    nothing behind on disk.  The agent's own file tools still work, so a
    resource with a workspace can read and edit files as normal.

    ``output_type`` is handed straight to pydantic-ai, so it accepts
    anything its ``Agent`` does -- a Pydantic model, a union, a tool
    output spec, or ``None`` for plain text.

    With no ``callback`` the query runs synchronously and its output is
    returned.  With a ``callback`` the query runs in the background and
    the callback is invoked as ``callback(output, AgentRunInfo)`` on the
    worker thread; the output is ``None`` when the run failed and the
    error is on the run info.
    """
    if callback is None:
        output, _info = _run_sync(_query(agent_id, prompt, output_type))
        return output
    thread = threading.Thread(
        target=_report,
        args=(agent_id, prompt, output_type, callback),
        daemon=True,
        name=f"agent-query-{agent_id}",
    )
    thread.start()
    return None
