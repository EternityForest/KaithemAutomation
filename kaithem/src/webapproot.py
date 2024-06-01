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

import iot_devices
import iot_devices.host
import quart
import starlette.responses
import structlog
from hypercorn.asyncio import serve
from hypercorn.config import Config
from hypercorn.middleware import AsyncioWSGIMiddleware, DispatcherMiddleware
from hypercorn.typing import ASGIFramework, Scope
from quart import Response, make_response, request, send_file

from kaithem.api import web as webapi
from kaithem.src.chandler import web  # noqa: F401

from . import (
    alerts,
    devices,
    directories,
    messagebus,
    module_actions,
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
    widgets,
)
from .config import config

logger = structlog.get_logger("system")
logger.setLevel(logging.INFO)


messagebus.subscribe("/system/shutdown", devices.closeAll)
messagebus.subscribe("/system/shutdown", iot_devices.host.app_exit_cleanup)


# This class represents the "/" root of the web app
# class webapproot:
#     login = weblogin.LoginScreen()
#     auth = ManageUsers.ManageAuthorization()
#     modules = modules_interface.WebInterface()
#     settings = settings.Settings()
#     # errors = Errors()
#     pages = CorePluginUserPageResources.KaithemPage()
#     logs = messagelogging.WebInterface()
#     notifications = notifications.WI()
#     syslog = logviewer.WebInterface()
#     devices = devices_interface.WebDevices()
#     chandler = cweb.Web()
#     cli = cliserver.WebAPI()


@quart_app.app.route("/favicon.ico")
async def favicon():
    fn = os.path.join(directories.datadir, "static", settings_overrides.get_val("core/favicon_ico"))
    if not os.path.exists(fn):
        fn = os.path.join(directories.vardir, settings_overrides.get_val("core/favicon_ico"))
    return await send_file(fn, cache_timeout=3600 * 24)


@quart_app.app.route("/apiwidget/<widgetid>")
def apiwidget(widgetid):
    js_name = request.args.get("js_name", None)
    assert js_name
    try:
        pages.require("enumerate_endpoints")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return widgets.widgets[widgetid]._render(js_name)


# Todo: is this to slow for async??
@quart_app.app.route("/user_static/<path:args>")
async def user_static(*args):
    "Very simple file server feature!"
    try:
        pages.require("enumerate_endpoints")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    if not args:
        if os.path.exists(os.path.join(directories.vardir, "static", "index.html")):
            return await quart.send_file(os.path.join(directories.vardir, "static", "index.html"))

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
            return await quart.send_file(dir)
        else:
            x = [(i + "/" if os.path.isdir(os.path.join(dir, i)) else i) for i in os.listdir(dir)]
            x = "\r\n".join(['<a href="' + i + '">' + i + "</a><br>" for i in x])
            return x
    except Exception:
        return traceback.format_exc()


@quart_app.app.route("/")
async def index_default(*path, **data):
    r = settings.redirects.get("/", {}).get("url", "")
    if r:
        raise quart.redirect(r)

    try:
        pages.require("view_status")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    r = pages.get_template("index.html").render(api=notifications.api, alertsapi=alerts.api)
    r2 = await make_response(r)
    r2.set_cookie("LastSawMainPage", str(time.time()))
    return r2


@quart_app.app.route("/index")
async def index_direct():
    try:
        pages.require("view_status")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    r = pages.get_template("index.html").render(api=notifications.api, alertsapi=alerts.api)
    r2 = await make_response(r)
    r2.set_cookie("LastSawMainPage", str(time.time()))
    return r2


@quart_app.app.route("/dropdownpanel")
def dropdownpanel():
    try:
        pages.require("view_status")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("dropdownpanel.html").render(api=notifications.api, alertsapi=alerts.api)


@quart_app.app.route("/tagpoints")
def tagpoints_index(*path, show_advanced=""):
    # This page could be slow because of the db stuff, so we restrict it more
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    data = request.args

    return pages.get_template("settings/tagpoints.html").render(data=data, module="", resource="")


@quart_app.app.route("/tagpoints/<path:path>", methods=["GET", "POST"])
def specific_tagpoint(path):
    path = path.split("/")
    # This page could be slow because of the db stuff, so we restrict it more
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    tn = "/".join(path)
    if (not tn.startswith("=")) and not tn.startswith("/"):
        tn = "/" + tn
    if tagpoints.normalize_tag_name(tn) not in tagpoints.allTags:
        raise ValueError("This tag does not exist")
    return pages.get_template("settings/tagpoint.html").render(tagName=tn, data=request.args, show_advanced=True, module="", resource="")


@quart_app.app.route("/action_step/<id>")
def action_step(id):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return module_actions.actions[id].step(**request.args) or ""


@quart_app.app.route("/tag_api/<cmd>/<path:path>")
def tag_api(cmd, *path):
    # This page could be slow because of the db stuff, so we restrict it more
    try:
        pages.require("enumerate_endpoints")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

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
def docs(*path):
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
def themetest():
    return pages.get_template("help/themetest.html").render()


@quart_app.app.route("/about")
def about():
    return pages.get_template("help/about.html").render()


@quart_app.app.route("/changelog")
def changelog():
    return pages.get_template("help/changes.html").render()


@quart_app.app.route("/helpmenu")
def helpmenu():
    return pages.get_template("help/index.html").render()


@quart_app.app.route("/license")
def license():
    return pages.get_template("help/license.html").render()


class AsgiDispatcher:
    def __init__(self, patterns):
        self.patterns = []
        for i in patterns:
            self.patterns.append((i, patterns[i]))

        # Longest to shortest
        self.patterns.sort()
        self.patterns.reverse()

    async def __call__(self, scope, receive, send):
        app = None
        for p in self.patterns:
            scope_path = p[0]
            asgi_application = p[1]

            if scope["path"].startswith(scope_path):
                app = asgi_application
                break

        assert app
        try:
            await app(scope, receive, send)
        except Exception:
            if scope["type"] == "http":
                r = starlette.responses.Response(pages.get_template("errors/e500.html").render(e=traceback.format_exc()))
                await r(scope, receive, send)
            else:
                print("Error", traceback.format_exc())
            raise


def startServer():
    quart_app.app.config["MAX_CONTENT_LENGTH"] = 384 * 1024
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
            await self.app(scope, receive, send)

    webapi.add_asgi_app("/widgets/ws", widgets.app, "__guest__")
    webapi.add_asgi_app("/widgets/wsraw", widgets.rawapp, "__guest__")

    for i in webapi._wsgi_apps:
        hypercornapps[i[0]] = AuthMiddleware(AsyncioWSGIMiddleware(i[1]), i[2])

    for i in webapi._asgi_apps:
        hypercornapps[i[0]] = AuthMiddleware(i[1], i[2])

    hypercornapps["/"] = quart_app.app
    dispatcher_app = AsgiDispatcher(hypercornapps)

    config2 = Config()
    config2.bind = [f"{bindto}:{config['http_port']}"]  # As an example configuration setting
    config2.workers = 8
    config2.worker_class = "uvloop"
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
