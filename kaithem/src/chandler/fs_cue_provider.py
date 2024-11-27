import copy
import os
import re

import structlog
import yaml

from .core import disallow_special
from .cue import Cue, CueProvider, fnToCueName

sound_extensions = (
    ".mp3",
    ".m4a",
    ".ogg",
    ".wav",
    ".wma",
    ".opus",
    ".flac",
    ".aac",
)
video_extensions = (
    ".mp4",
    ".mov",
    ".webm",
    ".mpg",
    ".mpeg",
    ".avi",
    ".mkv",
    ".webp",
)
image_extensions = (".png", ".jpeg", ".jpg", ".gif", ".svg")

media_extensions = (
    sound_extensions + video_extensions + image_extensions + (".cue.yaml",)
)

logger = structlog.get_logger(__name__)


def get_number_from_fn(fn):
    r = re.match(r"[:alpha:][:alpha:]?([0-9]+\.?[0-9]*)", fn)
    if r:
        return int(float(r.group(1)) * 1000)

    return None


class FilesystemCueProvider(CueProvider):
    def __init__(self, url: str, *a, **k):
        super().__init__(url, *a, **k)
        self.dir = url.split("://")[1].split("?")[0]
        self.query_string = url.split("://")[1].split("?")[1]

        self.cue_source_files = {}

        # Save auto generated stuff so we know what's user generated
        self.data_as_imported = {}

        if not os.path.isdir(self.dir):
            raise RuntimeError(
                "Cue provider directory does not exist: " + self.dir
            )

    def validate_property_update(self, cue: Cue, prop: str, value):
        if prop == "name":
            if cue.name and cue.name != value:
                raise RuntimeError("Name is linked to imported file")

        if prop == "sound":
            if cue.sound and cue.sound != value:
                raise RuntimeError("Sound is linked to imported file")

        if prop == "slide":
            if cue.slide and cue.slide != value:
                raise RuntimeError("Slide is linked to imported file")

        if prop == "number":
            fn = self.cue_source_files[cue.id]
            n = get_number_from_fn(fn)
            if n:
                if cue.number and cue.number != value:
                    raise RuntimeError("Cue is numbered by its filename")

        return super().validate_property_update(cue, prop, value)

    def get_dir_for_cue(self, cue: Cue) -> str | None:
        if cue.id in self.cue_source_files:
            return os.path.dirname(self.cue_source_files[cue.id])

    def scan_cues(self) -> dict[str, Cue]:
        cues = {}
        discovered = []
        for root, dirs, files in os.walk(self.dir):
            # Sorted because we want the media file to come before the bare YAML
            # That will have fn.cue.yaml and be longer than the main
            for i in files:
                if not i.startswith("."):
                    n = get_number_from_fn(i)
                    discovered.append((n or 10**9, root, i))

        for number, root, i in sorted(discovered):
            if len(cues) > 8192 * 4:
                break

            if i.endswith(media_extensions):
                name = ".".join(i.split(".")[:-1])
                if not name:
                    continue
                fn = os.path.join(root, i)
                id = "file://" + fn
                id = fnToCueName(id)
                id = disallow_special(id, replaceMode="_")

                slide = ""
                sound = ""
                if "slide" in self.query_string:
                    slide = i
                if "sound" in self.query_string:
                    sound = i

                if fn.endswith(sound_extensions) or fn.endswith(
                    video_extensions
                ):
                    length = 0.01
                    rel_len = True
                else:
                    length = 0
                    rel_len = False

                try:
                    name = fnToCueName(name)
                except Exception:
                    logger.info("Skipping:  " + name)
                    continue

                data = {
                    "name": name,
                    "id": id,
                    "sound": sound,
                    "slide": slide,
                    "length": length,
                    "rel_length": rel_len,
                }
                self.data_as_imported[id] = copy.deepcopy(data)

                if os.path.exists(fn + ".cue.yaml"):
                    with open(fn + ".cue.yaml") as f:
                        y = yaml.safe_load(f)
                        if y is not None:
                            data.update(y)

                if "name" in data:
                    name = data["name"]

                if (id not in cues) and (name not in self.group.cues):
                    if number is None:
                        number = self.group.cues_ordered[-1].number + 5000
                        number = max(number, 10**6)
                    if "number" not in data:
                        data["number"] = number

                    cues[name] = Cue(self.group, **data, provider=self.url)
                    self.cue_source_files[cues[name].id] = fn

                else:
                    if name in self.discovered_cues:
                        cues[name] = self.discovered_cues[name]
                        self.cue_source_files[cues[name].id] = fn

        self.discovered_cues = cues

        return cues

    def delete_saved_user_cue_data(self, cue: Cue):
        if cue.id in self.cue_source_files:
            fn = self.cue_source_files[cue.id] + ".cue.yaml"
            if os.path.exists(fn):
                os.remove(fn)

    def save_cue(self, cue: Cue):
        id = cue.id

        if id not in self.cue_source_files:
            cn = cue.name
            cn = disallow_special(cn, replaceMode="_")
            self.cue_source_files[id] = (
                cue.name.replace("/", "_")
                .replace(" ", "_")
                .replace(".", "_")
                .replace("~", "_")
            )

        fn = self.cue_source_files[id]

        d = cue.serialize()

        d.pop("id", None)
        d.pop("provider", None)

        # Remove any properties that haven't been modified
        if id in self.data_as_imported:
            for i in self.data_as_imported[id]:
                if i in d:
                    if d[i] == self.data_as_imported[id][i]:
                        d.pop(i)

        if fn.split(".")[-1] in video_extensions:
            d.pop("slide", None)

        if fn.split(".")[-1] in sound_extensions:
            d.pop("sound", None)

        # Number set by the filename
        if cue.number == get_number_from_fn(fn):
            d.pop("number", None)

        # Number is one of the high up millions ones.
        if cue.number >= 10**6:
            d.pop("number", None)

        x = fn + ".cue.yaml"

        if d:
            with open(x, "w") as f:
                yaml.dump(d, f)
        else:
            if os.path.exists(x):
                if not x.endswith(".cue.yaml"):
                    raise RuntimeError("Super defensive coding here")
                os.remove(x)
