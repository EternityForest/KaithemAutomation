# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the self-debug route and its websocket lifecycle.

The real debugger is never started here.  A stub proxy stands in for the
process-wide one, so these tests cover the ``self_debug`` gating and the
arm-on-connect / detach-on-disconnect contract the websocket handler
drives without touching debugpy.
"""

from __future__ import annotations

import asyncio

import pytest

from kaithem.src import config, quart_app
from kaithem.src.plugins.CorePluginTextEditor import self_debug

from .helpers import make_client


class _StubProxy:
    """Records the calls the websocket handler makes on the real proxy."""

    def __init__(self, busy: bool = False) -> None:
        self.armed = False
        self.busy = busy
        self.arm_calls = 0
        self.detach_calls = 0
        self.acquire_calls = 0
        self.release_calls = 0
        self.received: list[str] = []
        self.received_event = asyncio.Event()

    def arm(self) -> int:
        self.arm_calls += 1
        self.armed = True
        return 12345

    def detach(self) -> None:
        self.detach_calls += 1
        self.armed = False

    def acquire_browser(self, loop, queue) -> bool:
        self.acquire_calls += 1
        return not self.busy

    def release_browser(self) -> None:
        self.release_calls += 1

    def from_browser(self, text: str) -> None:
        self.received.append(text)
        self.received_event.set()


@pytest.fixture
def stub_proxy(monkeypatch):
    """Install a stub proxy and neutralise the debugpy main-thread tweak."""
    monkeypatch.setitem(config.config, "self_debug", True)
    stub = _StubProxy()
    monkeypatch.setattr(self_debug, "get_proxy", lambda: stub)
    monkeypatch.setattr(
        self_debug, "disable_main_thread_tracing", lambda _loop: None
    )
    return stub


async def test_self_debug_route_is_hidden_when_disabled(monkeypatch):
    monkeypatch.setitem(config.config, "self_debug", False)
    client = await make_client()
    response = await client.get("/text-editor-plugin/self-debug")
    assert response.status_code == 404


async def test_self_debug_route_redirects_guests_to_login(monkeypatch):
    monkeypatch.setitem(config.config, "self_debug", False)
    client = quart_app.app.test_client(use_cookies=True)
    response = await client.get("/text-editor-plugin/self-debug")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


async def test_self_debug_socket_refuses_when_disabled(monkeypatch):
    monkeypatch.setitem(config.config, "self_debug", False)
    client = await make_client()
    with pytest.raises(Exception):
        async with client.websocket("/text-editor-plugin/self-debug-ws") as ws:
            await ws.receive()


async def test_self_debug_socket_arms_on_connect_and_detaches(stub_proxy):
    client = await make_client()
    async with client.websocket("/text-editor-plugin/self-debug-ws") as ws:
        await ws.send('{"seq": 1, "type": "request", "command": "threads"}')
        # Wait until the handler has bridged the message, so the assertions
        # below do not race the server task.
        await asyncio.wait_for(stub_proxy.received_event.wait(), 5)

    # The link is armed on connect and fully torn down on disconnect, so the
    # next session can attach again.
    assert stub_proxy.arm_calls == 1
    assert stub_proxy.acquire_calls == 1
    assert stub_proxy.release_calls == 1
    assert stub_proxy.detach_calls == 1
    assert stub_proxy.received == [
        '{"seq": 1, "type": "request", "command": "threads"}'
    ]
    assert not stub_proxy.armed


async def test_self_debug_socket_refuses_a_second_browser(monkeypatch):
    # A second browser must be refused without arming or detaching, so it
    # cannot tear down the session the first browser is using.
    monkeypatch.setitem(config.config, "self_debug", True)
    stub = _StubProxy(busy=True)
    monkeypatch.setattr(self_debug, "get_proxy", lambda: stub)
    monkeypatch.setattr(
        self_debug, "disable_main_thread_tracing", lambda _loop: None
    )

    client = await make_client()
    with pytest.raises(Exception):
        async with client.websocket("/text-editor-plugin/self-debug-ws") as ws:
            await ws.receive()

    assert stub.acquire_calls == 1
    assert stub.arm_calls == 0
    assert stub.detach_calls == 0
    assert stub.release_calls == 0
