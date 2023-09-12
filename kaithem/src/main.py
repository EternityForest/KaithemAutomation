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

from types import MethodType
from typing import Any, Dict, Optional

from . import tweaks
from . import logconfig

# Enable importing stuff directly from ./thirdparty,
# Since we include lots of dependancies that would normally be provided by the system.
# This must be done before CherryPy
from . import pathsetup
import os
import sys

import cherrypy
import logging


# Enable logging when threads start and stop.
tweaks.installThreadLogging()

# Thhese happpen early so we cab start logging stuff soon
from . import messagelogging
from . import pylogginghandler


from . import notifications


import getpass
import atexit
import signal
import mimetypes
import time
import traceback
from . import util, workers
from . import selftest
from . import devices
import importlib
from scullery import messagebus
from . import statemachines
from . import auth
from . import directories
from . import pages
import iot_devices.host
from .config import config
from . import config as cfg
import mako.exceptions
from . import tagpoints
from . import builtintags
from . import kaithemobj
from . import wifimanager
from . import tagpoints
from . import rtmidimanager
from . import logviewer
from . import weblogin
from . import ManageUsers
from . import newevt
from . import persist
from . import modules
from . import modules_interface
from . import settings
from . import usrpages
from . import systasks
from . import widgets
from . import alerts
from . import tag_errors
from . import scheduling
from . import plugin_system
from . import signalhandlers
from . import webapproot
from . import version_info
from . import chandler


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
    util.drop_perms(config["run-as-user"], config["run-as-group"])
    auth.dumpDatabase()
    logger.info(
        "Kaithem users set up. Now exiting(May take a few seconds. You may start the service manually or via systemd/init"
    )
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
    from . import jackmixer
workers.do(loadJackMixer)

# from . import wifimanager


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

    if config["change-process-title"]:
        try:
            import setproctitle

            setproctitle.setproctitle("kaithem")
            logger.info("setting process title")
        except Exception:
            logger.warning("error setting process title")

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

    # There are lots of other objects ad classes represeting subfolders of the website so we attatch them
    root = webapproot.root

    if not os.path.abspath(__file__).startswith("/usr/bin"):
        sdn = os.path.join(
            os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src"
        )
        ddn = os.path.join(
            os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "data"
        )
    else:
        sdn = "/usr/lib/kaithem/src"
        ddn = "/usr/share/kaithem"

    def allow_upload(*args, **kwargs):
        # Only do the callback if needed. Assume it's really big if no header.
        if (
            int(cherrypy.request.headers.get("Content-Length", 2**32))
            > cherrypy.request.body.maxbytes
        ):
            cherrypy.request.body.maxbytes = cherrypy.request.config[
                "tools.allow_upload.f"
            ]()

    cherrypy.tools.allow_upload = cherrypy.Tool("before_request_body", allow_upload)

    site_config = {
        "request.body.maxbytes": 64 * 1024,
        "tools.encode.on": True,
        "tools.encode.encoding": "utf-8",
        "tools.decode.on": True,
        "tools.decode.encoding": "utf-8",
        "request.error_response": webapproot.cpexception,
        "log.screen": config["cherrypy-log-stdout"],
        "engine.autoreload.on": False,
        "tools.allow_upload.on": True,
        "tools.allow_upload.f": lambda: auth.getUserLimit(
            pages.getAcessingUser(), "web.maxbytes"
        )
        or 64 * 1024,
    }

    cnf = {
        "/static": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": os.path.join(ddn, "static"),
            "tools.sessions.on": False,
            "tools.addheader.on": True,
            "tools.expires.on": True,
            "tools.expires.secs": 3600 + 48,  # expire in 48 hours
        },
        "/static/js": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": os.path.join(sdn, "js"),
            "tools.sessions.on": False,
            "tools.addheader.on": True,
        },
        "/static/vue": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": os.path.join(sdn, "vue"),
            "tools.sessions.on": False,
            "tools.addheader.on": True,
        },
        "/static/css": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": os.path.join(sdn, "css"),
            "tools.sessions.on": False,
            "tools.addheader.on": True,
        },
        "/static/docs": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": os.path.join(sdn, "docs"),
            "tools.sessions.on": False,
            "tools.addheader.on": True,
        },
        "/static/zip": {
            "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
            "tools.addheader.on": True,
        },
        "/pages": {
            "tools.allow_upload.on": True,
            "tools.allow_upload.f": lambda: auth.getUserLimit(
                pages.getAcessingUser(), "web.maxbytes"
            )
            or 64 * 1024,
            "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
        },
    }

    if not config["favicon-png"] == "default":
        cnf["/favicon.png"] = {
            "tools.staticfile.on": True,
            "tools.staticfile.filename": os.path.join(
                directories.datadir, "static", config["favicon-png"]
            ),
            "tools.expires.on": True,
            "tools.expires.secs": 3600,  # expire in an hour
        }

    if not config["favicon-ico"] == "default":
        cnf["/favicon.ico"] = {
            "tools.staticfile.on": True,
            "tools.staticfile.filename": os.path.join(
                directories.datadir, "static", config["favicon-ico"]
            ),
            "tools.expires.on": True,
            "tools.expires.secs": 3600,  # expire in an hour
        }

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



    # Unlike other shm stuff that only gets used after startup, this
    # Can be used both before and after we are fully loaded.
    # So we need to hand off everything to the user we will actually run as.

    # This is also useful for when someone directly modifies config
    # Over SSH and we want to adopt those changes to the kaithem usr.

    # It's even useful if we ever change the user for some reason.

    # We only do this if we start as root though.

    if not config["run-as-user"] == "root" and getpass.getuser() == "root":
        try:
            d = "/dev/shm/kaithem_pyx_" + config["run-as-user"]
            directories.rchown(d, config["run-as-user"])
            directories.rchown(directories.vardir, config["run-as-user"])
            directories.rchown(directories.logdir, config["run-as-user"])
            # Might as well own our own SSL dir, that way we can change certs via the webUI.
            directories.rchown(directories.ssldir, config["run-as-user"])
            directories.rchown(directories.usersdir, config["run-as-user"])
            directories.rchown(directories.regdir, config["run-as-user"])
        except Exception:
            logger.exception("This is normal on non-unix")

    # If configured that way on unix, check if we are root and drop root.
    util.drop_perms(config["run-as-user"], config["run-as-group"])
    pylogginghandler.onUserChanged()
    messagebus.postMessage("/system/startup", "System Initialized")
    messagebus.postMessage("/system/notifications/important", "System Initialized")


    cherrypy.server.unsubscribe()
    cherrypy.config.update({"environment": "embedded"})
    # cherrypy.engine.signals.subscribe()

    cherrypy.engine.start()

    import tornado
    import tornado.httpserver
    import tornado.wsgi
    import tornado.web
    from tornado.routing import RuleRouter, Rule, PathMatches, AnyMatches, Matcher

    container = tornado.wsgi.WSGIContainer(wsgiapp)


    wsapp = tornado.web.Application(
        [
            (r"/widgets/ws", widgets.makeTornadoSocket()),
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
        Rule(PathMatches("/widgets/ws"), wsapp),
    ]

    rules.append(Rule(AnyMatches(), container))

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
                    {"url": "/login"},
                ),
            ]
        )
    router = RuleRouter(rules)

    http_server = tornado.httpserver.HTTPServer(router)
    http_server.listen(config["http-port"], bindto)

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
