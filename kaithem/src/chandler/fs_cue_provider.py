import os

import yaml

from .core import disallow_special
from .cue import Cue, CueProvider, fnToCueName

sound_extensions = (".mp3", ".m4a", ".ogg", ".wav", ".wma", ".opus", ".flac", ".aac")
video_extensions = (".mp4", ".mov", ".webm", ".mpg", ".mpeg", ".avi", ".mkv", ".webp")
image_extensions = (".png", ".jpeg", ".jpg", ".gif", ".svg")

media_extensions = sound_extensions + video_extensions + image_extensions + (".cue.yaml",)


class FilesystemCueProvider(CueProvider):
    def __init__(self, url: str, *a, **k):
        super().__init__(url, *a, **k)
        self.dir = url.split("://")[1].split("?")[0]
        self.query_string = url.split("://")[1].split("?")[1]

        self.cue_source_files = {}

        if not os.path.isdir(self.dir):
            raise RuntimeError("Cue provider directory does not exist: " + self.dir)

    def get_dir_for_cue(self, cue: Cue) -> str | None:
        if cue.id in self.cue_source_files:
            return os.path.dirname(self.cue_source_files[cue.id])

    def scan_cues(self) -> dict[str, Cue]:
        cues = {}
        for root, dirs, files in os.walk(self.dir):
            # Sorted because we want the media file to come before the bare YAML
            # That will have fn.cue.yaml and be longer than the main

            for i in sorted(files):
                if len(cues) > 512:
                    break

                if i.endswith(media_extensions):
                    name = ".".join(i.split(".")[:-1])
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

                    if fn.endswith(sound_extensions) or fn.endswith(video_extensions):
                        length = 0.01
                        rel_len = True
                    else:
                        length = 0
                        rel_len = False

                    name = fnToCueName(name)

                    data = {"name": name, "id": id, "sound": sound, "slide": slide, "length": length, "rel_length": rel_len}

                    if os.path.exists(fn + ".cue.yaml"):
                        with open(fn + ".cue.yaml") as f:
                            data.update(yaml.safe_load(f))

                    if "name" in data:
                        name = data["name"]

                    if (id not in cues) and (name not in self.group.cues):
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
            self.cue_source_files[id] = cue.name.replace("/", "_").replace(" ", "_").replace(".", "_").replace("~", "_")

        fn = self.cue_source_files[id]

        with open(fn + ".cue.yaml", "w") as f:
            yaml.dump(cue.serialize(), f)
