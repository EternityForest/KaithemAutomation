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

"""This is the global general purpose utility thing that is accesable from almost anywhere in user code."""

import traceback
from . import tagpoints, geolocation
import time
import random
import subprocess
import threading
import json
import yaml
import os
import weakref
import datetime
from scullery import persist as sculleryPersist

from typing import Any, Callable, Optional, Dict, List

try:
    import holidays
except Exception:
    print("Error importing holidays")

import cherrypy
from . import unitsofmeasure
from . import workers
from . import sound
from . import messagebus
from . import util
from . import widgets
from . import directories
from . import pages
from . import config
from . import persist
from . import breakpoint
from . import statemachines
from . import devices
from . import alerts
from . import midi
from . import theming
from . import assetlib
from kaithem import __version__

from . import astrallibwrapper as sky
from . import scriptbindings


wsgi_apps = []
tornado_apps = []


bootTime = time.time()

# Persist is one of the ones that we want to be usable outside of kaithem, so we add our path resolution stuff here.


def resolve_path(fn: str, expand: bool = False):
    if not fn.startswith(os.pathsep) or fn.startswith("~") or fn.startswith("$"):
        fn = os.path.join(directories.moduledatadir, fn)

    return (os.path.expandvars(os.path.expanduser(fn))) if expand else fn


persist.resolve_path = resolve_path

# This exception is what we raise from within the page handler to serve a static file


ServeFileInsteadOfRenderingPageException = pages.ServeFileInsteadOfRenderingPageException

plugins = weakref.WeakValueDictionary()


class TagInterface():

    @property
    def all_tags_raw(self):
        return tagpoints.allTagsAtomic
    
    def __contains__(self, k: str):
        try:
            x = tagpoints.allTagsAtomic[k]()
            if not x:
                return False
            return True
        except KeyError:
            return False
        
    def __getitem__(self, k: str):
        try:
            x = tagpoints.allTagsAtomic[k]()
            if not x:
                return tagpoints.Tag(k)
            return x
        except KeyError:
            return tagpoints.Tag(k)

    def StringTag(self, k: str) -> tagpoints.StringTagPointClass:
        t = tagpoints.StringTag(k)
        return t

    def ObjectTag(self, k: str) -> tagpoints.ObjectTagPointClass:
        t = tagpoints.ObjectTag(k)
        return t

    def BinaryTag(self, k: str) -> tagpoints.BinaryTagPointClass:
        t = tagpoints.BinaryTag(k)
        return t

    def __iter__(self):
        return tagpoints.allTagsAtomic

    GenericTagPointClass = tagpoints.GenericTagPointClass
    StringTagPointClass = tagpoints.StringTagPointClass
    ObjectTagPointClass = tagpoints.ObjectTagPointClass
    BinaryTagPointClass = tagpoints.BinaryTagPointClass
    NumericTagPointClass = tagpoints.NumericTagPointClass

    # HysteresisFilter = tagpoints.HysteresisFilter
    LowpassFilter = tagpoints.LowpassFilter
    HighpassFilter = tagpoints.HighpassFilter


class SoundOutput():
    pass


class Kaithem():
    devices = devices.DeviceNamespace()
    context = threading.local()
    tags = TagInterface()
    chandlerscript = scriptbindings
    widget = widgets

    assetpacks = assetlib.AssetPacks(
        os.path.join(directories.vardir, 'assets'))

    def __getattr__(self, name):
        if name in plugins:
            return plugins[name]
        else:
            raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        plugins[name] = value

    class units():
        convert = unitsofmeasure.convert
        units = unitsofmeasure.units
        getType = unitsofmeasure.get_unit_type
        define = unitsofmeasure.define_unit

    class users(object):
        @staticmethod
        def check_permission(user, permission: str):
            try:
                if pages.canUserDoThis(permission, user):
                    return True
                else:
                    return False
            except KeyError:
                return False

    class alerts(object):
        Alert = alerts.Alert

    class logging(object):
        @staticmethod
        def flushsyslog():
            import pylogginghandler
            pylogginghandler.syslogger.flush()

    class misc(object):

        version = __version__.__version__
        version_info = __version__.__version_info__

        @staticmethod
        def lorem() -> str:
            return (random.choice(sentences))
            # return ("""lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin vitae laoreet eros. Integer nunc nisl, ultrices et commodo sit amet, dapibus vitae sem. Nam vel odio metus, ac cursus nulla. Pellentesque scelerisque consequat massa, non mollis dolor commodo ultrices. Vivamus sit amet sapien non metus fringilla pretium ut vitae lorem. Donec eu purus nulla, quis venenatis ipsum. Proin rhoncus laoreet ullamcorper. Etiam fringilla ligula ut erat feugiat et pulvinar velit fringilla.""")

        @staticmethod
        def do(f: Callable[..., Any]) -> None:
            workers.do(f)

        @staticmethod
        def location() -> tuple[float, float]:
            lat, lon = geolocation.getCoords()
            if not lon or not lat:
                raise RuntimeError("No location set")
            return ((lat, lon))

        @staticmethod
        def uptime():
            return time.time() - bootTime

        @staticmethod
        def errors(f: Callable):
            try:
                f()
            except Exception as e:
                return e
            return None

        @staticmethod
        def breakpoint():
            breakpoint.breakpoint()

        effwords = util.eff_wordlist

        vardir = directories.vardir
        datadir = directories.datadir

    # In modules.py, we insert a resource API object.
    # kaithemobj.kaithem.resource = ResourceAPI()

    class time(object):

        # @staticmethod
        # def checkHoliday(name, zones=None):
        #     "Return true if the named holiday is happening in any listed zone.  Defaults to server config zone."

        #     if not zones:
        #         l = geolocation.getLocation()['country']
        #         if not l:
        #             return False
        #         zones = [l]

        #     else:
        #         for i in zones:
        #             h = holidays.country_holidays(i)

        #             try:
        #                 h = h[datetime.datetime.now()]
        #             except KeyError:
        #                 False

        #             try:
        #                 if name.replace("'",'').replace(' ','').lower() in h.replace("'",'').replace(' ','').lower():
        #                     return True
        #             except Exception:
        #                 pass

        @staticmethod
        def lantime():
            return time.time()

        @staticmethod
        def uptime():
            return time.time() - bootTime

        @staticmethod
        def strftime(*args):
            return unitsofmeasure.strftime(*args)

        @staticmethod
        def time():
            return time.time()

        @staticmethod
        def month():
            return (unitsofmeasure.Month())

        @staticmethod
        def day():
            return (time.localtime().tm_mday)

        @staticmethod
        def year():
            return (time.localtime().tm_year)

        @staticmethod
        def hour():
            return (time.localtime().tm_hour)

        @staticmethod
        def minute():
            return (time.localtime().tm_min)

        @staticmethod
        def second():
            return (time.localtime().tm_sec)

        @staticmethod
        def isdst():
            # It returns 1 or 0, cast to bool because that's just weird.
            return (bool(time.localtime().tm_isdst))

        @staticmethod
        def dayofweek():
            return (unitsofmeasure.DayOfWeek())

        @staticmethod
        def sunset_time(lat: Optional[float] = None, lon: Optional[float] = None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.sunset(lat, lon, date))

        @staticmethod
        def sunrise_time(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.sunrise(lat, lon, date))

        @staticmethod
        def civil_dusk_time(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.dusk(lat, lon, date))

        @staticmethod
        def civil_dawn_time(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.dawn(lat, lon, date))

        @staticmethod
        def rahu_start(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.rahu(lat, lon, date)[0])

        @staticmethod
        def rahu_end(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.rahu(lat, lon, date)[1])

        @staticmethod
        def is_dark(lat=None, lon=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.isDark(lat, lon))

        @staticmethod
        def is_rahu(lat=None, lon=None):
            if lat is None:
                if lon is None:
                    lat, lon = geolocation.getCoords()

                else:
                    raise ValueError("You set lon, but not lst?")
                if lat is None or lon is None:
                    raise RuntimeError(
                        "No server location set, fix this in system settings")

            return (sky.isRahu(lat, lon))

        @staticmethod
        def is_day(lat=None, lon=None):
            if lat is None:
                if lon is None:
                    lat, lon = geolocation.getCoords()

                if lat is None or lon is None:
                    raise RuntimeError(
                        "No server location set, fix this in system settings")
            return (sky.isDay(lat, lon))

        @staticmethod
        def is_night(lat=None, lon=None):
            if lat is None:
                if lon is None:
                    lat, lon = geolocation.getCoords()

                if lat is None or lon is None:
                    raise RuntimeError(
                        "No server location set, fix this in system settings")
            return (sky.isNight(lat, lon))

        @staticmethod
        def is_light(lat=None, lon=None):
            if lat is None:
                if lon is None:
                    lat, lon = geolocation.getCoords()

                if lat is None or lon is None:
                    raise RuntimeError(
                        "No server location set, fix this in system settings")
            return (sky.isLight(lat, lon))

        @staticmethod
        def moon_phase():
            return sky.moon()

        @staticmethod
        def moon_percent():
            x = sky.moon()
            if x > 14:
                x -= 14
                x = 14 - x

            return 100 * (x / 14.0)

        @staticmethod
        def accuracy():
            return util.timeaccuracy()

    class sys(object):
        @staticmethod
        def shellex(cmd):
            env = {}
            env.update(os.environ)
            return (subprocess.check_output(cmd, shell=True, env=env))

        @staticmethod
        def shellexbg(cmd):
            subprocess.Popen(cmd, shell=True)

        @staticmethod
        def which(exe: str):
            return util.which(exe)

        @staticmethod
        def sensors():
            try:
                if util.which('sensors'):
                    return (subprocess.check_output('sensors').decode('utf8'))
                else:
                    return ('"sensors" command failed(lm_sensors not available)')
            except Exception:
                return ('sensors call failed')

    class states(object):
        StateMachine = statemachines.StateMachine

    class web(object):
        controllers = pages.nativeHandlers

        nav_bar_plugins = pages.nav_bar_plugins

        theming = theming


        @staticmethod
        def add_wsgi_app(pattern: str, app, permission="system_admin"):
            "Mount a WSGI application to handle all URLs matching the pattern regex"
            wsgi_apps.append((pattern, app, permission))

        @staticmethod
        def add_tornado_app(pattern: str, app, args, permission="system_admin"):
            "Mount a Tornado application to handle all URLs matching the pattern regex"
            tornado_apps.append((pattern, app, args, permission))


        @staticmethod
        def freeboard(page, kwargs, plugins=[]):
            "Returns the ready-to-embed code for freeboard.  Used to unclutter user created pages that use it."
            if cherrypy.request.method == "POST":
                import re
                import html
                pages.require("system_admin")
                c = re.sub(r"<\s*freeboard-data\s*>[\s\S]*<\s*\/freeboard-data\s*>", "<freeboard-data>\n" + html.escape(
                    yaml.dump(json.loads(kwargs['bd']))) + "\n</freeboard-data>", page.getContent())
                page.setContent(c)
            else:
                return pages.get_template("freeboard/app.html").render(plugins=plugins)

        @staticmethod
        def go_back():
            raise cherrypy.HTTPRedirect(cherrypy.request.headers['Referer'])

        @staticmethod
        def goto(url):
            raise cherrypy.HTTPRedirect(url)

        @staticmethod
        def serve_file(*a, **k):
            pages.serveFile(*a, **k)

        @staticmethod
        def user():
            x = pages.getAcessingUser()
            if x:
                return x
            else:
                return ''

        @staticmethod
        def has_permission(permission):
            return pages.canUserDoThis(permission)

    midi = midi.MidiAPI()

    class sound(object):

        builtin_sounds = sound.builtinSounds
        resolve_sound = sound.resolve_sound

        ogg_test = sound.ogg_test

        directories = config.config['audio-paths']

        @staticmethod
        def outputs():
            try:
                from . import jackmanager
                # Always
                try:
                    x = [i.name for i in jackmanager.get_ports(
                        is_audio=True, is_input=True)]
                except Exception:
                    print(traceback.format_exc())
                    x = []

                prefixes = {}
                op = []

                for i in x:
                    if not i.split(":")[0] in prefixes:
                        prefixes[i.split(":")[0]] = i
                        op.append(i.split(":")[0])
                    op.append(i)

                return [''] + op
            except Exception:
                print(traceback.format_exc())
                return []

        @staticmethod
        def play(
                filename: str,
                handle: str = "PRIMARY",
                extraPaths: List[str] = [],
                volume: float = 1,
                output: Optional[str] = "",
                loop: float = 1,
                start: float = 0,
                speed: float = 1):

            sound.play_sound(
                filename=filename,
                handle=handle,
                extraPaths=extraPaths,
                volume=volume,
                output=output,
                loop=loop,
                start=start,
                speed=speed
            )

        @staticmethod
        def wait(*args, **kwargs):
            sound.wait(*args, **kwargs)

        @staticmethod
        def stop(handle: str = "PRIMARY"):
            sound.stop_sound(handle)

        @staticmethod
        def pause(*args, **kwargs):
            sound.pause(*args, **kwargs)

        @staticmethod
        def resume(*args, **kwargs):
            sound.resume(*args, **kwargs)

        @staticmethod
        def stop_all():
            sound.stop_all_sounds()

        @staticmethod
        def is_playing(*args, **kwargs):
            return sound.is_playing(*args, **kwargs)

        @staticmethod
        def position(*args, **kwargs):
            return sound.position(*args, **kwargs)

        @staticmethod
        def setvol(*args, **kwargs):
            return sound.setvol(*args, **kwargs)

        @staticmethod
        def fade_to(
            file: str | None,
                length: float = 1.0,
                block: bool = False,
                handle: str = "PRIMARY",
                output: str = "",
                volume: float = 1,
                windup: float = 0,
                winddown: float = 0,
                loop: int = 1,
                start: float = 0,
                speed: float = 1):
            sound.fade_to(
                file,
                length=length,
                block=block,
                handle=handle,
                output=output,
                volume=volume,
                windup=windup,
                winddown=winddown,
                start=start,
                loop=loop,
                speed=speed
            )

        @staticmethod
        def preload(*args, **kwargs):
            pass
            # TODO Make this work again
            # return sound.preload(*args, **kwargs)

    class message():
        @staticmethod
        def post(topic: str, message: Any):
            messagebus.post_message(topic, message)

        @staticmethod
        def subscribe(topic: str, callback: Callable[..., Any]):
            messagebus.subscribe(topic, callback)

        @staticmethod
        def unsubscribe(topic: str, callback: Callable[..., Any]):
            messagebus.unsubscribe(topic, callback)

    class persist():
        unsaved = sculleryPersist.unsavedFiles

        @staticmethod
        def load(fn: str, *args: tuple[Any], **kwargs: Dict[str, Any]) -> bytes | str | Dict[Any, Any] | List[Any]:
            return persist.load(fn, *args, **kwargs)

        @staticmethod
        def save(data: bytes | str | Dict[Any, Any] | List[Any], fn: str, *args: tuple[Any], **kwargs: Dict[str, Any]):
            return persist.save(data, fn, *args, **kwargs)

    class string():
        @staticmethod
        def usrstrftime(*a):
            return unitsofmeasure.strftime(*a)

        @staticmethod
        def si_format(number, d=2):
            return unitsofmeasure.si_format_number(number, d)

        @staticmethod
        def format_time_interval(s, places=2, clock=False):
            return unitsofmeasure.format_time_interval(s, places, clock)

    class events():
        pass
        # Stuff gets inserted here externally


class obj():
    pass


Kaithem.globals = obj()  # this is just a place to stash stuff.


# This is a global instance but we are moving away from that
kaithem = Kaithem()

# Moving away from the thin time wrapper stuff to just astro stuff
kaithem.sky = kaithem.time

if config.config['quotes-file'] == 'default':
    sentences = kaithem.persist.load(
        os.path.join(directories.datadir, "quotes.yaml"))
else:
    sentences = kaithem.persist.load(config.config['quotes-file'])
