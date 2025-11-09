#!/usr/bin/python3
# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later
import gc
import importlib
import logging
import os
import sys
import threading
import time
from typing import Any

import structlog
import structlog.dev

from . import config as config_module

structlog.stdlib.recreate_defaults()

shared_processors = [
    # Processors that have nothing to do with output,
    # e.g., add timestamps or log level names.
]

if True or sys.stderr.isatty():
    # Pretty printing when we run in a terminal session.
    # Automatically prints pretty tracebacks when "rich" is installed
    processors = shared_processors + [
        structlog.dev.ConsoleRenderer(
            exception_formatter=structlog.dev.plain_traceback
        ),
    ]
else:
    # Print JSON when we run, e.g., in a Docker container.
    # Also print structured tracebacks.
    processors = shared_processors + [
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(),
    ]


structlog.configure(
    processors=structlog.get_config()["processors"][:-1]
    + shared_processors
    + processors
)


def import_in_thread(m):
    def f():
        start_time = time.time()
        importlib.import_module(m)
        taken = round(time.time() - start_time, 2)
        if taken > 5:
            print(f"Loading {m} took {taken}s")

    threading.Thread(
        target=f, daemon=True, name=f"nostartstoplog.importer.{m}"
    ).start()


def initialize(config: dict[str, Any] | None = None):
    "Config priority is default, then cfg param, then cmd line cfg file as highest priority"

    start_time = time.time()

    from . import (
        logconfig,  # noqa: F401
        tweaks,  # noqa: F401
    )

    # Paralellize slow imports
    for i in [
        "sqlite3",
        "pytz",
        "mako",
        "mako.lookup",
        "jinja2",
        "multiprocessing",
        "glob",
        "pygments",
        "numpy",
        "zeroconf",
        "msgpack",
        "dateutil.rrule",
        "psutil",
        "kaithem.src.jackmanager",
    ]:
        import_in_thread(i)
    time.sleep(0.1)

    # config needs to be available before init for overrides
    # but it can't be initialized until after pathsetup which may
    config_module.initialize(config)
    from . import (
        geolocation,
    )

    geolocation.use_api_if_needed()

    # must load AFTER config init
    from scullery import (
        messagebus,
        scheduling,  # noqa: F401
        statemachines,  # noqa: F401
    )

    from . import pathsetup  # noqa

    pathsetup.setupPath()

    from . import sound

    sound.init()

    # Enable importing stuff directly from ./thirdparty,
    # Since we include lots of dependancies that would normally be provided by the system.
    # This must be done before CherryPy
    # Thhese happpen early so we cab start logging stuff soon
    from . import (
        ManageUsers,  # noqa: F401
        alerts,  # noqa: F401
        auth,  # noqa: F401
        chandler,  # noqa: F401
        devices,  # noqa: F401
        directories,
        gis,  # noqa: F401
        logviewer,  # noqa: F401
        messagelogging,  # noqa: F401
        module_object_inspector,  # noqa: F401
        modules,  # noqa: F401
        notifications,  # noqa: F401
        plugin_system,  # noqa: F401
        settings,  # noqa: F401
        signalhandlers,  # noqa: F401
        systasks,  # noqa: F401
        tag_errors,  # noqa: F401
        tagpoints,  # noqa: F401
        webapproot,  # noqa: F401
        weblogin,  # noqa: F401
        widgets,  # noqa: F401
    )
    from .chandler import resource_type  # noqa

    def handle_error(f):
        # If we can, try to send the exception back whence it came
        try:
            import traceback

            from .plugins import CorePluginEventResources

            if f.__module__ in CorePluginEventResources.eventsByModuleName:
                CorePluginEventResources.eventsByModuleName[
                    f.__module__
                ].handle_exception()
            else:
                print(traceback.format_exc())

        except Exception:
            print(traceback.format_exc())

        try:
            if hasattr(f, "__name__") and hasattr(f, "__module__"):
                logger.exception(
                    "Exception in scheduled function "
                    + f.__name__
                    + " of module "
                    + f.__module__
                )
        except Exception:
            logger.exception(f"Exception in scheduled function {repr(f)}")

    def handle_first_error(f):
        "Callback to deal with the first error from any given event"
        m = f.__module__
        messagebus.post_message(
            "/system/notifications/errors",
            "Problem in scheduled event function: "
            + repr(f)
            + " in module: "
            + m
            + ", check logs for more info.",
        )

    scheduling.handle_first_error = handle_first_error

    scheduling.function_error_hooks.append(handle_error)

    logger = structlog.get_logger(__name__)
    logger.setLevel(logging.INFO)

    os.makedirs(os.path.join(directories.vardir, "static"), exist_ok=True)

    auth.initializeAuthentication()
    logger.info("Loaded auth data")

    plugin_system.load_plugins()
    plugin_system.load_user_plugins()

    # Load all modules from the active modules directory
    modules.initModules()
    logger.info("Loaded modules")

    try:
        import setproctitle

        try:
            title = config_module.config.get("process_title", "kaithem")
        except Exception:
            logging.exception("error getting process title")
            title = "kaithem"

        setproctitle.setproctitle(title)
    except Exception:
        logger.exception("error setting process title")

    taken = round(time.time() - start_time, 2)
    logger.info(f"initialize() took {taken}s")


def start_server():
    from . import webapproot

    webapproot.startServer()
    gc.collect()
    gc.collect()
    time.sleep(0.1)
    gc.collect()
    gc.collect()
