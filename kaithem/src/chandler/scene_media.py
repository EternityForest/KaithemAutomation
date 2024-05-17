from __future__ import annotations

import base64
import os
import traceback
from typing import TYPE_CHECKING

from icemedia import sound_player
from tinytag import TinyTag

from .soundmanager import fadeSound, play_sound, stop_sound

if TYPE_CHECKING:
    from . import scenes


class SceneMediaPlayer:
    def __init__(self, scene: scenes.Scene):
        self.scene = scene
        self.cue = None

    def next(self, cue: scenes.Cue):
        "Call this whenever the media changes"

        if self.cue:
            oldSoundOut = self.cue.sound_output
        else:
            oldSoundOut = None
        if not oldSoundOut:
            oldSoundOut = self.scene.sound_output

        self.cue = cue

        if not cue.sound == "__keep__":
            # Don't stop audio of we're about to crossfade to the next track
            if not (self.scene.crossfade and cue.sound):
                if self.scene.cue.sound_fade_out or self.scene.cue.media_wind_down:
                    fadeSound(
                        None,
                        length=self.scene.cue.sound_fade_out,
                        handle=str(self.scene.id),
                        winddown=self.scene.evalExprFloat(self.scene.cue.media_wind_down or 0),
                    )
                else:
                    stop_sound(str(self.scene.id))
            # There is no next sound so crossfade to silence
            if self.scene.crossfade and (not cue.sound):
                if self.scene.cue.sound_fade_out or self.scene.cue.media_wind_down:
                    fadeSound(
                        None,
                        length=self.scene.cue.sound_fade_out,
                        handle=str(self.scene.id),
                        winddown=self.scene.evalExprFloat(self.scene.cue.media_wind_down or 0),
                    )
                else:
                    stop_sound(str(self.scene.id))

            self.scene.media_link.allowed_remote_media_url = None

            out: str | None = cue.sound_output

            if not out:
                out = self.scene.sound_output
            if not out:
                out = None

            if oldSoundOut == "scenewebplayer" and not out == "scenewebplayer":
                self.scene.media_link_socket.send(["volume", self.scene.alpha])
                self.scene.media_link_socket.send(
                    [
                        "mediaURL",
                        None,
                        self.scene.entered_cue,
                        max(0, cue.fade_in or self.scene.crossfade),
                    ]
                )

            if cue.sound and self.scene.active:
                sound = cue.sound
                try:
                    self.scene.cueVolume = min(
                        5,
                        max(
                            0,
                            self.scene.evalExprFloat(cue.sound_volume or 1),
                        ),
                    )
                except Exception:
                    self.scene.event(
                        "script.error",
                        self.scene.name + " in cueVolume eval:\n" + traceback.format_exc(),
                    )
                    self.scene.cueVolume = 1
                try:
                    sound = self.scene.resolve_sound(sound)
                except Exception:
                    print(traceback.format_exc())

                if os.path.isfile(sound):
                    if not out == "scenewebplayer":
                        # Always fade in if the face in time set.
                        # Also fade in for crossfade,
                        # but in that case we only do it if there is something to fade in from.

                        spd = self.scene.script_context.preprocessArgument(cue.media_speed)
                        spd = spd or 1
                        spd = float(spd)

                        if not (
                            (((self.scene.crossfade > 0) and not (cue.sound_fade_in < 0)) and sound_player.is_playing(str(self.scene.id)))
                            or (cue.fade_in > 0)
                            or (cue.sound_fade_in > 0)
                            or cue.media_wind_up
                            or self.scene.cue.media_wind_down
                        ):
                            play_sound(
                                sound,
                                handle=str(self.scene.id),
                                volume=self.scene.alpha * self.scene.cueVolume,
                                output=out,
                                loop=cue.sound_loops,
                                start=self.scene.evalExprFloat(cue.sound_start_position or 0),
                                speed=spd,
                            )
                        else:
                            fade = cue.fade_in or cue.sound_fade_in or self.scene.crossfade
                            # Odd cases where there's a wind up but specifically disabled fade
                            if cue.sound_fade_in < 0:
                                fade = 0.1

                            fadeSound(
                                sound,
                                length=max(fade, 0.1),
                                handle=str(self.scene.id),
                                volume=self.scene.alpha * self.scene.cueVolume,
                                output=out,
                                loop=cue.sound_loops,
                                start=self.scene.evalExprFloat(cue.sound_start_position or 0),
                                windup=self.scene.evalExprFloat(cue.media_wind_up or 0),
                                winddown=self.scene.evalExprFloat(self.scene.cue.media_wind_down or 0),
                                speed=spd,
                            )

                    else:
                        self.scene.media_link.allowed_remote_media_url = sound
                        self.scene.media_link_socket.send(["volume", self.scene.alpha])
                        self.scene.media_link_socket.send(
                            [
                                "mediaURL",
                                sound,
                                self.scene.entered_cue,
                                max(0, cue.fade_in or self.scene.crossfade),
                            ]
                        )

                    try:
                        soundMeta = TinyTag.get(sound, image=True)

                        currentAudioMetadata = {
                            "title": soundMeta.title or "Unknown",
                            "artist": soundMeta.artist or "Unknown",
                            "album": soundMeta.album or "Unknown",
                            "year": soundMeta.year or "Unknown",
                        }
                        album_art = soundMeta.get_image()
                    except Exception:
                        # Not support, but it might just be an unsupported type.
                        # if mp3, its a real error, we should alert
                        if sound.endswith(".mp3"):
                            self.scene.event(
                                "error",
                                "Reading metadata for: " + sound + traceback.format_exc(),
                            )
                        album_art = None
                        currentAudioMetadata = {
                            "title": "",
                            "artist": "",
                            "album": "",
                            "year": "",
                        }

                    self.scene.cueInfoTag.value = {"audio.meta": currentAudioMetadata}

                    if album_art and len(album_art) < 3 * 10**6:
                        self.scene.albumArtTag.value = "data:image/jpeg;base64," + base64.b64encode(album_art).decode()
                    else:
                        self.scene.albumArtTag.value = ""

                else:
                    self.scene.event("error", "File does not exist: " + sound)

    def stop(self):
        stop_sound(str(self.scene.id))
