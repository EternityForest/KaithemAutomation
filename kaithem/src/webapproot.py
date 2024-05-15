# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import atexit
import json
import logging
import mimetypes
import os
import sys
import time
import traceback
from typing import Any, Dict

import cherrypy
import cherrypy._cpreqbody
import iot_devices
import mako
import mako.exceptions
import tornado
from cherrypy import _cperror
from cherrypy.lib.static import serve_file
from tornado.routing import AnyMatches, Matcher, PathMatches, Rule, RuleRouter

from kaithem.api import web as webapi
from kaithem.src.thirdparty import tornado_asgi_handler

from . import (
    ManageUsers,
    alerts,
    cliserver,
    devices,
    devices_interface,
    directories,
    logviewer,
    messagebus,
    messagelogging,
    module_actions,
    modules_interface,
    notifications,
    pages,
    settings,
    settings_overrides,
    systasks,
    tagpoints,
    # TODO we gotta stop depending on import side effects
    util,
    weblogin,
    widgets,
    wsgi_adapter,
)
from .chandler import web as cweb
from .config import config
from .plugins import CorePluginUserPageResources

logger = logging.getLogger("system")
logger.setLevel(logging.INFO)


cherrypy.engine.subscribe("stop", devices.closeAll)
cherrypy.engine.subscribe("stop", iot_devices.host.app_exit_cleanup)


class Errors:
    @cherrypy.expose
    def permissionerror(
        self,
    ):
        cherrypy.response.status = 403
        return pages.get_template("errors/permissionerror.html").render()

    @cherrypy.expose
    def alreadyexists(
        self,
    ):
        cherrypy.response.status = 400
        return pages.get_template("errors/alreadyexists.html").render()

    @cherrypy.expose
    def gosecure(
        self,
    ):
        cherrypy.response.status = 426
        return pages.get_template("errors/gosecure.html").render()

    @cherrypy.expose
    def loginerror(
        self,
    ):
        cherrypy.response.status = 400
        return pages.get_template("errors/loginerror.html").render()

    @cherrypy.expose
    def nofoldermoveerror(
        self,
    ):
        cherrypy.response.status = 400
        return pages.get_template("errors/nofoldermove.html").render()

    @cherrypy.expose
    def wrongmethod(
        self,
    ):
        cherrypy.response.status = 405
        return pages.get_template("errors/wrongmethod.html").render()

    @cherrypy.expose
    def error(
        self,
    ):
        cherrypy.response.status = 500
        return pages.get_template("errors/error.html").render(info="An Error Occurred")


def error_page(status, message, traceback, version):
    cherrypy.response.status = 500
    try:
        cherrypy.response.body = bytes(
            pages.get_template("errors/cperror.html").render(
                e=_cperror.format_exc(),
                mk=str(
                    mako.exceptions.html_error_template().render().decode(),
                ),
            ),
            "utf8",
        )
    except Exception:
        cherrypy.response.body = bytes(
            pages.get_template("errors/cperror.html").render(e=_cperror.format_exc(), mk=""),
            "utf8",
        )


@cherrypy.tools.register("before_error_response", priority=90)
def handle_error():
    cherrypy.response.status = 500
    cherrypy.response.body = [pages.get_template("errors/cperror.html").render(e=traceback.format_exc(), mk="").encode()]


def error_page_404(status, message, traceback, version):
    return pages.get_template("errors/e404.html").render()


# This class represents the "/" root of the web app
@cherrypy.config(**{"request.error_response": handle_error})
class webapproot:
    login = weblogin.LoginScreen()
    auth = ManageUsers.ManageAuthorization()
    modules = modules_interface.WebInterface()
    settings = settings.Settings()
    errors = Errors()
    pages = CorePluginUserPageResources.KaithemPage()
    logs = messagelogging.WebInterface()
    notifications = notifications.WI()
    syslog = logviewer.WebInterface()
    devices = devices_interface.WebDevices()
    chandler = cweb.Web()
    cli = cliserver.WebAPI()

    @cherrypy.expose
    def favicon_ico(self):
        cherrypy.response.headers["Cache-Control"] = "max-age=3600"
        fn = os.path.join(directories.datadir, "static", settings_overrides.get_val("core/favicon_ico"))
        if not os.path.exists(fn):
            fn = os.path.join(directories.vardir, settings_overrides.get_val("core/favicon_ico"))
        return serve_file(fn)

    @cherrypy.expose
    def apiwidget(self, widgetid, js_name):
        pages.require("enumerate_endpoints")
        return widgets.widgets[widgetid]._render(js_name)

    @cherrypy.expose
    def default(self, *path, **data):
        if path[0] in webapi._simple_handlers:
            if webapi._simple_handlers[path[0]][0]:
                pages.require(webapi._simple_handlers[path[0]][0])

            return webapi._simple_handlers[path[0]][1](*path, **data)
        raise cherrypy.HTTPError(404, "No builtin or plugin handler")

    @cherrypy.expose
    @cherrypy.config(**{"response.timeout": 7200})
    def user_static(self, *args, **kwargs):
        "Very simple file server feature!"
        pages.require("enumerate_endpoints")
        if not args:
            if os.path.exists(os.path.join(directories.vardir, "static", "index.html")):
                return serve_file(os.path.join(directories.vardir, "static", "index.html"))

        try:
            dir = "/".join(args)
            for i in dir:
                if "/" in i:
                    raise RuntimeError("Security violation")

            for i in dir:
                if ".." in i:
                    raise RuntimeError("Security violation")

            dir = os.path.join(directories.vardir, "static", dir)

            if not os.path.normpath(dir).startswith(os.path.join(directories.vardir, "static")):
                raise RuntimeError("Security violation")

            if os.path.isfile(dir):
                return serve_file(dir)
            else:
                x = [(i + "/" if os.path.isdir(os.path.join(dir, i)) else i) for i in os.listdir(dir)]
                x = "\r\n".join(['<a href="' + i + '">' + i + "</a><br>" for i in x])
                return x
        except Exception:
            return traceback.format_exc()

    # Keep the dispatcher from freaking out. The actual handling
    # Is done by a cherrypy tool. These just keeo cp_dispatch from being called
    # I have NO clue why the favicon doesn't have this issue.
    @cherrypy.expose
    def static(self, *path, **data):
        pass

    @cherrypy.expose
    def usr(self, *path, **data):
        pass

    @cherrypy.expose
    def index(self, *path, **data):
        r = settings.redirects.get("/", {}).get("url", "")
        if r and not path and not cherrypy.url().endswith("/index") or cherrypy.url().endswith("/index/"):
            raise cherrypy.HTTPRedirect(r)

        pages.require("view_status")
        cherrypy.response.cookie["LastSawMainPage"] = time.time()
        return pages.get_template("index.html").render(api=notifications.api, alertsapi=alerts.api)

    @cherrypy.expose
    def dropdownpanel(self, *path, **data):
        pages.require("view_status")
        return pages.get_template("dropdownpanel.html").render(api=notifications.api, alertsapi=alerts.api)

    # @cherrypy.expose
    # def alerts(self, *path, **data):
    #     pages.require("view_status")
    #     return pages.get_template('alerts.html').render(api=notifications.api, alertsapi=alerts.api)

    @cherrypy.expose
    def tagpoints(self, *path, show_advanced="", **data):
        # This page could be slow because of the db stuff, so we restrict it more
        pages.require("system_admin")

        if path:
            tn = "/".join(path)
            if (not tn.startswith("=")) and not tn.startswith("/"):
                tn = "/" + tn
            if tagpoints.normalize_tag_name(tn) not in tagpoints.allTags:
                raise ValueError("This tag does not exist")
            return pages.get_template("settings/tagpoint.html").render(tagName=tn, data=data, show_advanced=True, module="", resource="")
        else:
            return pages.get_template("settings/tagpoints.html").render(data=data, module="", resource="")

    @cherrypy.expose
    def action_step(self, id, **k):
        pages.require("system_admin")
        return module_actions.actions[id].step(**k)

    @cherrypy.expose
    def tag_api(self, cmd, *path, show_advanced="", **data):
        # This page could be slow because of the db stuff, so we restrict it more
        pages.require("enumerate_endpoints")

        if path:
            tn = "/".join(path)
            if (not tn.startswith("=")) and not tn.startswith("/"):
                tn = "/" + tn
            if tagpoints.normalize_tag_name(tn) not in tagpoints.allTags:
                raise ValueError("This tag does not exist")
            if cmd == "info":
                # Funtion does permissions by itself
                return json.dumps(tagpoints.get_tag_meta(tn))
        else:
            raise RuntimeError("No tag specified")

    # docs, helpmenu, and license are just static pages.
    @cherrypy.expose
    def docs(self, *path, **data):
        if path:
            if path[0] == "thirdparty":
                p = os.path.normpath(os.path.join(directories.srcdir, "docs", "/".join(path)))
                if not p.startswith(os.path.join(directories.srcdir, "docs")):
                    raise RuntimeError("Invalid URL")
                cherrypy.response.headers["Content-Type"] = mimetypes.guess_type(p)[0]

                with open(p, "rb") as f:
                    return f.read()
            return pages.get_template("help/" + path[0] + ".html").render(path=path, data=data)
        return pages.get_template("help/help.html").render()

    @cherrypy.expose
    def themetest(self, *path, **data):
        return pages.get_template("help/themetest.html").render()

    @cherrypy.expose
    def about(self, *path, **data):
        return pages.get_template("help/about.html").render()

    @cherrypy.expose
    def changelog(self, *path, **data):
        return pages.get_template("help/changes.html").render()

    @cherrypy.expose
    def helpmenu(self, *path, **data):
        return pages.get_template("help/index.html").render()

    @cherrypy.expose
    def license(self, *path, **data):
        return pages.get_template("help/license.html").render()


root = webapproot()

sdn = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src")
ddn = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "data")

conf = {
    "/": {
        "tools.gzip.on": True,
        "tools.gzip.mime_types": ["text/*", "application/*"],
        "tools.gzip.compress_level": 1,
        "tools.handle_error.on": True,
    },
    "/static": {
        "tools.staticdir.on": True,
        "tools.staticdir.dir": os.path.join(ddn, "static"),
        "tools.sessions.on": False,
        "tools.addheader.on": True,
        "tools.expires.on": True,
        "tools.expires.secs": 3600 + 48,  # expire in 48 hours
        "tools.caching.on": True,
        "tools.caching.delay": 3600,
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
    "/pages": {
        "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
    },
}


def startServer():
    # We don't want Cherrypy writing temp files for no reason
    cherrypy._cpreqbody.Part.maxrambytes = 64 * 1024

    logger.info("Loaded core python code")

    if not config["host"] == "default":
        bindto = config["host"]
    else:
        if config["local_access_only"]:
            bindto = "127.0.0.1"
        else:
            bindto = "::"

    logger.info("Ports are free")

    sys.modules["kaithem"] = sys.modules["__main__"]

    def save():
        if config["save_before_shutdown"]:
            messagebus.post_message("/system/notifications/important/", "System saving before shutting down")
            util.SaveAllState()

    # let the user choose to have the server save everything before a shutdown
    if config["save_before_shutdown"]:
        atexit.register(save)
        cherrypy.engine.subscribe("exit", save)

    site_config = {
        "tools.encode.on": True,
        "tools.encode.encoding": "utf-8",
        "tools.decode.on": True,
        "tools.decode.encoding": "utf-8",
        "log.screen": config["cherrypy_log_stdout"],
        "engine.autoreload.on": False,
    }

    cnf = conf

    def addheader(*args, **kwargs):
        "This function's only purpose is to tell the browser to cache requests for an hour"
        cherrypy.response.headers["Cache-Control"] = "max-age=28800"
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

        # del cherrypy.response.headers['Expires']

    def pageloadnotify(*args, **kwargs):
        systasks.aPageJustLoaded()

    cherrypy.config.update(site_config)
    cherrypy.config.update({"error_page.default": error_page})
    cherrypy.config.update({"error_page.404": error_page_404})

    cherrypy.tools.pageloadnotify = cherrypy.Tool("on_start_resource", pageloadnotify)
    cherrypy.config["tools.pageloadnotify.on"] = True

    cherrypy.tools.addheader = cherrypy.Tool("before_finalize", addheader)

    if hasattr(cherrypy.engine, "signal_handler"):
        del cherrypy.engine.signal_handler.handlers["SIGUSR1"]
        cherrypy.engine.signal_handler.subscribe()

    wsgiapp = cherrypy.tree.mount(root, config=cnf)

    messagebus.post_message("/system/startup", "System Initialized")
    messagebus.post_message("/system/notifications/important", "System Initialized")

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
    ]

    x = []
    for i in webapi._wsgi_apps:
        x += [
            (
                KAuthMatcher(i[0], i[2]),
                wsgi_adapter.WSGIHandler,
                {"wsgi_application": i[1]},
            ),
            (
                PathMatches(i[0]),
                tornado.web.RedirectHandler,
                {"url": "/login", "permanent": False},
            ),
        ]

    for i in webapi._asgi_apps:
        x += [
            (
                KAuthMatcher(i[0], i[2]),
                tornado_asgi_handler.AsgiHandler,
                {"asgi_app": i[1]},
            ),
            (
                PathMatches(i[0]),
                tornado.web.RedirectHandler,
                {"url": "/login", "permanent": False},
            ),
        ]

    xt = []
    for i in webapi._tornado_apps:
        xt += [
            (KAuthMatcher(i[0], i[3]), i[1], i[2]),
            (
                PathMatches("i[0]"),
                tornado.web.RedirectHandler,
                {"url": "/login", "permanent": False},
            ),
        ]

    rules.append(
        Rule(
            AnyMatches(),
            tornado.web.Application(
                x
                + xt
                + [
                    (
                        AnyMatches(),
                        wsgi_adapter.WSGIHandler,
                        {"wsgi_application": wsgiapp},
                    ),
                ]
            ),
        )
    )

    router = RuleRouter(rules)

    http_server = tornado.httpserver.HTTPServer(router)
    # Legacy config comptibility
    http_server.listen(config["http_port"], bindto if not bindto == "::" else None)

    if config["https_port"]:
        if not os.path.exists(os.path.join(directories.ssldir, "certificate.key")):
            cherrypy.server.unsubscribe()
            messagebus.post_message(
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
            https_server.listen(config["https_port"], bindto)

    # Publish to the CherryPy engine as if
    # we were using its mainloop
    tornado.ioloop.PeriodicCallback(lambda: cherrypy.engine.publish("main"), 100).start()
    tornado.ioloop.IOLoop.instance().start()

    logger.info("Cherrypy engine stopped")
