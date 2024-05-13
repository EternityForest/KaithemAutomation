# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import ctypes  # Calm down, this has become standard library since 2.5
import logging
import os
import shutil
import subprocess
import threading
import time
import traceback
import zipfile

import cherrypy
from cherrypy.lib.static import serve_file

from . import (
    auth,
    directories,
    kaithemobj,
    messagebus,
    pages,
    persist,
    weblogin,
)

notificationsfn = os.path.join(directories.vardir, "core.settings", "pushnotifications.toml")

pushsettings = persist.getStateFile(notificationsfn)


upnpsettingsfile = os.path.join(directories.vardir, "core.settings", "upnpsettings.yaml")

upnpsettings = persist.getStateFile(upnpsettingsfile)


redirectsfn = os.path.join(directories.vardir, "core.settings", "httpredirects.toml")


if os.path.exists(redirectsfn):
    redirects = persist.load(redirectsfn)
else:
    redirects = {"/": {"url": ""}}


def setRedirect(url):
    redirects["/"]["url"] = url
    persist.save(redirects, redirectsfn)


displayfn = os.path.join(directories.vardir, "core.settings", "display.toml")

if os.path.exists(displayfn):
    display = persist.load(displayfn)
else:
    display = {"__first__": {"rotate": ""}}


fix_alsa = """
/bin/amixer set Master 100%
/bin/amixer -c 1 set PCM 100%
/bin/amixer -c 0 set PCM 100%
/bin/amixer set Headphone 100%
/bin/amixer set Speaker 100%
exit 0
"""


def setScreenRotate(direction):
    if direction not in ("", "left", "right", "normal", "invert"):
        raise RuntimeError("Security!!!")
    os.system(
        """DISPLAY=:0 xrandr --output $(DISPLAY=:0 xrandr | grep -oP  -m 1 '^(.*) (.*)connected' | cut -d" " -f1) --rotate """ + direction
    )
    display["__first__"]["rotate"] = direction
    persist.save(display, displayfn, private=True)


if display.get("__first__", {}).get("rotate", ""):
    try:
        os.system(
            "DISPLAY=:0 xrandr --output $(DISPLAY=:0 xrandr | grep -oP  -m 1 '^(.*) (.*)connected' | cut -d"
            " -f1) --rotate " + display.get("__first__", {}).get("rotate", "")
        )
    except Exception:
        pass


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

    ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(target_tid), ctypes.py_object(exception))
    # ref: http://docs.python.org/c-api/init.html#PyThreadState_SetAsyncExc
    if ret == 0:
        raise ValueError("Invalid thread ID")
    elif ret > 1:
        # Huh? Why would we notify more than one threads?
        # Because we punch a hole into C level interpreter.
        # So it is better to clean up the mess.
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(target_tid), NULL)
        raise SystemError("PyThreadState_SetAsyncExc failed")


syslogger = logging.getLogger("system")


page_plugins: dict[str, PagePlugin] = {}


class PagePlugin:
    def __init__(self, name: str, perms=("system_admin",), title=""):
        page_plugins[name] = self
        self.perms = perms
        self.title = title

    def handle(self, *a, **k):
        raise NotImplementedError()


class Settings:
    @cherrypy.expose
    def index(self):
        """Index page for web interface"""
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return pages.get_template("settings/index.html").render()

    @cherrypy.expose
    def default(self, plugin: str, *a, **k):
        pages.require(page_plugins[plugin].perms)
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return page_plugins[plugin].handle(*a, **k)

    @cherrypy.expose
    def loginfailures(self, **kwargs):
        pages.require("system_admin")
        with weblogin.recordslock:
            fr = weblogin.failureRecords.items()
        return pages.get_template("settings/security.html").render(history=fr)

    @cherrypy.expose
    def threads(self, *a, **k):
        """Return a page showing all of kaithem's current running threads"""
        pages.require("view_admin_info", noautoreturn=True)
        return pages.get_template("settings/threads.html").render()

    @cherrypy.expose
    def killThread(self, a):
        pages.require("system_admin", noautoreturn=True)
        pages.postOnly()

        for i in threading.enumerate():
            if str(id(i)) == a:
                ctype_async_raise(i, SystemExit)
        raise cherrypy.HTTPRedirect("/settings/threads")

    @cherrypy.expose
    def fix_alsa_volume(self, *a, **k):
        pages.require(
            "system_admin",
        )
        subprocess.check_call(fix_alsa, shell=True)
        raise cherrypy.HTTPRedirect("/settings")

    @cherrypy.expose
    def mdns(self, *a, **k):
        """Return a page showing all of the discovered stuff on the LAN"""
        pages.require("system_admin", noautoreturn=True)
        return pages.get_template("settings/mdns.html").render()

    @cherrypy.expose
    def screenshot(self):
        pages.require("system_admin")
        try:
            os.remove("/dev/shm/kaithem_temp_screenshot.jpg")
        except Exception:
            pass

        os.system("scrot /dev/shm/kaithem_temp_screenshot.jpg")
        return serve_file("/dev/shm/kaithem_temp_screenshot.jpg")

    @cherrypy.expose
    def upnp(self, *a, **k):
        """Return a page showing all of the discovered stuff on the LAN"""
        pages.require("system_admin", noautoreturn=True)
        return pages.get_template("settings/upnp.html").render()

    @cherrypy.expose
    def stopsounds(self, *args, **kwargs):
        """Used to stop all sounds currently being played via kaithem's sound module"""
        pages.require("system_admin", noautoreturn=True)
        pages.postOnly()
        kaithemobj.kaithem.sound.stop_all()
        raise cherrypy.HTTPRedirect("/settings")

    @cherrypy.expose
    def gcsweep(self, *args, **kwargs):
        """Used to do a garbage collection. I think this is safe and doesn't need xss protection"""
        pages.require("system_admin")
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

        raise cherrypy.HTTPRedirect("/settings")

    @cherrypy.expose
    @cherrypy.config(**{"response.timeout": 7200})
    def files(self, *args, **kwargs):
        """Return a file manager. Kwargs may contain del=file to delete a file. The rest of the path is the directory to look in."""
        pages.require("system_admin")
        try:
            dir = os.path.join("/", *args)

            if "del" in kwargs:
                pages.postOnly()
                node = os.path.join(dir, kwargs["del"])
                if os.path.isfile(node):
                    os.remove(node)
                else:
                    shutil.rmtree(node)
                raise cherrypy.HTTPRedirect(cherrypy.request.path_info.split("?")[0])

            if "file" in kwargs:
                pages.postOnly()
                if os.path.exists(os.path.join(dir, kwargs["file"].filename)):
                    raise RuntimeError("Node with that name already exists")
                with open(os.path.join(dir, kwargs["file"].filename), "wb") as f:
                    while True:
                        data = kwargs["file"].file.read(8192)
                        if not data:
                            break
                        f.write(data)

            if "zipfile" in kwargs:
                # Unpack all zip members directly right here,
                # Without creating a subfolder.
                pages.postOnly()
                with zipfile.ZipFile(kwargs["zipfile"].file) as zf:
                    for i in zf.namelist():
                        with open(os.path.join(dir, i), "wb") as outf:
                            f = zf.open(i)
                            while True:
                                data = f.read(8192)
                                if not data:
                                    break
                                outf.write(data)
                            f.close()

            if os.path.isdir(dir):
                return pages.get_template("settings/files.html").render(dir=dir)
            else:
                return serve_file(dir)
        except Exception:
            return traceback.format_exc()

    @cherrypy.expose
    def hlsplayer(self, *args, **kwargs):
        """Return a file manager. Kwargs may contain del=file to delete a file. The rest of the path is the directory to look in."""
        pages.require("system_admin")
        try:
            dir = os.path.join("/", *args)
            return pages.get_template("settings/hlsplayer.html").render(play=dir)
        except Exception:
            return traceback.format_exc()

    @cherrypy.expose
    def cnfdel(self, *args, **kwargs):
        pages.require("system_admin")
        path = os.path.join("/", *args)
        return pages.get_template("settings/cnfdel.html").render(path=path)

    @cherrypy.expose
    def broadcast(self, **kwargs):
        pages.require("system_admin")
        return pages.get_template("settings/broadcast.html").render()

    @cherrypy.expose
    def snackbar(self, msg, duration):
        pages.require("system_admin")
        pages.postOnly()
        kaithemobj.widgets.sendGlobalAlert(msg, float(duration))
        return pages.get_template("settings/broadcast.html").render()

    @cherrypy.expose
    def account(self):
        pages.require("own_account_settings")
        return pages.get_template("settings/user_settings.html").render()

    @cherrypy.expose
    def leaflet(self, *a, **k):
        pages.require("view_status")
        return pages.render_jinja_template("settings/util/leaflet.html")

    @cherrypy.expose
    def refreshuserpage(self, target):
        pages.require("own_account_settings")
        pages.require("/users/settings.edit")
        pages.postOnly()

        from . import widgets

        widgets.send_to("__FORCEREFRESH__", "", target)
        raise cherrypy.HTTPRedirect("/settings/account")

    @cherrypy.expose
    def changeprefs(self, **kwargs):
        pages.require("own_account_settings")
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        pages.postOnly()

        if "tabtospace" in kwargs:
            auth.setUserSetting(pages.getAcessingUser(), "tabtospace", True)
        else:
            auth.setUserSetting(pages.getAcessingUser(), "tabtospace", False)

        for i in kwargs:
            if i.startswith("pref_"):
                if i not in ["pref_strftime", "pref_timezone", "email"]:
                    continue
                # Filter too long values
                auth.setUserSetting(pages.getAcessingUser(), i[5:], kwargs[i][:200])

        auth.setUserSetting(pages.getAcessingUser(), "allow-cors", "allowcors" in kwargs)

        raise cherrypy.HTTPRedirect("/settings/account")

    @cherrypy.expose
    def changeinfo(self, **kwargs):
        pages.require("own_account_settings")
        pages.postOnly()
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        if len(kwargs["email"]) > 120:
            raise RuntimeError("Limit 120 chars for email address")
        auth.setUserSetting(pages.getAcessingUser(), "email", kwargs["email"])
        messagebus.post_message("/system/auth/user/changedemail", pages.getAcessingUser())
        raise cherrypy.HTTPRedirect("/settings/account")

    @cherrypy.expose
    def changepwd(self, **kwargs):
        pages.require("own_account_settings")
        pages.postOnly()
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        t = cherrypy.request.cookie["kaithem_auth"].value
        u = auth.whoHasToken(t)
        if len(kwargs["new"]) > 100:
            raise RuntimeError("Limit 100 chars for password")
        auth.resist_timing_attack((u + kwargs["old"]).encode("utf8"))
        if not auth.userLogin(u, kwargs["old"]) == "failure":
            if kwargs["new"] == kwargs["new2"]:
                auth.changePassword(u, kwargs["new"])
            else:
                raise cherrypy.HTTPRedirect("/errors/mismatch")
        else:
            raise cherrypy.HTTPRedirect("/errors/loginerror")
        messagebus.post_message("/system/auth/user/selfchangedepassword", pages.getAcessingUser())

        raise cherrypy.HTTPRedirect("/")

    @cherrypy.expose
    def system(self):
        pages.require("view_admin_info")
        return pages.get_template("settings/global_settings.html").render()

    @cherrypy.expose
    def theming(self):
        pages.require("system_admin")
        return pages.get_template("settings/theming.html").render()

    @cherrypy.expose
    def settime(self):
        pages.require("system_admin")
        return pages.get_template("settings/settime.html").render()

    @cherrypy.expose
    def set_time_from_web(self, **kwargs):
        pages.require("system_admin", noautoreturn=True)
        pages.postOnly()
        t = float(kwargs["time"])
        subprocess.call(
            [
                "date",
                "-s",
                time.strftime("%Y%m%d%H%M%S", time.gmtime(t - 0.05)),
                "+%Y%m%d%H%M%S",
            ]
        )
        try:
            subprocess.call(["sudo", "hwclock", "--systohc"])
        except Exception:
            pass

        raise cherrypy.HTTPRedirect("/settings/system")

    @cherrypy.expose
    def changealertsettingstarget(self, **kwargs):
        pages.require("system_admin", noautoreturn=True)
        pages.postOnly()
        from . import alerts

        alerts.file["warning"]["interval"] = float(kwargs["warningbeeptime"])
        alerts.file["error"]["interval"] = float(kwargs["errorbeeptime"])
        alerts.file["critical"]["interval"] = float(kwargs["critbeeptime"])
        alerts.file["warning"]["file"] = kwargs["warningsound"]
        alerts.file["error"]["file"] = kwargs["errorsound"]
        alerts.file["critical"]["file"] = kwargs["critsound"]
        alerts.file["all"]["soundcard"] = kwargs["soundcard"]
        alerts.saveSettings()

        raise cherrypy.HTTPRedirect("/settings/system")

    @cherrypy.expose
    def changesettingstarget(self, **kwargs):
        pages.require("system_admin", noautoreturn=True)
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

        messagebus.post_message("/system/settings/changedelocation", pages.getAcessingUser())
        raise cherrypy.HTTPRedirect("/settings/system")

    @cherrypy.expose
    def changepushsettings(self, **kwargs):
        pages.require("system_admin", noautoreturn=True)
        pages.postOnly()

        t = kwargs["apprise_target"]

        pushsettings.set("apprise_target", t.strip())

        messagebus.post_message("/system/notifications/important", "Push notification config was changed")

        raise cherrypy.HTTPRedirect("/settings/system")

    @cherrypy.expose
    def changeredirecttarget(self, **kwargs):
        pages.require("system_admin", noautoreturn=True)
        pages.postOnly()
        setRedirect(kwargs["url"])
        raise cherrypy.HTTPRedirect("/settings/system")

    @cherrypy.expose
    def changerotationtarget(self, **kwargs):
        pages.require("system_admin", noautoreturn=True)
        pages.postOnly()
        setScreenRotate(kwargs["rotate"])
        raise cherrypy.HTTPRedirect("/settings/system")

    @cherrypy.expose
    def settheming(self, **kwargs):
        pages.require("system_admin", noautoreturn=True)
        pages.postOnly()
        from . import theming

        theming.file["web"]["csstheme"] = kwargs["cssfile"]
        theming.saveTheme()
        raise cherrypy.HTTPRedirect("/settings/theming")

    @cherrypy.expose
    def ip_geolocate(self, **kwargs):
        pages.require("system_admin", noautoreturn=True)
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

        messagebus.post_message("/system/settings/changedelocation", pages.getAcessingUser())
        raise cherrypy.HTTPRedirect("/settings/system")

    @cherrypy.expose
    def processes(self):
        pages.require("view_admin_info")
        return pages.get_template("settings/processes.html").render()

    @cherrypy.expose
    def dmesg(self):
        pages.require("view_admin_info")
        return pages.get_template("settings/dmesg.html").render()

    @cherrypy.expose
    def environment(self):
        pages.require("view_admin_info")
        return pages.get_template("settings/environment.html").render()

    class profiler:
        @cherrypy.expose
        def index():
            pages.require("system_admin")
            return pages.get_template("settings/profiler/index.html").render(sort="")

        @cherrypy.expose
        def bytotal():
            pages.require("system_admin")
            return pages.get_template("settings/profiler/index.html").render(sort="total")

        @cherrypy.expose
        def start():
            pages.require("system_admin", noautoreturn=True)
            pages.postOnly()
            import yappi

            if not yappi.is_running():
                yappi.start()
                try:
                    yappi.set_clock_type("cpu")
                except Exception:
                    logging.exception("CPU time profiling not supported")

            time.sleep(0.5)
            messagebus.post_message("/system/settings/activatedprofiler", pages.getAcessingUser())
            raise cherrypy.HTTPRedirect("/settings/profiler")

        @cherrypy.expose
        def stop():
            pages.require("system_admin", noautoreturn=True)
            pages.postOnly()
            import yappi

            if yappi.is_running():
                yappi.stop()
            raise cherrypy.HTTPRedirect("/settings/profiler")

        @cherrypy.expose
        def clear():
            pages.require("system_admin", noautoreturn=True)
            pages.postOnly()
            import yappi

            yappi.clear_stats()
            raise cherrypy.HTTPRedirect("/settings/profiler/")
