import os
import time

from icemedia import sound_player as sound  # noqa: F401

# TODO legacy
from icemedia.sound_player import *  # noqa
from icemedia.sound_player import is_playing, play_sound

from . import config, directories, messagebus, util


def test(output=None):
    t = "test_" + str(time.time())
    play_sound("alert.ogg", output=output, handle=t)
    for i in range(100):
        if is_playing(t, refresh=True):
            return
        time.sleep(0.01)
    raise RuntimeError("Sound did not report as playing within 1000ms")


sound.test = test


def init():
    # Todo move sound init to it's own thing
    if "dummy" in sound.backend.backendname.lower():
        messagebus.post_message(
            "/system/notifications/errors",
            "Using a dummy sound backend. Suggest installing MPV if you want sound",
        )

    def special_resolver(fn):
        if fn == "alert.ogg":
            return os.path.join(
                directories.datadir,
                "static/sounds/72127__kizilsungur__sweetalertsound3.opus",
            )
        if fn == "error.ogg":
            return os.path.join(
                directories.datadir,
                "static/sounds/423166__plasterbrain__minimalist-sci-fi-ui-error.opus",
            )

    def resolver(fn):
        d = os.path.join(directories.vardir, "modules", "data")
        if os.path.isdir(d):
            for i in os.listdir(d):
                p = os.path.join(
                    directories.vardir,
                    "modules",
                    "data",
                    i,
                    "__filedata__",
                    "media",
                )
                filename = util.search_paths(fn, [p])
                if filename:
                    return filename

    sound.media_resolvers["kaithem_module"] = resolver
    sound.media_resolvers["kaithem_special"] = special_resolver

    sound.media_paths.append(os.path.join(directories.vardir, "static"))
    sound.media_paths.append(os.path.join(directories.vardir, "assets"))
    sound.select_backend("mpv")

    p = config.config["audio_paths"]
    for i in p:
        if i == "__default__":
            sound.media_paths.append(
                os.path.join(directories.datadir, "static", "sounds")
            )
        else:
            sound.media_paths.append(i)
