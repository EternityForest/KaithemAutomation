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
import scullery.persist
from typing import Any

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
from . import gpio
from . import theming

from . import version_info

from . import astrallibwrapper as sky

bootTime = time.time()

# Persist is one of the ones that we want to be usable outside of kaithem, so we add our path resolution stuff here.


def resolvePath(fn, expand=False):
    if not fn.startswith(os.pathsep) or fn.startswith("~") or fn.startswith("$"):
        fn = os.path.join(directories.moduledatadir, fn)

    return (os.path.expandvars(os.path.expanduser(fn))) if expand else fn


persist.resolvePath = resolvePath

# This exception is what we raise from within the page handler to serve a static file


ServeFileInsteadOfRenderingPageException = pages.ServeFileInsteadOfRenderingPageException

plugins = weakref.WeakValueDictionary()


class TagInterface():
    def __getitem__(self, k):
        try:
            x = tagpoints.allTagsAtomic[k]()
            if not x:
                return tagpoints.Tag(k)
            return x
        except KeyError:
            return tagpoints.Tag(k)

    def StringTag(self, k):
        t = tagpoints.StringTag(k)
        return t

    def ObjectTag(self, k):
        t = tagpoints.ObjectTag(k)
        return t

    def BinaryTag(self, k):
        t = tagpoints.BinaryTag(k)
        return t

    def __iter__(self):
        return tagpoints.allTagsAtomic

    TagClass = tagpoints._TagPoint
    #HysteresisFilter = tagpoints.HysteresisFilter
    LowpassFilter = tagpoints.LowpassFilter
    HighpassFilter = tagpoints.HighpassFilter


class SoundOutput():
    pass


from . import scriptbindings

class Kaithem():
    devices = devices.DeviceNamespace()
    context = threading.local()
    tags = TagInterface()
    chandlerscript = scriptbindings

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
        getType = unitsofmeasure.getUnitType
        define = unitsofmeasure.defineUnit

    class users(object):
        @staticmethod
        def checkPermission(user, permission):
            try:
                if pages.canUserDoThis(permission, user):
                    return True
                else:
                    return False
            except KeyError:
                return False

    class alerts(object):
        Alert = alerts.Alert

    class gpio():
        DigitalInput = gpio.DigitalInput
        DigitalOutput = gpio.DigitalOutput
        PWMOutput = gpio.PWMOutput

    class logging(object):
        @staticmethod
        def flushsyslog():
            import pylogginghandler
            pylogginghandler.syslogger.flush()

    class mqtt(object):
        @staticmethod
        def Connection(server, port=1883, password=None, alertPriority="info", alertAck=True, messageBusName=None, connectionID=None):
            from . import mqtt as mqttPatch
            from scullery import mqtt
            return mqtt.getConnection(server=server, port=port, password=password, alertPriority=alertPriority, alertAck=alertAck, messageBusName=messageBusName, connectionID=connectionID)

        @staticmethod
        def listConnections():
            from . import mqtt as mqttPatch
            from scullery import mqtt
            return mqttPatch.listConnections()

    class misc(object):

        version = version_info.__version__
        version_info = version_info.__version_info__

        @staticmethod
        def lorem():
            return(random.choice(sentences))
            # return ("""lorem ipsum dolor sit amet, consectetur adipiscing elit. Proin vitae laoreet eros. Integer nunc nisl, ultrices et commodo sit amet, dapibus vitae sem. Nam vel odio metus, ac cursus nulla. Pellentesque scelerisque consequat massa, non mollis dolor commodo ultrices. Vivamus sit amet sapien non metus fringilla pretium ut vitae lorem. Donec eu purus nulla, quis venenatis ipsum. Proin rhoncus laoreet ullamcorper. Etiam fringilla ligula ut erat feugiat et pulvinar velit fringilla.""")

        @staticmethod
        def do(f):
            workers.do(f)

        @staticmethod
        def location():
            lat, lon = geolocation.getCoords()
            if not lon or not lat:
                raise RuntimeError("No location set")
            return((lat, lon))

        @staticmethod
        def uptime():
            return time.time() - bootTime

        @staticmethod
        def errors(f):
            try:
                f()
            except Exception as e:
                return e
            return None

        @staticmethod
        def breakpoint():
            breakpoint.breakpoint()

        @staticmethod
        def mkdir(d):
            util.ensure_dir2(d)

        effwords = util.eff_wordlist

        vardir = directories.vardir
        datadir = directories.datadir



    # In modules.py, we insert a resource API object.
    #kaithemobj.kaithem.resource = ResourceAPI()

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
            return(unitsofmeasure.Month())

        @staticmethod
        def day():
            return(time.localtime().tm_mday)

        @staticmethod
        def year():
            return(time.localtime().tm_year)

        @staticmethod
        def hour():
            return(time.localtime().tm_hour)

        @staticmethod
        def minute():
            return(time.localtime().tm_min)

        @staticmethod
        def second():
            return(time.localtime().tm_sec)

        @staticmethod
        def isdst(self):
            # It returns 1 or 0, cast to bool because that's just weird.
            return(bool(time.localtime().tm_isdst))

        @staticmethod
        def dayofweek():
            return (unitsofmeasure.DayOfWeek())

        @staticmethod
        def sunsetTime(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.sunset(lat, lon, date))

        @staticmethod
        def sunriseTime(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.sunrise(lat, lon, date))

        @staticmethod
        def civilDuskTime(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.dusk(lat, lon, date))

        @staticmethod
        def civilDawnTime(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.dawn(lat, lon, date))

        @staticmethod
        def rahuStart(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.rahu(lat, lon, date)[0])

        @staticmethod
        def rahuEnd(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.rahu(lat, lon, date)[1])

        @staticmethod
        def isDark(lat=None, lon=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings")

            return (sky.isDark(lat, lon))

        @staticmethod
        def isRahu(lat=None, lon=None):
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
        def isDay(lat=None, lon=None):
            if lat is None:
                if lon is None:
                    lat, lon = geolocation.getCoords()

                if lat is None or lon is None:
                    raise RuntimeError(
                        "No server location set, fix this in system settings")
            return (sky.isDay(lat, lon))

        @staticmethod
        def isNight(lat=None, lon=None):
            if lat is None:
                if lon is None:
                    lat, lon = geolocation.getCoords()

                if lat is None or lon is None:
                    raise RuntimeError(
                        "No server location set, fix this in system settings")
            return (sky.isNight(lat, lon))

        @staticmethod
        def isLight(lat=None, lon=None):
            if lat is None:
                if lon is None:
                    lat, lon = geolocation.getCoords()

                if lat is None or lon is None:
                    raise RuntimeError(
                        "No server location set, fix this in system settings")
            return (sky.isLight(lat, lon))

        @staticmethod
        def moonPhase():
            return sky.moon()

        @staticmethod
        def moonPercent():
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
        def lsdirs(path):
            return util.get_immediate_subdirectories(path)

        @staticmethod
        def lsfiles(path):
            return util.get_files(path)

        @staticmethod
        def which(exe):
            return util.which(exe)

        @staticmethod
        def sensors():
            try:
                if util.which('sensors'):
                    return (subprocess.check_output('sensors').decode('utf8'))
                else:
                    return('"sensors" command failed(lm_sensors not available)')
            except Exception:
                return('sensors call failed')


    class states(object):
        StateMachine = statemachines.StateMachine

    class web(object):
        # TODO: Deprecate webresource stuff
        @staticmethod
        def resource(name):
            return pages.webResources[name].url

        controllers = pages.nativeHandlers

        navBarPlugins = pages.navBarPlugins

        theming = theming

        @staticmethod
        def freeboard(page, kwargs, plugins=[]):
            "Returns the ready-to-embed code for freeboard.  Used to unclutter user created pages that use it."
            if cherrypy.request.method == "POST":
                import re
                import html
                pages.require("/admin/modules.edit")
                c = re.sub(r"<\s*freeboard-data\s*>[\s\S]*<\s*\/freeboard-data\s*>", "<freeboard-data>\n" + html.escape(
                    yaml.dump(json.loads(kwargs['bd']))) + "\n</freeboard-data>", page.getContent())
                page.setContent(c)
            else:
                return pages.get_template("freeboard/app.html").render(plugins=plugins)

        @staticmethod
        def unurl(s):
            return util.unurl(s)

        @staticmethod
        def url(s):
            return util.url(s)

        @staticmethod
        def goBack():
            raise cherrypy.HTTPRedirect(cherrypy.request.headers['Referer'])

        @staticmethod
        def goto(url):
            raise cherrypy.HTTPRedirect(url)

        @staticmethod
        def serveFile(*a, **k):
            pages.serveFile(*a, **k)

        @staticmethod
        def user():
            x = pages.getAcessingUser()
            if x:
                return x
            else:
                return ''

        @staticmethod
        def hasPermission(permission):
            return pages.canUserDoThis(permission)

    midi = midi.MidiAPI()

    class sound(object):

        builtinSounds = sound.builtinSounds
        resolveSound = sound.resolveSound

        oggTest = sound.oggSoundTest

        directories = config.config['audio-paths']

        @staticmethod
        def outputs():
            try:
                from . import jackmanager
                # Always
                try:
                    x = [i.name for i in jackmanager.getPorts(
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
        def play(*args, **kwargs):
            sound.playSound(*args, **kwargs)

        @staticmethod
        def stop(*args, **kwargs):
            sound.stopSound(*args, **kwargs)

        @staticmethod
        def pause(*args, **kwargs):
            sound.pause(*args, **kwargs)

        @staticmethod
        def resume(*args, **kwargs):
            sound.resume(*args, **kwargs)

        @staticmethod
        def stopAll():
            sound.stopAllSounds()

        @staticmethod
        def isPlaying(*args, **kwargs):
            return sound.isPlaying(*args, **kwargs)

        @staticmethod
        def position(*args, **kwargs):
            return sound.position(*args, **kwargs)

        @staticmethod
        def setvol(*args, **kwargs):
            return sound.setvol(*args, **kwargs)

        @staticmethod
        def setEQ(*args, **kwargs):
            return sound.setEQ(*args, **kwargs)

        @staticmethod
        def fadeTo(*args, **kwargs):
            return sound.fadeTo(*args, **kwargs)

        @staticmethod
        def preload(*args, **kwargs):
            return sound.preload(*args, **kwargs)

    class message():
        @staticmethod
        def post(topic, message):
            messagebus.postMessage(topic, message)

        @staticmethod
        def subscribe(topic, callback):
            messagebus.subscribe(topic, callback)

        @staticmethod
        def unsubscribe(topic, callback):
            messagebus.unsubscribe(topic, callback)

    class pymessage():
        @staticmethod
        def post(topic, message):
            messagebus.pyPostMessage(topic, message)

        @staticmethod
        def subscribe(topic, callback):
            messagebus.pySubscribe(topic, callback)

    class persist():
        unsaved = scullery.persist.unsavedFiles

        @staticmethod
        def load(*args, **kwargs):
            return persist.load(*args, **kwargs)

        @staticmethod
        def save(*args, **kwargs):
            return persist.save(*args, **kwargs)

    class string():
        @staticmethod
        def usrstrftime(*a):
            return unitsofmeasure.strftime(*a)

        @staticmethod
        def SIFormat(number, d=2):
            return unitsofmeasure.siFormatNumber(number, d)

        @staticmethod
        def formatTimeInterval(s, places=2, clock=False):
            return unitsofmeasure.formatTimeInterval(s, places, clock)

    class events():
        pass
        # Stuff gets inserted here externally


class obj():
    pass


Kaithem.widget = widgets
Kaithem.globals = obj()  # this is just a place to stash stuff.


# This is a global instance but we are moving away from that
kaithem = Kaithem()

if config.config['quotes-file'] == 'default':
    sentences = kaithem.persist.load(
        os.path.join(directories.datadir, "quotes.yaml"))
else:
    sentences = kaithem.persist.load(config.config['quotes-file'])
