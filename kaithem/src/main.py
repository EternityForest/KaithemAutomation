#!/usr/bin/python3
# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import logging
import os
import sys

from kaithem import __version__
from . import config
from typing import Dict, Any, Optional


__version_info__ = __version__.__version_info__
__version__ = __version__.__version__


def initialize(cfg: Optional[Dict[str, Any]] = None):
    "Config priority is default, then cfg param, then cmd line cfg file as highest priority"
    from . import tweaks  # noqa: F401
    from . import logconfig  # noqa: F401

    # config needs to be available before init for overrides
    # but it can't be initialized until after pathsetup which may
    config.initialize(cfg)

    from . import geolocation

    geolocation.use_api_if_needed()

    # must load AFTER config init
    from . import directories

    # Enable importing stuff directly from ./thirdparty,
    # Since we include lots of dependancies that would normally be provided by the system.
    # This must be done before CherryPy
    from . import pathsetup  # noqa: F401

    # Thhese happpen early so we cab start logging stuff soon
    from . import messagelogging  # noqa: F401
    from . import pylogginghandler  # noqa: F401

    from . import notifications  # noqa: F401

    from . import workers
    from . import selftest  # noqa: F401
    from . import devices  # noqa: F401
    from scullery import messagebus
    from scullery import statemachines  # noqa: F401
    from . import auth  # noqa: F401
    from . import pages
    import iot_devices.host

    from . import config as cfg
    from . import gis  # noqa: F401
    from . import sound  # noqa: F401
    from . import tagpoints  # noqa: F401
    from . import builtintags  # noqa: F401
    from . import kaithemobj  # noqa: F401
    from . import wifimanager  # noqa: F401
    from . import rtmidimanager  # noqa: F401
    from . import logviewer  # noqa: F401
    from . import weblogin  # noqa: F401
    from . import ManageUsers  # noqa: F401
    from . import newevt  # noqa: F401
    from . import persist  # noqa: F401
    from . import modules  # noqa: F401
    from . import modules_interface  # noqa: F401
    from . import settings  # noqa: F401
    from . import usrpages  # noqa: F401
    from . import systasks  # noqa: F401
    from . import widgets  # noqa: F401
    from . import alerts  # noqa: F401
    from . import tag_errors  # noqa: F401
    from scullery import scheduling  # noqa: F401
    from . import plugin_system  # noqa: F401
    from . import signalhandlers  # noqa: F401
    from . import webapproot  # noqa: F401
    from . import chandler  # noqa: F401

    def handle_error(f):
        # If we can, try to send the exception back whence it came
        try:
            from . import newevt
            import traceback

            newevt.eventsByModuleName[f.__module__]._handle_exception()
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
