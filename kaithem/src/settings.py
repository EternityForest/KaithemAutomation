# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import ctypes  # Calm down, this has become standard library since 2.5
import datetime
import inspect
import logging
import os
import shutil
import subprocess
import threading
import time
import traceback
from typing import Coroutine

import quart
import quart.utils
import structlog
import vignette
from quart.ctx import copy_current_request_context

from . import (
    auth,
    directories,
    kaithemobj,
    messagebus,
    pages,
    persist,
    quart_app,
    weblogin,
)

notificationsfn = os.path.join(
    directories.vardir, "core.settings", "pushnotifications.toml"
)

pushsettings = persist.getStateFile(notificationsfn)


redirectsfn = os.path.join(
    directories.vardir, "core.settings", "httpredirects.toml"
)


if os.path.exists(redirectsfn):
    redirects = persist.load(redirectsfn)
else:
    redirects = {"/": {"url": ""}}


def setRedirect(url):
    redirects["/"]["url"] = url
    persist.save(redirects, redirectsfn)


fix_alsa = """
/bin/amixer set Master 100%
/bin/amixer -c 1 set PCM 100%
/bin/amixer -c 0 set PCM 100%
/bin/amixer set Headphone 100%
/bin/amixer set Speaker 100%
exit 0
"""

NULL = 0

# https://gist.github.com/liuw/2407154


def ctype_async_raise(thread_obj, exception):
    found = False
    target_tid = 0
    # TODO we use an undocumented api here....
    for tid, tobj in threading._active.items():  # type: ignore
        if tobj is thread_obj:
            found = True
            target_tid = tid
            break

    if not found:
        raise ValueError("Invalid thread object")

    ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(target_tid), ctypes.py_object(exception)
    )
    # ref: http://docs.python.org/c-api/init.html#PyThreadState_SetAsyncExc
    if ret == 0:
        raise ValueError("Invalid thread ID")
    elif ret > 1:
        # Huh? Why would we notify more than one threads?
        # Because we punch a hole into C level interpreter.
        # So it is better to clean up the mess.
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(target_tid), NULL
        )
        raise SystemError("PyThreadState_SetAsyncExc failed")


logger = structlog.get_logger(__name__)


def legacy_route(f):
    r = f"/settings/{f.__name__}"

    p = inspect.signature(f).parameters
    for i in p:
        if i not in ("a", "k", "kwargs", "kw"):
            r += f"/<{i}>"

    async def f2(*a):
        kwargs = dict(await quart.request.form)
        kwargs.update(quart.request.args)

        @copy_current_request_context
        def f3():
            return f(*a, **kwargs)

        return await f3()

    f2.__name__ = f.__name__ + str(os.urandom(8).hex())
    f.f2 = f2

    quart_app.app.route(r, methods=["GET", "POST"])(f2)
    return f


@quart_app.app.route("/settings")
@quart_app.app.route("/settings/index")
@quart_app.app.route("/settings/")
def index_settings():
    """Index page for web interface"""
    return pages.get_template("settings/index.html").render()


@legacy_route
def loginfailures():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    with weblogin.recordslock:
        fr = weblogin.failureRecords.items()
    return pages.get_template("settings/security.html").render(history=fr)


@legacy_route
def threads():
    """Return a page showing all of kaithem's current running threads"""
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/threads.html").render()


@legacy_route
def killThread(a):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()

    for i in threading.enumerate():
        if str(id(i)) == a:
            ctype_async_raise(i, SystemExit)
    return quart.redirect("/settings/threads")


@legacy_route
def fix_alsa_volume():
    pages.require(
        "system_admin",
    )
    subprocess.check_call(fix_alsa, shell=True)
    return quart.redirect("/settings")


@legacy_route
def mdns():
    """Return a page showing all of the discovered stuff on the LAN"""
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/mdns.html").render()


@legacy_route
def stopsounds():
    """Used to stop all sounds currently being played via kaithem's sound module"""
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    kaithemobj.kaithem.sound.stop_all()
    return quart.redirect("/settings")


@legacy_route
def gcsweep():
    """Used to do a garbage collection. I think this is safe and doesn't need xss protection"""
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    import gc

    # I don't think we can return right away anyway or people would think it was broken and not doing anything,
    # Might as well retry a few times in case we have  cleanups that have to propagate through the thread pool or some
    # other crazy unusual case
    gc.collect()
    gc.collect()
    time.sleep(0.1)
    gc.collect()
    time.sleep(0.3)
    gc.collect()
    time.sleep(0.1)
    gc.collect()
    gc.collect()

    return quart.redirect("/settings")


@quart_app.app.route("/settings/files", methods=["GET", "POST"])
@quart_app.app.route("/settings/files/<path:path>", methods=["GET", "POST"])
async def files(path=""):
    """Return a file manager. Kwargs may contain del=file to delete a file. The rest of the path is the directory to look in."""
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    dir = os.path.join("/", path)

    kwargs = dict(await quart.request.form)
    kwargs.update(quart.request.args)

    files = await quart.request.files
    if "file" in files:
        pages.postOnly()
        if os.path.exists(os.path.join(dir, files["file"].filename)):
            raise RuntimeError("Node with that name already exists")

        with open(os.path.join(dir, files["file"].filename), "wb") as f:

            def bg_upload():
                while True:
                    data = files["file"].read(8192)
                    if not data:
                        break
                    f.write(data)

            await quart.utils.run_sync(bg_upload)()

    @copy_current_request_context
    def f():
        try:
            if "del" in kwargs:
                pages.postOnly()
                node = os.path.join(dir, kwargs["del"])
                if os.path.isfile(node):
                    os.remove(node)
                else:
                    shutil.rmtree(node)
                return quart.redirect(quart.request.url.split("?")[0])

            # if "zipfile" in kwargs:
            #     # Unpack all zip members directly right here,
            #     # Without creating a subfolder.
            #     pages.postOnly()
            #     with zipfile.ZipFile(kwargs["zipfile"].file) as zf:
            #         for i in zf.namelist():
            #             with open(os.path.join(dir, i), "wb") as outf:
            #                 f = zf.open(i)
            #                 while True:
            #                     data = f.read(8192)
            #                     if not data:
            #                         break
            #                     outf.write(data)
            #                 f.close()

            if os.path.isdir(dir):
                return pages.get_template("settings/files.html").render(dir=dir)
            else:
                if "thumbnail" in kwargs:
                    t = vignette.try_get_thumbnail(dir)
                    if t:
                        return quart.send_file(t)
                    else:
                        return ""

                return quart.send_file(dir)
        except Exception:
            return traceback.format_exc()

    x = await f()
    if isinstance(x, Coroutine):
        x = await x

    return x


@quart_app.app.route("/settings/cnfdel/<path:path>")
def cnfdel(
    path,
):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/cnfdel.html").render(path=path)


@legacy_route
def broadcast():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/broadcast.html").render()


@legacy_route
def snackbar(msg, duration):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    kaithemobj.widgets.sendGlobalAlert(msg, float(duration))
    return pages.get_template("settings/broadcast.html").render()


@legacy_route
def account():
    try:
        pages.require("own_account_settings")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/user_settings.html").render()


@legacy_route
def leaflet():
    try:
        pages.require("view_status")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.render_jinja_template("settings/util/leaflet.html")


@legacy_route
def refreshuserpage(target):
    try:
        pages.require("own_account_settings")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    try:
        pages.require("/users/settings.edit")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()

    from . import widgets

    widgets.send_to("__FORCEREFRESH__", "", target)
    return quart.redirect("/settings/account")


@legacy_route
def changeprefs(**kwargs):
    try:
        pages.require("own_account_settings")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()

    for i in kwargs:
        if i.startswith("pref_"):
            if i not in ["pref_strftime", "pref_timezone", "email"]:
                continue
            # Filter too long values
            auth.setUserSetting(pages.getAcessingUser(), i[5:], kwargs[i][:200])

    auth.setUserSetting(
        pages.getAcessingUser(), "allow-cors", "allowcors" in kwargs
    )

    return quart.redirect("/settings/account")


@legacy_route
def changeinfo(**kwargs):
    try:
        pages.require("own_account_settings")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    if len(kwargs["email"]) > 120:
        raise RuntimeError("Limit 120 chars for email address")
    auth.setUserSetting(pages.getAcessingUser(), "email", kwargs["email"])
    messagebus.post_message(
        "/system/auth/user/changedemail", pages.getAcessingUser()
    )
    return quart.redirect("/settings/account")


@legacy_route
def changepwd(**kwargs):
    try:
        pages.require("own_account_settings")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    t = quart.request.cookies["kaithem_auth"]
    u = auth.whoHasToken(t)
    if len(kwargs["new"]) > 100:
        raise RuntimeError("Limit 100 chars for password")
    auth.resist_timing_attack((u + kwargs["old"]).encode("utf8"))
    if not auth.userLogin(u, kwargs["old"]) == "failure":
        if kwargs["new"] == kwargs["new2"]:
            auth.changePassword(u, kwargs["new"])
        else:
            return quart.redirect("/errors/mismatch")
    else:
        return quart.redirect("/errors/loginerror")
    messagebus.post_message(
        "/system/auth/user/selfchangedepassword", pages.getAcessingUser()
    )

    return quart.redirect("/")


@legacy_route
def system():
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/global_settings.html").render()


@legacy_route
def theming():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/theming.html").render()


@legacy_route
def settime():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/settime.html").render()


@legacy_route
def set_time_from_web(**kwargs):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    t = float(kwargs["time"])
    subprocess.call(
        [
            "date",
            "-s",
            datetime.datetime.fromtimestamp(
                t, tz=datetime.timezone.utc
            ).isoformat(),
        ]
    )
    try:
        subprocess.call(["sudo", "hwclock", "--systohc"])
    except Exception:
        pass

    return quart.redirect("/settings/system")


@legacy_route
def changesettingstarget(**kwargs):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    from . import geolocation

    geolocation.setDefaultLocation(
        float(kwargs["lat"]),
        float(kwargs["lon"]),
        kwargs["city"],
        country=kwargs["country"],
        region=kwargs["region"],
        timezone=kwargs["timezone"],
    )

    messagebus.post_message(
        "/system/settings/changedelocation", pages.getAcessingUser()
    )
    return quart.redirect("/settings/system")


@legacy_route
def changepushsettings(**kwargs):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()

    t = kwargs["apprise_target"]

    pushsettings.set("apprise_target", t.strip())

    messagebus.post_message(
        "/system/notifications/important",
        "Push notification config was changed",
    )

    return quart.redirect("/settings/system")


@legacy_route
def changeredirecttarget(**kwargs):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    setRedirect(kwargs["url"])
    return quart.redirect("/settings/system")


@legacy_route
def settheming(**kwargs):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    from . import theming

    theming.file["web"]["csstheme"] = kwargs["cssfile"]
    theming.saveTheme()
    return quart.redirect("/settings/theming")


@legacy_route
def ip_geolocate():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    from . import geolocation

    discovered_location = geolocation.ip_geolocate()
    geolocation.setDefaultLocation(
        discovered_location["lat"],
        discovered_location["lon"],
        discovered_location["city"],
        discovered_location["timezone"],
        discovered_location["regionName"],
        discovered_location["countryCode"],
    )

    messagebus.post_message(
        "/system/settings/changedelocation", pages.getAcessingUser()
    )
    return quart.redirect("/settings/system")


@legacy_route
def processes():
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/processes.html").render()


@legacy_route
def dmesg():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/dmesg.html").render()


@legacy_route
def environment():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/environment.html").render()


def legacy_route_prf(f):
    r = f"/settings/profiler/{f.__name__}"

    p = inspect.signature(f).parameters
    for i in p:
        if i not in ("a", "k"):
            r += f"/<{i}>"

    quart_app.app.route(r, methods=["GET", "POST"])(f)


@quart_app.app.route("/settings/profiler")
def prf_index():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/profiler/index.html").render(sort="")


@legacy_route_prf
def bytotal():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("settings/profiler/index.html").render(
        sort="total"
    )


@legacy_route_prf
def start():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    import yappi

    if not yappi.is_running():
        yappi.start()
        try:
            yappi.set_clock_type("cpu")
        except Exception:
            logging.exception("CPU time profiling not supported")

    time.sleep(0.5)
    messagebus.post_message(
        "/system/settings/activatedprofiler", pages.getAcessingUser()
    )
    return quart.redirect("/settings/profiler")


@legacy_route_prf
def stop():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    import yappi

    if yappi.is_running():
        yappi.stop()
    return quart.redirect("/settings/profiler")


@legacy_route_prf
def clear():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    import yappi

    yappi.clear_stats()
    return quart.redirect("/settings/profiler")
