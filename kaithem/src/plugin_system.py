# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import importlib
import logging
import os
import threading
import time
import traceback

from . import messagebus, pathsetup

logger = logging.getLogger("system")
logger.setLevel(logging.INFO)

plugins = {}
evs: list[threading.Event] = []


def import_in_thread(m):
    e = threading.Event()
    e.set()
    evs.append(e)

    def f():
        try:
            t = time.monotonic()
            plugins[m] = importlib.import_module(m)
            logger.info(f"Loaded plugin {m} in {round((time.monotonic()-t) * 1000,2)}ms")
        except Exception:
            logger.exception("Error loading plugin " + m)
            messagebus.post_message(
                "/system/notifications/errors",
                "Error loading plugin " + m + "\n" + traceback.format_exc(),
            )
        e.clear()

    threading.Thread(target=f, daemon=True, name=f"nostartstoplog.importer.{m}").start()


def load_plugins():
    try:
        for i in os.listdir(pathsetup.startupPluginsPath):
            if "." not in i or i.endswith(".py"):
                import_in_thread(i)

        for i in range(240000):
            time.sleep(0.001)
            all_true = True
            try:
                for i in evs:
                    if i.is_set():
                        all_true = False
            except Exception:
                pass

            if all_true:
                return

    except Exception:
        messagebus.post_message("/system/notifications/errors", "Error loading plugins")
        logger.exception("Error loading plugins")
