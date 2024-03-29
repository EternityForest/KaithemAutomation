# Copyright Daniel Dunn 2013,2017
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
import time
import threading
import ctypes  # Calm down, this has become standard library since 2.5
import cherrypy
import base64
import os
import subprocess
import shutil
import sys
import logging
import traceback
import zipfile
from cherrypy.lib.static import serve_file
from . import pages, util, messagebus, config, auth, kaithemobj, config, weblogin, systasks, gpio, directories, persist


notificationsfn = os.path.join(
    directories.vardir, "core.settings", "pushnotifications.toml")

pushsettings = persist.getStateFile(notificationsfn)


upnpsettingsfile = os.path.join(
    directories.vardir, "core.settings", "upnpsettings.yaml")

upnpsettings = persist.getStateFile(upnpsettingsfile)


redirectsfn = os.path.join(
    directories.vardir, "core.settings", "httpredirects.toml")


if os.path.exists(redirectsfn):
    redirects = persist.load(redirectsfn)
else:
    redirects = {
        "/": {
            "url": ""
        }
    }


def setRedirect(url):
    redirects['/']['url'] = url
    persist.save(redirects, redirectsfn)


displayfn = os.path.join(directories.vardir, "core.settings", "display.toml")

if os.path.exists(displayfn):
    display = persist.load(displayfn)
else:
    display = {
        "__first__": {
            "rotate": ""
        }
    }


fix_alsa = """
/bin/amixer set Master 100%
/bin/amixer -c 1 set PCM 100%
/bin/amixer -c 0 set PCM 100%
/bin/amixer set Headphone 100%
/bin/amixer set Speaker 100%
exit 0
"""


def setScreenRotate(direction):
    if not direction in ('', 'left', 'right', 'normal', 'invert'):
        raise RuntimeError("Security!!!")
    os.system('''DISPLAY=:0 xrandr --output $(DISPLAY=:0 xrandr | grep -oP  -m 1 '^(.*) (.*)connected' | cut -d" " -f1) --rotate ''' + direction)
    display['__first__']['rotate'] = direction
    persist.save(display, displayfn, private=True)


if display.get('__first__', {}).get('rotate', ''):
    try:
        os.system("DISPLAY=:0 xrandr --output $(DISPLAY=:0 xrandr | grep -oP  -m 1 '^(.*) (.*)connected' | cut -d" " -f1) --rotate " +
                  display.get('__first__', {}).get('rotate', ''))
    except Exception:
        pass


NULL = 0

# https://gist.github.com/liuw/2407154


def ctype_async_raise(thread_obj, exception):
    found = False
    target_tid = 0
    for tid, tobj in threading._active.items():
        if tobj is thread_obj:
            found = True
            target_tid = tid
            break

    if not found:
        raise ValueError("Invalid thread object")

    ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(target_tid), ctypes.py_object(exception))
    # ref: http://docs.python.org/c-api/init.html#PyThreadState_SetAsyncExc
    if ret == 0:
        raise ValueError("Invalid thread ID")
    elif ret > 1:
        # Huh? Why would we notify more than one threads?
        # Because we punch a hole into C level interpreter.
        # So it is better to clean up the mess.
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(target_tid), NULL)
        raise SystemError("PyThreadState_SetAsyncExc failed")


def validate_upload():
    # Allow large uploads for admin users, otherwise only allow 64k
    return 64 * 1024 if not pages.canUserDoThis("/admin/settings.edit") else 1024 * 1024 * 8192 * 4


syslogger = logging.getLogger("system")


class Settings():
    @cherrypy.expose
    def index(self):
        """Index page for web interface"""
        cherrypy.response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        return pages.get_template("settings/index.html").render()

    @cherrypy.expose
    def loginfailures(self, **kwargs):
        pages.require("/admin/settings.edit")
        with weblogin.recordslock:
            fr = weblogin.failureRecords.items()
        return pages.get_template("settings/security.html").render(history=fr)

    @cherrypy.expose
    def reloadcfg(self):
        """"Used to reload the config file"""
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()
        config.reload()
        raise cherrypy.HTTPRedirect("/settings")

    @cherrypy.expose
    def threads(self, *a, **k):
        """Return a page showing all of kaithem's current running threads"""
        pages.require("/admin/settings.view", noautoreturn=True)
        return pages.get_template("settings/threads.html").render()

    @cherrypy.expose
    def killThread(self, a):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()

        for i in threading.enumerate():
            if str(id(i)) == a:
                ctype_async_raise(i, SystemExit)
        raise cherrypy.HTTPRedirect("/settings/threads")

    @cherrypy.expose
    def mixer(self, *a, **k):
        pages.require("/users/mixer.edit",)
        from kaithem.src import jackmixer, directories
        return pages.get_template("settings/mixer.html").render(os=os,
                                                                jackmixer=jackmixer,
                                                                directories=directories)
    @cherrypy.expose
    def fix_alsa_volume(self, *a, **k):
        pages.require("/users/mixer.edit",)
        subprocess.check_call(fix_alsa, shell=True)
        raise cherrypy.HTTPRedirect("/settings")

    @cherrypy.expose
    def wifi(self, *a, **k):
        """Return a page showing the wifi config"""
        pages.require("/admin/settings.edit",)
        return pages.get_template("settings/wifi.html").render()

    @cherrypy.expose
    def mdns(self, *a, **k):
        """Return a page showing all of the discovered stuff on the LAN"""
        pages.require("/admin/settings.edit", noautoreturn=True)
        return pages.get_template("settings/mdns.html").render()

    @cherrypy.expose
    def screenshot(self):
        pages.require("/admin/settings.edit")
        try:
            os.remove("/dev/shm/kaithem_temp_screenshot.jpg")
        except Exception:
            pass

        os.system("scrot /dev/shm/kaithem_temp_screenshot.jpg")
        return serve_file("/dev/shm/kaithem_temp_screenshot.jpg")

    @cherrypy.expose
    def upnp(self, *a, **k):
        """Return a page showing all of the discovered stuff on the LAN"""
        pages.require("/admin/settings.edit", noautoreturn=True)
        return pages.get_template("settings/upnp.html").render()

    @cherrypy.expose
    def stopsounds(self, *args, **kwargs):
        """Used to stop all sounds currently being played via kaithem's sound module"""
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()
        kaithemobj.kaithem.sound.stop_all()
        raise cherrypy.HTTPRedirect("/settings")

    @cherrypy.expose
    def gcsweep(self, *args, **kwargs):
        """Used to do a garbage collection. I think this is safe and doesn't need xss protection"""
        pages.require("/admin/settings.edit")
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
    def updateytdl(self, *args, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()

        if util.which("yt-dlp"):
            try:
                subprocess.check_call(["yt-dlp", '-U'])
            except Exception:
                subprocess.check_call(
                    ["pip3", "install", "--upgrade", "yt-dlp"])

        raise cherrypy.HTTPRedirect("/settings")

    @cherrypy.expose
    @cherrypy.config(**{'response.timeout': 7200})
    def files(self, *args, **kwargs):
        """Return a file manager. Kwargs may contain del=file to delete a file. The rest of the path is the directory to look in."""
        pages.require("/admin/settings.edit")
        try:
            dir = os.path.join('/', *args)

            if 'del' in kwargs:
                pages.postOnly()
                node = os.path.join(dir, kwargs['del'])
                if os.path.isfile(node):
                    os.remove(node)
                else:
                    shutil.rmtree(node)
                raise cherrypy.HTTPRedirect(
                    cherrypy.request.path_info.split('?')[0])

            if 'file' in kwargs:
                pages.postOnly()
                if os.path.exists(os.path.join(dir, kwargs['file'].filename)):
                    raise RuntimeError("Node with that name already exists")
                with open(os.path.join(dir, kwargs['file'].filename), 'wb') as f:
                    while True:
                        data = kwargs['file'].file.read(8192)
                        if not data:
                            break
                        f.write(data)

            if 'zipfile' in kwargs:
                # Unpack all zip members directly right here,
                # Without creating a subfolder.
                pages.postOnly()
                with zipfile.ZipFile(kwargs['zipfile'].file) as zf:
                    for i in zf.namelist():
                        with open(os.path.join(dir, i), 'wb') as outf:
                            f = zf.open(i)
                            while True:
                                data = f.read(8192)
                                if not data:
                                    break
                                outf.write(data)
                            f.close()

            if util.which("yt-dlp"):
                ytdl = "yt-dlp"
            else:
                ytdl = "youtube-dl"

            if 'youtubedl' in kwargs:
                pages.postOnly()
                subprocess.check_call([ytdl, '--format', 'bestaudio', "--extract-audio", "--audio-format",
                                       "mp3", "--audio-quality", "2", "--embed-thumbnail", "--add-metadata", kwargs['youtubedl']], cwd=dir)

            if 'youtubedlvid' in kwargs:
                pages.postOnly()
                subprocess.check_call([ytdl, kwargs['youtubedlvid']], cwd=dir)

            if os.path.isdir(dir):
                return pages.get_template("settings/files.html").render(dir=dir)
            else:
                return serve_file(dir)
        except Exception:
            return (traceback.format_exc())

    @cherrypy.expose
    def hlsplayer(self, *args, **kwargs):
        """Return a file manager. Kwargs may contain del=file to delete a file. The rest of the path is the directory to look in."""
        pages.require("/admin/settings.edit")
        try:
            dir = os.path.join('/', *args)
            return pages.get_template("settings/hlsplayer.html").render(play=dir)
        except Exception:
            return (traceback.format_exc())

    @cherrypy.expose
    def cnfdel(self, *args, **kwargs):
        pages.require("/admin/settings.edit")
        path = os.path.join('/', *args)
        return pages.get_template("settings/cnfdel.html").render(path=path)

    @cherrypy.expose
    def broadcast(self, **kwargs):
        pages.require("/admin/settings.edit")
        return pages.get_template("settings/broadcast.html").render()

    @cherrypy.expose
    def snackbar(self, msg, duration):
        pages.require("/admin/settings.edit")
        pages.postOnly()
        kaithemobj.widgets.sendGlobalAlert(msg, float(duration))
        return pages.get_template("settings/broadcast.html").render()

    @cherrypy.expose
    def console(self, **kwargs):
        pages.require("/admin/settings.edit")
        cherrypy.response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if 'script' in kwargs:
            pages.postOnly()
            x = ''
            env = {}
            env.update(os.environ)

            if util.which("bash"):
                p = subprocess.Popen("bash -i", universal_newlines=True, shell=True, env=env,
                                     stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                p = subprocess.Popen("sh -i", universal_newlines=True, shell=True, env=env,
                                     stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

            t = p.communicate(kwargs['script'])

            if isinstance(t, bytes):
                try:
                    t = t.decode('utf-8')
                except Exception:
                    pass

            x += t[0] + t[1]
            try:
                time.sleep(0.1)
                t = p.communicate('')
                x += t[0] + t[1]
                p.kill()
                p.stdout.close()
                p.stderr.close()
                p.stdin.close()
            except Exception:
                pass
            return pages.get_template("settings/console.html").render(output=x)
        else:
            return pages.get_template("settings/console.html").render(output="Kaithem System Shell")

    @cherrypy.expose
    def account(self):
        pages.require("/users/accountsettings.edit")
        return pages.get_template("settings/user_settings.html").render()

    @cherrypy.expose
    def imgmap(self):
        pages.require("/admin/modules.view")
        return pages.get_template("settings/util/imgmap.html").render()

    @cherrypy.expose
    def leaflet(self, *a, **k):
        pages.require("/admin/mainpage.view")
        return pages.render_jinja_template("settings/util/leaflet.html")

    @cherrypy.expose
    def refreshuserpage(self, target):
        pages.require("/users/accountsettings.edit")
        pages.require("/users/settings.edit")
        pages.postOnly()

        from . import widgets
        widgets.sendTo("__FORCEREFRESH__", '', target)
        raise cherrypy.HTTPRedirect("/settings/account")

    @cherrypy.expose
    def changeprefs(self, **kwargs):
        pages.require("/users/accountsettings.edit")
        cherrypy.response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        pages.postOnly()
        lists = []
        if "tabtospace" in kwargs:
            auth.setUserSetting(pages.getAcessingUser(), "tabtospace", True)
        else:
            auth.setUserSetting(pages.getAcessingUser(), "tabtospace", False)

        for i in kwargs:
            if i.startswith("pref_"):
                if not i in ['pref_strftime', "pref_timezone", "email"]:
                    continue
                # Filter too long values
                auth.setUserSetting(pages.getAcessingUser(),
                                    i[5:], kwargs[i][:200])

        auth.setUserSetting(pages.getAcessingUser(),
                            'usemonaco', 'usemonaco' in kwargs)

        auth.setUserSetting(pages.getAcessingUser(),
                            'allow-cors', 'allowcors' in kwargs)

        raise cherrypy.HTTPRedirect("/settings/account")

    @cherrypy.expose
    def changeinfo(self, **kwargs):
        pages.require("/users/accountsettings.edit")
        pages.postOnly()
        cherrypy.response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if len(kwargs['email']) > 120:
            raise RuntimeError("Limit 120 chars for email address")
        auth.setUserSetting(pages.getAcessingUser(), 'email', kwargs['email'])
        messagebus.post_message(
            "/system/auth/user/changedemail", pages.getAcessingUser())
        raise cherrypy.HTTPRedirect("/settings/account")

    @cherrypy.expose
    def changepwd(self, **kwargs):
        pages.require("/users/accountsettings.edit")
        pages.postOnly()
        cherrypy.response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        t = cherrypy.request.cookie['kaithem_auth'].value
        u = auth.whoHasToken(t)
        if len(kwargs['new']) > 100:
            raise RuntimeError("Limit 100 chars for password")
        auth.resist_timing_attack((u + kwargs['old']).encode('utf8'))
        if not auth.userLogin(u, kwargs['old']) == "failure":
            if kwargs['new'] == kwargs['new2']:
                auth.changePassword(u, kwargs['new'])
            else:
                raise cherrypy.HTTPRedirect("/errors/mismatch")
        else:
            raise cherrypy.HTTPRedirect("/errors/loginerror")
        messagebus.post_message(
            "/system/auth/user/selfchangedepassword", pages.getAcessingUser())

        raise cherrypy.HTTPRedirect("/")

    @cherrypy.expose
    def system(self):
        pages.require("/admin/settings.view")
        return pages.get_template("settings/global_settings.html").render()

    @cherrypy.expose
    def save(self):
        pages.require("/admin/settings.edit")
        return pages.get_template("settings/save.html").render()

    @cherrypy.expose
    def theming(self):
        pages.require("/admin/settings.edit")
        return pages.get_template("settings/theming.html").render()

    @cherrypy.expose
    def savetarget(self):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()
        util.SaveAllState()
        raise cherrypy.HTTPRedirect('/')

    @cherrypy.expose
    def settime(self):
        pages.require("/admin/settings.edit")
        return pages.get_template("settings/settime.html").render()

    @cherrypy.expose
    def set_time_from_web(self, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()
        t = float(kwargs['time'])
        subprocess.call(["date", "-s",
                         time.strftime("%Y%m%d%H%M%S", time.gmtime(t - 0.05)), "+%Y%m%d%H%M%S", ])
        try:
            subprocess.call(["sudo", "hwclock", "--systohc"])
        except Exception:
            pass

        raise cherrypy.HTTPRedirect('/settings/system')

    @cherrypy.expose
    def changealertsettingstarget(self, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()
        from . import alerts

        alerts.file['warning']['interval'] = float(kwargs['warningbeeptime'])
        alerts.file['error']['interval'] = float(kwargs['errorbeeptime'])
        alerts.file['critical']['interval'] = float(kwargs['critbeeptime'])
        alerts.file['warning']['file'] = kwargs['warningsound']
        alerts.file['error']['file'] = kwargs['errorsound']
        alerts.file['critical']['file'] = kwargs['critsound']
        alerts.file['all']['soundcard'] = kwargs['soundcard']
        alerts.saveSettings()

        raise cherrypy.HTTPRedirect('/settings/system')

    @cherrypy.expose
    def changesettingstarget(self, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()
        from . import geolocation
        geolocation.setDefaultLocation(float(kwargs['lat']), float(kwargs['lon']), kwargs['city'],
                                       country=kwargs['country'], region=kwargs['region'], timezone=kwargs['timezone'])

        messagebus.post_message(
            "/system/settings/changedelocation", pages.getAcessingUser())
        raise cherrypy.HTTPRedirect('/settings/system')

    @cherrypy.expose
    def changepushsettings(self, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()

        t = kwargs['apprise_target']

        pushsettings.set("apprise_target", t.strip())

        messagebus.post_message(
            "/system/notifications/important", "Push notification config was changed")

        raise cherrypy.HTTPRedirect('/settings/system')

    @cherrypy.expose
    def changestartupscript(self, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()

        t = kwargs['data']
        util.ensure_dir(os.path.join(directories.vardir, 'core.settings', 'startup.sh'))
        with open(os.path.join(directories.vardir, 'core.settings', 'startup.sh'), 'w') as f:
            f.write(t)

        raise cherrypy.HTTPRedirect('/settings/system')

    @cherrypy.expose
    def changeupnptarget(self, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()

        upnpsettings.set("wan_port", int(kwargs['exposeport']))

        systasks.doUPnP()
        raise cherrypy.HTTPRedirect('/settings/system')

    @cherrypy.expose
    def changeredirecttarget(self, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()
        setRedirect(kwargs['url'])
        raise cherrypy.HTTPRedirect('/settings/system')

    @cherrypy.expose
    def changerotationtarget(self, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()
        setScreenRotate(kwargs['rotate'])
        raise cherrypy.HTTPRedirect('/settings/system')

    @cherrypy.expose
    def settheming(self, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()
        from . import theming
        theming.file['web']['csstheme'] = kwargs['cssfile']
        theming.saveTheme()
        raise cherrypy.HTTPRedirect('/settings/theming')

    @cherrypy.expose
    def ip_geolocate(self, **kwargs):
        pages.require("/admin/settings.edit", noautoreturn=True)
        pages.postOnly()
        from . import geolocation
        l = geolocation.ip_geolocate()
        geolocation.setDefaultLocation(
            l['lat'], l['lon'], l['city'], l['timezone'], l['regionName'], l['countryCode'])
        messagebus.post_message(
            "/system/settings/changedelocation", pages.getAcessingUser())
        raise cherrypy.HTTPRedirect('/settings/system')

    @cherrypy.expose
    def processes(self):
        pages.require("/admin/settings.view")
        return pages.get_template("settings/processes.html").render()

    @cherrypy.expose
    def dmesg(self):
        pages.require("/admin/settings.view")
        return pages.get_template("settings/dmesg.html").render()

    @cherrypy.expose
    def environment(self):
        pages.require("/admin/settings.view")
        return pages.get_template("settings/environment.html").render()

    gpio = gpio.WebInterface()

    class profiler():
        @cherrypy.expose
        def index():
            pages.require("/admin/settings.edit")
            return pages.get_template("settings/profiler/index.html").render(sort='')

        @cherrypy.expose
        def bytotal():
            pages.require("/admin/settings.edit")
            return pages.get_template("settings/profiler/index.html").render(sort='total')

        @cherrypy.expose
        def start():
            pages.require("/admin/settings.edit", noautoreturn=True)
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
                "/system/settings/activatedprofiler", pages.getAcessingUser())
            raise cherrypy.HTTPRedirect("/settings/profiler")

        @cherrypy.expose
        def stop():
            pages.require("/admin/settings.edit", noautoreturn=True)
            pages.postOnly()
            import yappi
            if yappi.is_running():
                yappi.stop()
            raise cherrypy.HTTPRedirect("/settings/profiler")

        @cherrypy.expose
        def clear():
            pages.require("/admin/settings.edit", noautoreturn=True)
            pages.postOnly()
            import yappi
            yappi.clear_stats()
            raise cherrypy.HTTPRedirect("/settings/profiler/")
