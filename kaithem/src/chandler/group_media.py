from __future__ import annotations

import base64
import os
import traceback
from typing import TYPE_CHECKING

from icemedia import sound_player
from tinytag import TinyTag

from .soundmanager import fadeSound, play_sound, stop_sound

if TYPE_CHECKING:
    from . import groups


class GroupMediaPlayer:
    def __init__(self, group: groups.Group):
        self.group = group
        self.cue = None

    def next(self, cue: groups.Cue):
        "Call this whenever the media changes"

        if self.cue:
            oldSoundOut = self.cue.sound_output
        else:
            oldSoundOut = None
        if not oldSoundOut:
            oldSoundOut = self.group.sound_output

        self.cue = cue

        fade_len = max(
            0,
            self.group.cue.sound_fade_out
            or self.group.crossfade
            or self.group.evalExprFloat(cue.fade_in),
        )

        if not cue.sound == "__keep__":
            # Don't stop audio of we're about to crossfade to the next track
            if not (self.group.crossfade and cue.sound):
                if (
                    self.group.cue.sound_fade_out
                    or self.group.cue.media_wind_down
                ):
                    fadeSound(
                        None,
                        length=self.group.cue.sound_fade_out,
                        handle=str(self.group.id),
                        winddown=self.group.evalExprFloat(
                            self.group.cue.media_wind_down or 0
                        ),
                    )
                else:
                    if not fade_len:
                        stop_sound(str(self.group.id))

            # There is no next sound so crossfade to silence
            elif self.group.crossfade and (not cue.sound):
                if (
                    self.group.cue.sound_fade_out
                    or self.group.cue.media_wind_down
                ):
                    fadeSound(
                        None,
                        length=self.group.cue.sound_fade_out,
                        handle=str(self.group.id),
                        winddown=self.group.evalExprFloat(
                            self.group.cue.media_wind_down or 0
                        ),
                    )
                else:
                    stop_sound(str(self.group.id))

            self.group.media_link.allowed_remote_media_url = None

            out: str | None = cue.sound_output

            if not out:
                out = self.group.sound_output
            if not out:
                out = None

            if oldSoundOut == "groupwebplayer" and not out == "groupwebplayer":
                self.group.media_link_socket.send(["volume", self.group.alpha])
                self.group.media_link_socket.send(
                    [
                        "mediaURL",
                        None,
                        self.group.entered_cue,
                        max(0, cue.fade_in or self.group.crossfade),
                    ]
                )

            if cue.sound and self.group.active:
                sound = cue.sound
                try:
                    self.group.cueVolume = min(
                        5,
                        max(
                            0,
                            self.group.evalExprFloat(cue.sound_volume or 1),
                        ),
                    )
                except Exception:
                    self.group.event(
                        "script.error",
                        self.group.name
                        + " in cueVolume eval:\n"
                        + traceback.format_exc(),
                    )
                    self.group.cueVolume = 1
                try:
                    sound = self.group.resolve_media(sound, cue)
                except Exception:
                    print(traceback.format_exc())

                if os.path.isfile(sound):
                    if not out == "groupwebplayer":
                        # Always fade in if the face in time set.
                        # Also fade in for crossfade,
                        # but in that case we only do it if there is something to fade in from.

                        spd = self.group.script_context.preprocessArgument(
                            cue.media_speed
                        )
                        spd = spd or 1
                        spd = float(spd)

                        if not (
                            (
                                (
                                    (self.group.crossfade > 0)
                                    and not (cue.sound_fade_in < 0)
                                )
                                and sound_player.is_playing(str(self.group.id))
                            )
                            or (cue.fade_in > 0)
                            or (cue.sound_fade_in > 0)
                            or cue.media_wind_up
                            or self.group.cue.media_wind_down
                        ):
                            play_sound(
                                sound,
                                handle=str(self.group.id),
                                volume=self.group.alpha * self.group.cueVolume,
                                output=out,
                                loop=cue.sound_loops,
                                start=self.group.evalExprFloat(
                                    cue.sound_start_position or 0
                                ),
                                speed=spd,
                            )
                        else:
                            fade = (
                                cue.fade_in
                                or cue.sound_fade_in
                                or self.group.crossfade
                            )
                            # Odd cases where there's a wind up but specifically disabled fade
                            if cue.sound_fade_in < 0:
                                fade = 0.1

                            fadeSound(
                                sound,
                                length=max(fade, 0.1),
                                handle=str(self.group.id),
                                volume=self.group.alpha * self.group.cueVolume,
                                output=out,
                                loop=cue.sound_loops,
                                start=self.group.evalExprFloat(
                                    cue.sound_start_position or 0
                                ),
                                windup=self.group.evalExprFloat(
                                    cue.media_wind_up or 0
                                ),
                                winddown=self.group.evalExprFloat(
                                    self.group.cue.media_wind_down or 0
                                ),
                                speed=spd,
                            )

                    else:
                        self.group.media_link.allowed_remote_media_url = sound
                        self.group.media_link_socket.send(
                            ["volume", self.group.alpha]
                        )
                        self.group.media_link_socket.send(
                            [
                                "mediaURL",
                                sound,
                                self.group.entered_cue,
                                max(0, cue.fade_in or self.group.crossfade),
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
                            self.group.event(
                                "error",
                                "Reading metadata for: "
                                + sound
                                + traceback.format_exc(),
                            )
                        album_art = None
                        currentAudioMetadata = {
                            "title": "",
                            "artist": "",
                            "album": "",
                            "year": "",
                        }

                    self.group.cueInfoTag.value = {
                        "audio.meta": currentAudioMetadata
                    }

                    if album_art and len(album_art) < 3 * 10**6:
                        self.group.albumArtTag.value = (
                            "data:image/jpeg;base64,"
                            + base64.b64encode(album_art).decode()
                        )
                    else:
                        self.group.albumArtTag.value = ""

                else:
                    self.group.event("error", "File does not exist: " + sound)
            else:
                if oldSoundOut == "groupwebplayer" or out == "groupwebplayer":
                    self.group.media_link.allowed_remote_media_url = None
                    self.group.media_link_socket.send(
                        [
                            "mediaURL",
                            None,
                            self.group.entered_cue,
                            max(0, cue.fade_in or self.group.crossfade),
                        ]
                    )

    def stop(self):
        stop_sound(str(self.group.id))
