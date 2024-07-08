import os

from .cue import Cue, CueProvider, fnToCueName

sound_extensions = (".mp3", ".m4a", ".ogg", ".wav", ".wma", ".opus", ".flac", ".aac")
video_extensions = (".mp4", ".mov", ".webm", ".mpg", ".mpeg", ".avi", ".mkv", ".webp")
image_extensions = (".png", ".jpeg", ".jpg", ".gif", ".svg")

media_extensions = sound_extensions + video_extensions + image_extensions


class FilesystemCueProvider(CueProvider):
    def __init__(self, url: str, *a, **k):
        super().__init__(url, *a, **k)
        self.dir = url.split("://")[1].split("?")[0]
        self.query_string = url.split("://")[1].split("?")[1]
        if not os.path.isdir(self.dir):
            raise RuntimeError("Cue provider directory does not exist: " + self.dir)

    def scan_cues(self) -> dict[str, Cue]:
        cues = {}
        for i in os.listdir(self.dir):
            if i.endswith(".cue.yaml"):
                name = i.split(".cue.yaml")[0]
                fn = os.path.join(self.dir, i)
                id = "file://" + fn
                id = fnToCueName(id)

                if name not in self.group.cues:
                    cues[name] = Cue(self.group, name, id=id, provider=self.url)
                else:
                    cues[name] = self.group.cues[name]

        for i in os.listdir(self.dir):
            if i.endswith(media_extensions):
                name = i.split(".")[0]
                fn = os.path.join(self.dir, i)
                id = "file://" + fn
                id = fnToCueName(id)

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

                if id not in cues and name not in self.group.cues:
                    cues[name] = Cue(
                        self.group, name=name, sound=sound, slide=slide, length=length, rel_length=rel_len, id=id, provider=self.url
                    )
                else:
                    cues[name] = self.group.cues[name]

        return cues

    def delete_saved_user_cue_data(self, cue: Cue):
        pass

    def save_cue(self, cue: Cue):
        pass
