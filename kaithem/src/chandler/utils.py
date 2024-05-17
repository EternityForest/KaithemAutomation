import os
import traceback

from tinytag import TinyTag

from .core import disallow_special, getSoundFolders
from .cue import fnToCueName
from .scenes import Scene


def new_cue_from_sound(scene: Scene, snd: str, name=None):
    bn = os.path.basename(snd)
    bn = fnToCueName(bn)
    try:
        tags = TinyTag.get(snd)
        if tags.artist and tags.title:
            bn = tags.title + " ~ " + tags.artist
    except Exception:
        print(traceback.format_exc())

    bn = disallow_special(bn, "_~", replaceMode=" ")
    if bn not in scene.cues:
        scene.add_cue(bn)
        scene.cues[bn].rel_length = True
        scene.cues[bn].length = 0.01

        soundfolders = getSoundFolders()
        s = None
        for i in soundfolders:
            s = snd
            # Make paths relative to a sound folder
            if not i.endswith("/"):
                i = i + "/"
            if s.startswith(i):
                s = s[len(i) :]
                break
        if not s:
            raise RuntimeError("Unknown, linter said was possible")
        scene.cues[bn].sound = s
        scene.cues[bn].named_for_sound = True
