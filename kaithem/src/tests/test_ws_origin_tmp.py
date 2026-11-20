# SPDX-License-Identifier: GPL-3.0-or-later
"""Temporary diagnostic: spy on the plugin's require from a real ws handler."""

from __future__ import annotations

import asyncio
import sys

import quart

from kaithem.src import pages

te = None
for _name, _mod in list(sys.modules.items()):
    if _name.endswith("CorePluginTextEditor") and hasattr(_mod, "require"):
        te = _mod
        break
assert te is not None, "plugin module not found"

from .helpers import make_client


async def test_spy_require(monkeypatch):
    calls = []
    real_require = te.require

    def spy(permission):
        info = {"permission": permission}
        try:
            info["scope_scheme"] = quart.websocket.scope.get("scheme")
        except Exception as e:  # noqa: BLE001
            info["scope_scheme_err"] = repr(e)
        try:
            info["host_url"] = quart.request.host_url
            info["origin"] = quart.request.headers.get("Origin", "")
        except Exception as e:  # noqa: BLE001
            info["req_err"] = repr(e)
        calls.append(info)
        return real_require(permission)

    monkeypatch.setattr(te, "require", spy)
    # Also log any noCrossSite invocation.
    real_ncs = pages.noCrossSite
    ncs_calls = []

    def ncs_spy(asgi=None):
        try:
            ncs_calls.append(
                {
                    "scheme": quart.websocket.scope.get("scheme"),
                    "host_url": quart.request.host_url,
                }
            )
        except Exception as e:  # noqa: BLE001
            ncs_calls.append({"err": repr(e)})
        return real_ncs(asgi)

    monkeypatch.setattr(pages, "noCrossSite", ncs_spy)

    client = await make_client()
    calls.clear()
    ncs_calls.clear()

    async def _try(headers):
        try:
            async with client.websocket(
                "/text-editor-plugin/ws",
                query_string={"workspace": "/dev/shm/kaithem_tests"},
                headers=headers,
            ) as ws:
                await ws.send_json({"type": "unwatch", "path": "x"})
                return "connected"
        except Exception as e:  # noqa: BLE001
            return f"failed: {type(e).__name__}: {e}"

    r1 = await asyncio.wait_for(_try({}), 10)
    r2 = await asyncio.wait_for(_try({"Origin": "http://localhost"}), 10)
    print(f"no-origin -> {r1}")  # noqa: T201
    print(f"origin -> {r2}")  # noqa: T201
    print(f"require calls: {calls}")  # noqa: T201
    print(f"noCrossSite calls: {ncs_calls}")  # noqa: T201
