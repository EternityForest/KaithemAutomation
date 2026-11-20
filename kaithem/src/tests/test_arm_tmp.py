# SPDX-License-Identifier: GPL-3.0-or-later
"""Temporary: does armed() stay True after arm()? (deleted after)"""

from __future__ import annotations

import asyncio

from kaithem.src import config
from kaithem.src.plugins.CorePluginTextEditor import self_debug


async def test_arm_stays_armed(monkeypatch):
    monkeypatch.setitem(config.config, "self_debug", True)
    proxy = self_debug.get_proxy()
    print("armed before:", proxy.armed)
    port = await asyncio.wait_for(asyncio.to_thread(proxy.arm), 40)
    print("arm() OK port:", port)
    for i in range(6):
        await asyncio.sleep(1)
        print(f"t+{i + 1}s armed:", proxy.armed)
