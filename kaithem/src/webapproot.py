# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import asyncio
import json
import logging
import mimetypes
import os
import sys
import time
import traceback
from typing import Callable

import cherrypy
import cherrypy._cpreqbody
import iot_devices
import iot_devices.host
import structlog
from cherrypy.lib.static import serve_file
from hypercorn.asyncio import serve
from hypercorn.config import Config
from hypercorn.middleware import AsyncioWSGIMiddleware, DispatcherMiddleware
from hypercorn.typing import ASGIFramework, Scope
from quart import Response, make_response, request

from kaithem.api import web as webapi

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
    quart_app,
    settings,
    settings_overrides,
    staticfiles,
    systasks,
    tagpoints,
    # TODO we gotta stop depending on import side effects
    util,
    weblogin,
    widgets,
)
from .chandler import web as cweb
from .config import config
from .plugins import CorePluginUserPageResources

logger = structlog.get_logger("system")
logger.setLevel(logging.INFO)


messagebus.subscribe("/system/shutdown", devices.closeAll)
messagebus.subscribe("/system/shutdown", iot_devices.host.app_exit_cleanup)


# This class represents the "/" root of the web app
class webapproot:
    login = weblogin.LoginScreen()
    auth = ManageUsers.ManageAuthorization()
    modules = modules_interface.WebInterface()
    settings = settings.Settings()
    # errors = Errors()
    pages = CorePluginUserPageResources.KaithemPage()
    logs = messagelogging.WebInterface()
    notifications = notifications.WI()
    syslog = logviewer.WebInterface()
    devices = devices_interface.WebDevices()
    chandler = cweb.Web()
    cli = cliserver.WebAPI()

    @quart_app.app.route("/favicon.ico")
    def favicon_ico(self):
        cherrypy.response.headers["Cache-Control"] = "max-age=3600"
        fn = os.path.join(directories.datadir, "static", settings_overrides.get_val("core/favicon_ico"))
        if not os.path.exists(fn):
            fn = os.path.join(directories.vardir, settings_overrides.get_val("core/favicon_ico"))
        return serve_file(fn)

    @quart_app.app.route("/apiwidget/<widgetid>/<js_name>")
    def apiwidget(self, widgetid, js_name):
        pages.require("enumerate_endpoints")
        return widgets.widgets[widgetid]._render(js_name)

    @quart_app.app.route("/<path:path>", methods=["GET", "POST"])
    def default(self, *path):
        data = request.args
        if path[0] in webapi._simple_handlers:
            if webapi._simple_handlers[path[0]][0]:
                pages.require(webapi._simple_handlers[path[0]][0])

            return webapi._simple_handlers[path[0]][1](*path, **data)
        raise cherrypy.HTTPError(404, "No builtin or plugin handler")

    @quart_app.app.route("/user_static/<args:path>")
    def user_static(self, *args):
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

    @cherrypy.expose
    def usr(self, *path, **data):
        pass

    @quart_app.app.route("/")
    async def index(self, *path, **data):
        r = settings.redirects.get("/", {}).get("url", "")
        if r:
            raise cherrypy.HTTPRedirect(r)

        pages.require("view_status")
        cherrypy.response.cookie["LastSawMainPage"] = time.time()
        r = pages.get_template("index.html").render(api=notifications.api, alertsapi=alerts.api)
        r2 = await make_response(r)
        r2.set_cookie("LastSawMainPage", str(time.time()))
        return r2

    @quart_app.app.route("/index")
    async def index2(self):
        pages.require("view_status")
        r = pages.get_template("index.html").render(api=notifications.api, alertsapi=alerts.api)
        r2 = await make_response(r)
        r2.set_cookie("LastSawMainPage", str(time.time()))
        return r2

    @quart_app.app.route("/dropdownpanel")
    def dropdownpanel(self):
        pages.require("view_status")
        return pages.get_template("dropdownpanel.html").render(api=notifications.api, alertsapi=alerts.api)

    @quart_app.app.route("/tagpoints")
    def tagpoints(self, *path, show_advanced=""):
        # This page could be slow because of the db stuff, so we restrict it more
        pages.require("system_admin")
        data = request.args

        return pages.get_template("settings/tagpoints.html").render(data=data, module="", resource="")

    @quart_app.app.route("/tagpoints/<path:tn>", methods=["GET", "POST"])
    def specific_tagpoint(self, *path):
        # This page could be slow because of the db stuff, so we restrict it more
        pages.require("system_admin")

        tn = "/".join(path)
        if (not tn.startswith("=")) and not tn.startswith("/"):
            tn = "/" + tn
        if tagpoints.normalize_tag_name(tn) not in tagpoints.allTags:
            raise ValueError("This tag does not exist")
        return pages.get_template("settings/tagpoint.html").render(
            tagName=tn, data=request.args, show_advanced=True, module="", resource=""
        )

    @quart_app.app.route("/action_step/<id>")
    def action_step(self, id):
        pages.require("system_admin")
        return module_actions.actions[id].step(**request.args) or ""

    @quart_app.app.route("/tag_api/<cmd>/<path:path>")
    def tag_api(self, cmd, *path):
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

        raise RuntimeError("No command specified or bad request")

    # docs, helpmenu, and license are just static pages.
    @quart_app.app.route("/docs/<path:path>")
    def docs(self, *path):
        if path:
            if path[0] == "thirdparty":
                p = os.path.normpath(os.path.join(directories.srcdir, "docs", "/".join(path)))
                if not p.startswith(os.path.join(directories.srcdir, "docs")):
                    raise RuntimeError("Invalid URL")

                with open(p, "rb") as f:
                    d = f.read()

                return Response(d, mimetype=mimetypes.guess_type(p)[0])

            return pages.get_template("help/" + path[0] + ".html").render(path=path, data=request.args)
        return pages.get_template("help/help.html").render()

    @quart_app.app.route("/themetest")
    def themetest(self):
        return pages.get_template("help/themetest.html").render()

    @quart_app.app.route("/about")
    def about(self):
        return pages.get_template("help/about.html").render()

    @quart_app.app.route("/changelog")
    def changelog(self):
        return pages.get_template("help/changes.html").render()

    @quart_app.app.route("/helpmenu")
    def helpmenu(self):
        return pages.get_template("help/index.html").render()

    def license(self):
        return pages.get_template("help/license.html").render()


root = webapproot()


conf = {
    "/": {
        "tools.gzip.on": True,
        "tools.gzip.mime_types": ["text/*", "application/*"],
        "tools.gzip.compress_level": 1,
        "tools.handle_error.on": True,
    },
    "/pages": {
        "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
    },
}


def startServer():
    # We don't want Cherrypy writing temp files for no reason
    cherrypy._cpreqbody.Part.maxrambytes = 64 * 1024
    staticfiles.add_apps()

    hypercornapps = {}
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

    def pageloadnotify(*args, **kwargs):
        systasks.aPageJustLoaded()

    messagebus.post_message("/system/startup", "System Initialized")
    messagebus.post_message("/system/notifications/important", "System Initialized")

    class AuthMiddleware:
        def __init__(self, app: ASGIFramework, permissions: str) -> None:
            self.app = app
            self.permissions = permissions

        async def __call__(self, scope: Scope, receive: Callable, send: Callable) -> None:
            if scope["type"] == "lifespan":
                await self.app(scope, receive, send)
            else:
                u = pages.getAcessingUser(asgi=scope)
                if not pages.canUserDoThis(self.permissions, u):
                    raise RuntimeError("Todo this is a permissino err")

    webapi.add_asgi_app("/widgets/ws", widgets.app, "__guest__")
    webapi.add_asgi_app("/widgets/wsraw", widgets.rawapp, "__guest__")

    x = []
    for i in webapi._wsgi_apps:
        hypercornapps[x[1]] = AuthMiddleware(AsyncioWSGIMiddleware(i[0]), i[2])

    for i in webapi._asgi_apps:
        hypercornapps[x[1]] = AuthMiddleware(i[0], i[2])

    for i in webapi._tornado_apps:
        logging.error("Tornado apps no longer supported")

    dispatcher_app = DispatcherMiddleware(hypercornapps)

    config2 = Config()
    config2.bind = [f"{bindto}:{config['http_port']}"]  # As an example configuration setting

    # if config["https_port"]:
    #     if not os.path.exists(os.path.join(directories.ssldir, "certificate.key")):
    #         raise RuntimeError("No SSL certificate found")
    #     else:
    #         https_server = tornado.httpserver.HTTPServer(
    #             router,
    #             ssl_options={
    #                 "certfile": os.path.join(directories.ssldir, "certificate.cert"),
    #                 "keyfile": os.path.join(directories.ssldir, "certificate.key"),
    #             },
    #         )
    #         https_server.listen(config["https_port"], bindto)

    asyncio.run(serve(dispatcher_app, config2))

    logger.info("Engine stopped")
