import os

from icemedia import sound_player as sound  # noqa: F401

# TODO legacy
from icemedia.sound_player import *  # noqa

from . import config, directories, messagebus, util


def init():
    # Todo move sound init to it's own thing
    if "dummy" in sound.backend.backendname.lower():
        messagebus.post_message(
            "/system/notifications/errors",
            "Using a dummy sound backend. Suggest installing MPV if you want sound",
        )

    def resolver(fn):
        for i in os.listdir(os.path.join(directories.vardir, "modules", "data")):
            p = os.path.join(directories.vardir, "modules", "data", i, "__filedata__", "media")
            filename = util.search_paths(fn, [p])
            if filename:
                break

    sound.media_resolvers["kaithem_module"] = resolver

    sound.media_paths.append(os.path.join(directories.vardir, "static"))
    sound.media_paths.append(os.path.join(directories.vardir, "assets"))
    sound.select_backend("mpv")

    p = config.config["audio_paths"]
    for i in p:
        if i == "__default__":
            sound.media_paths.append(os.path.join(directories.datadir, "sounds"))
        else:
            sound.media_paths.append(i)
