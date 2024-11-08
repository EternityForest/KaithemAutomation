# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

"""This is the global general purpose utility thing that is accesable from almost anywhere in user code."""

import os
import subprocess
import threading
import time
import traceback
import weakref
from typing import Any, Callable, Dict, List, Optional

from icemedia import sound_player as sound
from scullery import persist as sculleryPersist

from kaithem.api import util as apiutil
from kaithem.api import web as webapi

from . import (
    alerts,
    assetlib,
    breakpoint,
    config,
    devices,
    directories,
    geolocation,
    messagebus,
    pages,
    persist,
    scriptbindings,
    tagfilters,
    tagpoints,
    unitsofmeasure,
    util,
    widgets,
    workers,
)
from . import astrallibwrapper as sky

bootTime = time.time()


# Persist is one of the ones that we want to be usable outside of kaithem, so we add our path resolution stuff here.


def resolve_path(fn: str, expand: bool = False):
    if not fn.startswith((os.pathsep, "~", "$")):
        fn = os.path.join(directories.vardir, fn)

    return (os.path.expandvars(os.path.expanduser(fn))) if expand else fn


persist.resolve_path = resolve_path

# This exception is what we raise from within the page handler to serve a static file


ServeFileInsteadOfRenderingPageException = (
    pages.ServeFileInsteadOfRenderingPageException
)

plugins = weakref.WeakValueDictionary()


class TagInterface:
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
    LowpassFilter = tagfilters.LowpassFilter
    HighpassFilter = tagfilters.HighpassFilter


class SoundOutput:
    pass


class Kaithem:
    devices = devices.DeviceNamespace()
    context = threading.local()
    tags = TagInterface()

    widget = widgets

    assetpacks = assetlib.AssetPacks(os.path.join(directories.vardir, "assets"))

    def __init__(self):
        self.globals = obj()  # this is just a place to stash stuff

    def __getattr__(self, name):
        if name in plugins:
            return plugins[name]
        else:
            raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        plugins[name] = value

    class units:
        convert = unitsofmeasure.convert
        units = unitsofmeasure.units
        define = unitsofmeasure.define_unit

    class users:
        @staticmethod
        def check_permission(user, permission: str):
            try:
                if pages.canUserDoThis(permission, user):
                    return True
                else:
                    return False
            except KeyError:
                return False

    class alerts:
        Alert = alerts.Alert

    class chandlerscript:
        ChandlerScriptContext = scriptbindings.ChandlerScriptContext
        context_info = scriptbindings.context_info
        get_function_info = scriptbindings.get_function_info

    class logging:
        @staticmethod
        def flushsyslog():
            import pylogginghandler

            pylogginghandler.syslogger.flush()

    class misc:
        @staticmethod
        def lorem() -> str:
            return apiutil.lorem()

        @staticmethod
        def do(f: Callable[..., Any]) -> None:
            workers.do(f)

        @staticmethod
        def location() -> tuple[float, float]:
            lat, lon = geolocation.getCoords()
            if not lon or not lat:
                raise RuntimeError("No location set")
            return (lat, lon)

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

        vardir = directories.vardir
        datadir = directories.datadir

    # In modules.py, we insert a resource API object.
    # kaithemobj.kaithem.resource = ResourceAPI()

    class time:
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
        def uptime():
            return time.time() - bootTime

        @staticmethod
        def strftime(*args):
            return unitsofmeasure.strftime(*args)

        @staticmethod
        def sunset_time(
            lat: Optional[float] = None, lon: Optional[float] = None, date=None
        ):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings"
                )

            return sky.sunset(lat, lon, date)

        @staticmethod
        def sunrise_time(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings"
                )

            return sky.sunrise(lat, lon, date)

        @staticmethod
        def civil_dusk_time(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings"
                )

            return sky.dusk(lat, lon, date)

        @staticmethod
        def civil_dawn_time(lat=None, lon=None, date=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings"
                )

            return sky.dawn(lat, lon, date)

        @staticmethod
        def is_dark(lat=None, lon=None):
            if lon is None:
                lat, lon = geolocation.getCoords()

            else:
                raise ValueError("You set lon, but not lst?")
            if lat is None or lon is None:
                raise RuntimeError(
                    "No server location set, fix this in system settings"
                )

            return sky.is_dark(lat, lon)

        @staticmethod
        def is_day(lat=None, lon=None):
            if lat is None:
                if lon is None:
                    lat, lon = geolocation.getCoords()

                if lat is None or lon is None:
                    raise RuntimeError(
                        "No server location set, fix this in system settings"
                    )
            return sky.is_day(lat, lon)

        @staticmethod
        def is_night(lat=None, lon=None):
            if lat is None:
                if lon is None:
                    lat, lon = geolocation.getCoords()

                if lat is None or lon is None:
                    raise RuntimeError(
                        "No server location set, fix this in system settings"
                    )
            return sky.is_night(lat, lon)

        @staticmethod
        def is_light(lat=None, lon=None):
            if lat is None:
                if lon is None:
                    lat, lon = geolocation.getCoords()

                if lat is None or lon is None:
                    raise RuntimeError(
                        "No server location set, fix this in system settings"
                    )
            return sky.is_light(lat, lon)

        @staticmethod
        def moon_age():
            return sky.moon_age()

        @staticmethod
        def moon_percent():
            return sky.moon_illumination()

    class sys:
        @staticmethod
        def sensors():
            try:
                if util.which("sensors"):
                    return subprocess.check_output("sensors").decode("utf8")
                else:
                    return '"sensors" command failed(lm_sensors not available)'
            except Exception:
                return "sensors call failed"

    web = webapi

    class sound:
        resolve_sound = sound.resolve_sound

        test = sound.test
        ogg_test = sound.test

        directories = config.config["audio_paths"]

        @staticmethod
        def outputs() -> List[str]:
            try:
                from . import jackmanager

                # Always
                try:
                    x = [
                        i.name
                        for i in jackmanager.get_ports(
                            is_audio=True, is_input=True
                        )
                    ]
                except Exception:
                    print(traceback.format_exc())
                    x = []

                prefixes = {}
                op = []

                for i in x:
                    if i.split(":")[0] not in prefixes:
                        prefixes[i.split(":")[0]] = i
                        op.append(i.split(":")[0])
                    op.append(i)

                return [""] + op
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
            speed: float = 1,
        ):
            sound.play_sound(
                filename=filename,
                handle=handle,
                extraPaths=extraPaths,
                volume=volume,
                output=output,
                loop=loop,
                start=start,
                speed=speed,
            )

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
            speed: float = 1,
        ):
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
                speed=speed,
            )

        @staticmethod
        def preload(*args, **kwargs):
            pass
            # TODO Make this work again
            # return sound.preload(*args, **kwargs)

    class message:
        @staticmethod
        def post(topic: str, message: Any):
            messagebus.post_message(topic, message)

        @staticmethod
        def subscribe(topic: str, callback: Callable[..., Any]):
            messagebus.subscribe(topic, callback)

        @staticmethod
        def unsubscribe(topic: str, callback: Callable[..., Any]):
            messagebus.unsubscribe(topic, callback)

    class persist:
        unsaved = sculleryPersist.unsavedFiles

        @staticmethod
        def load(
            fn: str, *args: tuple[Any], **kwargs: Dict[str, Any]
        ) -> bytes | str | Dict[Any, Any] | List[Any]:
            return persist.load(fn, *args, **kwargs)

        @staticmethod
        def save(
            data: bytes | str | Dict[Any, Any] | List[Any],
            fn: str,
            *args: tuple[Any],
            **kwargs: Dict[str, Any],
        ):
            return persist.save(data, fn, *args, **kwargs)

    class string:
        @staticmethod
        def usrstrftime(*a):
            return unitsofmeasure.strftime(*a)

        @staticmethod
        def si_format(number, d=2):
            return unitsofmeasure.si_format_number(number, d)

        @staticmethod
        def format_time_interval(s, places=2, clock=False):
            return unitsofmeasure.format_time_interval(s, places, clock)

    class events:
        pass
        # Stuff gets inserted here externally


class obj:
    pass


# This is a global instance but we are moving away from that
kaithem = Kaithem()

# Moving away from the thin time wrapper stuff to just astro stuff
kaithem.sky = kaithem.time
