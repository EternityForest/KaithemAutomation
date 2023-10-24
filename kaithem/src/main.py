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

from typing import Any, Dict

from . import tweaks  # noqa: F401
from . import logconfig  # noqa: F401

# Enable importing stuff directly from ./thirdparty,
# Since we include lots of dependancies that would normally be provided by the system.
# This must be done before CherryPy
from . import pathsetup  # noqa: F401
import os
import sys

import cherrypy
import tornado
import tornado.httpserver
import tornado.wsgi
import tornado.web
from tornado.routing import RuleRouter, Rule, PathMatches, AnyMatches, Matcher

import logging

# Thhese happpen early so we cab start logging stuff soon
from . import messagelogging  # noqa: F401
from . import pylogginghandler  # noqa: F401


from . import notifications  # noqa: F401

from . import wsgi_adapter

import atexit
from . import util, workers
from . import selftest  # noqa: F401
from . import devices  # noqa: F401
from scullery import messagebus
from . import statemachines  # noqa: F401
from . import auth  # noqa: F401
from . import directories
from . import pages
import iot_devices.host
from .config import config
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
from . import version_info  # noqa: F401
from . import chandler  # noqa: F401
from . import tileserver



logger = logging.getLogger("system")
logger.setLevel(logging.INFO)

cherrypy.engine.subscribe("stop", iot_devices.host.app_exit_cleanup)


__version__ = version_info.__version__
__version_info__ = version_info.__version_info__


os.makedirs(os.path.join(directories.vardir, "static"), exist_ok=True)

auth.initializeAuthentication()
logger.info("Loaded auth data")

tagpoints.loadAllConfiguredTags(os.path.join(directories.vardir, "tags"))

if cfg.argcmd.initialpackagesetup:
    auth.dumpDatabase()
    logger.info("Kaithem users set up. Now exiting.")
    cherrypy.engine.exit()
    sys.exit()

builtintags.create()
plugin_system.load_plugins()
devices.init_devices()
cherrypy.engine.subscribe("stop", devices.closeAll)
rtmidimanager.init()

# Load all modules from the active modules directory
modules.initModules()
logger.info("Loaded modules")

workers.do(systasks.doUPnP)


def loadJackMixer():
    from . import jackmixer  # noqa: F401


workers.do(loadJackMixer)

if config["change-process-title"]:
    try:
        import setproctitle

        setproctitle.setproctitle("kaithem")
        logger.info("setting process title")
    except Exception:
        logger.warning("error setting process title")


def webRoot():
    # We don't want Cherrypy writing temp files for no reason
    cherrypy._cpreqbody.Part.maxrambytes = 64 * 1024

    logger.info("Loaded core python code")
    from . import config as cfgmodule

    if not config["host"] == "default":
        bindto = config["host"]
    else:
        if config["local-access-only"]:
            bindto = "127.0.0.1"
        else:
            bindto = "::"

    mode = int(cfgmodule.argcmd.nosecurity) if cfgmodule.argcmd.nosecurity else None
    # limit nosecurity to localhost
    if mode == 1:
        bindto = "127.0.0.1"

    logger.info("Ports are free")

    sys.modules["kaithem"] = sys.modules["__main__"]

    def save():
        if config["save-before-shutdown"]:
            messagebus.postMessage(
                "/system/notifications/important/", "System saving before shutting down"
            )
            util.SaveAllState()

    # let the user choose to have the server save everything before a shutdown
    if config["save-before-shutdown"]:
        atexit.register(save)
        cherrypy.engine.subscribe("exit", save)

    # There are lots of other objects ad classes represeting subfolders of the website
    #  so we attatch them
    root = webapproot.root

    site_config = {
        "tools.encode.on": True,
        "tools.encode.encoding": "utf-8",
        "tools.decode.on": True,
        "tools.decode.encoding": "utf-8",
        "request.error_response": webapproot.cpexception,
        "log.screen": config["cherrypy-log-stdout"],
        "engine.autoreload.on": False,
    }

    cnf = webapproot.conf

    def addheader(*args, **kwargs):
        "This function's only purpose is to tell the browser to cache requests for an hour"
        cherrypy.response.headers["Cache-Control"] = "max-age=28800"
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

        # del cherrypy.response.headers['Expires']

    def pageloadnotify(*args, **kwargs):
        systasks.aPageJustLoaded()

    cherrypy.config.update(site_config)

    cherrypy.tools.pageloadnotify = cherrypy.Tool("on_start_resource", pageloadnotify)
    cherrypy.config["tools.pageloadnotify.on"] = True

    cherrypy.tools.addheader = cherrypy.Tool("before_finalize", addheader)

    if hasattr(cherrypy.engine, "signal_handler"):
        del cherrypy.engine.signal_handler.handlers["SIGUSR1"]
        cherrypy.engine.signal_handler.subscribe()

    wsgiapp = cherrypy.tree.mount(root, config=cnf)

    messagebus.postMessage("/system/startup", "System Initialized")
    messagebus.postMessage("/system/notifications/important", "System Initialized")

    cherrypy.server.unsubscribe()
    cherrypy.config.update({"environment": "embedded"})
    cherrypy.engine.signals.subscribe()

    cherrypy.engine.start()

    wsapp = tornado.web.Application(
        [
            (r"/widgets/ws", widgets.makeTornadoSocket()),
            (r"/widgets/wsraw", widgets.makeRawTornadoSocket()),
        ]
    )

    class KAuthMatcher(Matcher):
        def __init__(self, path, permission) -> None:
            super().__init__()
            self.pm = PathMatches(path)
            self.perm = permission

        def match(self, request) -> Dict[str, Any] | None:
            if self.pm.match(request) is not None:
                if pages.canUserDoThis(self.perm, pages.getAcessingUser(request)):
                    return {}

            return None

    rules = [
        Rule(PathMatches("/widgets/ws.*"), wsapp),
        Rule(
            PathMatches("/maptiles/tile/.*"),
            tornado.web.Application([("/maptiles/tile/.*", tileserver.MainHandler)]),
        ),
    ]

    from . import tableview

    rules.append(
        Rule(
            AnyMatches(),
            tornado.web.Application(
                [
                    (
                        KAuthMatcher("/database.*", "/admin/settings.edit"),
                        wsgi_adapter.WSGIHandler,
                        {"wsgi_application": tableview.get_app()},
                    ),
                    (
                        PathMatches("/database.*"),
                        tornado.web.RedirectHandler,
                        {"url": "/login", 'permanent':False},
                    ),
                    (
                        AnyMatches(),
                        wsgi_adapter.WSGIHandler,
                        {"wsgi_application": wsgiapp},
                    ),
                ]
            ),
        )
    )

    if config["esphome-config-dir"]:
        from . import esphome_dash

        rules.extend(
            [
                Rule(
                    KAuthMatcher("/esphome.*", "/admin/settings.edit"),
                    esphome_dash.start_web_server(),
                ),
                Rule(
                    PathMatches("/esphome.*"),
                    tornado.web.RedirectHandler,
                    {"url": "/login",'permanent':False},
                ),
            ]
        )
    router = RuleRouter(rules)

    http_server = tornado.httpserver.HTTPServer(router)
    # Legacy config comptibility
    http_server.listen(config["http-port"], bindto if not bindto=='::' else None)

    if config["https-port"]:
        if not os.path.exists(os.path.join(directories.ssldir, "certificate.key")):
            cherrypy.server.unsubscribe()
            messagebus.postMessage(
                "/system/notifications",
                "You do not have an SSL certificate set up. HTTPS is not enabled.",
            )
        else:
            https_server = tornado.httpserver.HTTPServer(
                router,
                ssl_options={
                    "certfile": os.path.join(directories.ssldir, "certificate.cert"),
                    "keyfile": os.path.join(directories.ssldir, "certificate.key"),
                },
            )
            https_server.listen(config["https-port"], bindto)

    # Publish to the CherryPy engine as if
    # we were using its mainloop
    tornado.ioloop.PeriodicCallback(
        lambda: cherrypy.engine.publish("main"), 100
    ).start()
    tornado.ioloop.IOLoop.instance().start()

    logger.info("Cherrypy engine stopped")


webRoot()
