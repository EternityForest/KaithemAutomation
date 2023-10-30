#!/usr/bin/python3
# Copyright Daniel Dunn 2013-2015
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
import sys

from kaithem import __version__ 
from . import config

__version_info__ = __version__.__version_info__
__version__ = __version__.__version__



def initialize():
    from . import tweaks  # noqa: F401
    from . import logconfig  # noqa: F401
    # config needs to be available before init for overrides
    # but it can't be initialized until after pathsetup which may
    config.initialize()

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
    from kaithem.src.scullery import messagebus
    from . import statemachines  # noqa: F401
    from . import auth  # noqa: F401
    from . import pages
    import iot_devices.host

    from . import config as cfg
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
    from . import scheduling  # noqa: F401
    from . import plugin_system  # noqa: F401
    from . import signalhandlers  # noqa: F401
    from . import webapproot  # noqa: F401
    from . import chandler  # noqa: F401

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
    devices.init_devices()
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
            logger.info("setting process title")
        except Exception:
            logger.warning("error setting process title")


def start_server():
    from . import webapproot
    webapproot.startServer()
