# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import importlib
import importlib.machinery
import importlib.util
import logging
import os
import threading
import time
import traceback

import structlog

from . import directories, messagebus, pathsetup

logger = structlog.get_logger(__name__)
logger.setLevel(logging.INFO)

plugins = {}
evs: list[threading.Event] = []


def import_in_thread(m: str | importlib.machinery.ModuleSpec):
    e = threading.Event()
    e.set()
    evs.append(e)

    def f():
        try:
            t = time.monotonic()

            if isinstance(m, str):
                plugins[m] = importlib.import_module(m)

            else:
                # creates a new module based on spec
                foo = importlib.util.module_from_spec(m)

                # executes the module in its own namespace
                # when a module is imported or reloaded.
                assert m.loader
                m.loader.exec_module(foo)
                plugins[m.name] = foo

            logger.info(
                f"Loaded plugin {m} in {round((time.monotonic()-t) * 1000,2)}ms"
            )
        except Exception:
            logger.exception("Error loading plugin {m}")
            messagebus.post_message(
                "/system/notifications/errors",
                "Error loading plugin {m}\n" + traceback.format_exc(),
            )
        e.clear()

    threading.Thread(
        target=f, daemon=True, name=f"nostartstoplog.importer.{m}"
    ).start()


def load_plugins():
    try:
        for i in os.listdir(pathsetup.startupPluginsPath):
            if ("." not in i or i.endswith(".py")) and "__" not in i:
                # Very important to use the full name, not just add it to path,
                # or it would not know that it was the same module we might
                # import elsewhere
                import_in_thread("kaithem.src.plugins." + i)

        # core before user plugins
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
                break

    except Exception:
        messagebus.post_message(
            "/system/notifications/errors", "Error loading plugins"
        )
        logger.exception("Error loading plugins")


def load_user_plugins():
    try:
        usr = os.path.join(directories.vardir, "plugins")
        try:
            os.makedirs(usr, exist_ok=True)
        except Exception:
            pass

        if os.path.isdir(usr):
            for i in os.listdir(usr):
                if "." not in i and "__" not in i:
                    p = os.path.join(usr, i)
                    try:
                        spec = importlib.util.spec_from_file_location(
                            f"kaithem_usr_plugins.{i}",
                            os.path.join(p, "__init__.py"),
                            submodule_search_locations=[p],
                        )
                        assert spec
                        import_in_thread(spec)
                    except Exception:
                        logger.exception("Error in user plugin")

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
        messagebus.post_message(
            "/system/notifications/errors", "Error loading plugins"
        )
        logger.exception("Error loading plugins")
