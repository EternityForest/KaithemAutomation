# SPDX-License-Identifier: GPL-3.0-or-later
"""Temporary verification of self-debug route gating (deleted after run)."""

from __future__ import annotations

import pytest

from kaithem.src import config, quart_app
from kaithem.src.plugins.CorePluginTextEditor import self_debug

from .helpers import make_client


async def test_self_debug_route_disabled(monkeypatch):
    monkeypatch.setitem(config.config, "self_debug", False)
    client = await make_client()
    r = await client.get("/text-editor-plugin/self-debug")
    assert r.status_code == 404


async def test_self_debug_route_guest_redirects(monkeypatch):
    monkeypatch.setitem(config.config, "self_debug", False)
    client = quart_app.app.test_client(use_cookies=True)
    r = await client.get("/text-editor-plugin/self-debug")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


async def test_self_debug_ws_disabled(monkeypatch):
    monkeypatch.setitem(config.config, "self_debug", False)
    client = await make_client()
    with pytest.raises(Exception):
        async with client.websocket("/text-editor-plugin/self-debug-ws") as ws:
            await ws.receive()


async def test_self_debug_ws_not_armed(monkeypatch):
    # Flag on but debugpy never armed: must refuse without touching debugpy.
    monkeypatch.setitem(config.config, "self_debug", True)
    assert not self_debug.get_proxy().armed
    client = await make_client()
    with pytest.raises(Exception):
        async with client.websocket("/text-editor-plugin/self-debug-ws") as ws:
            await ws.receive()
