#!/usr/bin/python3
# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import importlib
import logging
import os
import sys
import threading
import time
from typing import Any, Dict, Optional

from kaithem import __version__

from . import config

__version_info__ = __version__.__version_info__
__version__ = __version__.__version__


def import_in_thread(m):
    def f():
        importlib.import_module(m)

    threading.Thread(target=f, daemon=True, name=f"nostartstoplog.importer.{m}").start()


def initialize(cfg: Optional[Dict[str, Any]] = None):
    "Config priority is default, then cfg param, then cmd line cfg file as highest priority"

    from . import (
        logconfig,  # noqa: F401
        tweaks,  # noqa: F401
    )

    # Paralellize slow imports
    for i in [
        "tornado",
        "sqlite3",
        "pytz",
        "mako",
        "mako.lookup",
        "jinja2",
        "tornado.websocket",
        "tornado.routing",
        "typeguard",
        "multiprocessing",
        "glob",
        "beartype",
        "pygments",
        "numpy",
        "zeroconf",
        "msgpack",
        "cherrypy",
        "dateutil.rrule",
    ]:
        import_in_thread(i)
    time.sleep(0.1)

    # config needs to be available before init for overrides
    # but it can't be initialized until after pathsetup which may
    config.initialize(cfg)

    from . import geolocation

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
        builtintags,  # noqa: F401
        chandler,  # noqa: F401
        devices,  # noqa: F401
        directories,
        gis,  # noqa: F401
        kaithemobj,  # noqa: F401
        logviewer,  # noqa: F401
        messagelogging,  # noqa: F401
        modules,  # noqa: F401
        modules_interface,  # noqa: F401
        newevt,  # noqa: F401
        notifications,  # noqa: F401
        persist,  # noqa: F401
        plugin_system,  # noqa: F401
        pylogginghandler,  # noqa: F401
        rtmidimanager,  # noqa: F401
        selftest,  # noqa: F401
        settings,  # noqa: F401
        signalhandlers,  # noqa: F401
        systasks,  # noqa: F401
        tag_errors,  # noqa: F401
        tagpoints,  # noqa: F401
        usrpages,  # noqa: F401
        webapproot,  # noqa: F401
        weblogin,  # noqa: F401
        widgets,  # noqa: F401
        wifimanager,  # noqa: F401
        workers,
    )
    from . import config as cfg

    def handle_error(f):
        # If we can, try to send the exception back whence it came
        try:
            import traceback

            from . import newevt

            if f.__module__ in newevt.eventsByModuleName:
                newevt.eventsByModuleName[f.__module__]._handle_exception()
            else:
                print(traceback.format_exc())

        except Exception:
            print(traceback.format_exc())

        try:
            if hasattr(f, "__name__") and hasattr(f, "__module__"):
                logger.exception("Exception in scheduled function " + f.__name__ + " of module " + f.__module__)
        except Exception:
            logger.exception(f"Exception in scheduled function {repr(f)}")

    def handle_first_error(f):
        "Callback to deal with the first error from any given event"
        m = f.__module__
        messagebus.post_message(
            "/system/notifications/errors",
            "Problem in scheduled event function: " + repr(f) + " in module: " + m + ", check logs for more info.",
        )

    scheduling.handle_first_error = handle_first_error

    scheduling.function_error_hooks.append(handle_error)

    logger = logging.getLogger("system")
    logger.setLevel(logging.INFO)

    os.makedirs(os.path.join(directories.vardir, "static"), exist_ok=True)

    auth.initializeAuthentication()
    logger.info("Loaded auth data")

    tagpoints.loadAllConfiguredTags(os.path.join(directories.vardir, "tags"))

    if cfg.argcmd.initialpackagesetup:
        auth.dumpDatabase()
        logger.info("Kaithem users set up. Now exiting.")
        import cherrypy

        cherrypy.engine.exit()
        sys.exit()

    builtintags.create()
    plugin_system.load_plugins()

    # Devices is started with the additional resource types system
    # devices.init_devices()
    rtmidimanager.init()

    # Load all modules from the active modules directory
    modules.initModules()
    logger.info("Loaded modules")

    workers.do(systasks.doUPnP)

    def loadJackMixer():
        from . import jackmixer  # noqa: F401

    workers.do(loadJackMixer)

    if config.config["change-process-title"]:
        try:
            import setproctitle

            setproctitle.setproctitle("kaithem")
        except Exception:
            logger.warning("error setting process title")


def start_server():
    from . import webapproot

    webapproot.startServer()
