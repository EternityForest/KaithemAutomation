from __future__ import annotations

import collections
import time
from typing import TYPE_CHECKING, Any

import kaithem.api.widgets as widgets
from kaithem.src.kaithemobj import kaithem

from . import core

if TYPE_CHECKING:
    from .cue import Cue
    from .scenes import Scene


class MediaLinkManager:
    def __init__(self, sceneObj: Scene):
        # This is used for the remote media triggers feature.
        # We must explicitly give it an ID so that it stays consistent
        # between runs and we can auto-reconnect
        self.scene = sceneObj

        # The active sound file being played through the remote playback mechanism.
        # Very ugly code with this, it only deals with routing sound not slides
        self.allowed_remote_media_url: str | None = None

        class APIWidget(widgets.APIWidget):
            # Ignore badly named s param because it need to not conflic with outer self
            def on_new_subscriber(s, user, cid, **kw):  # type: ignore
                self.send_all_media_link_info()

        self.media_link_socket = APIWidget(id=sceneObj.id + "_media_link")
        self.media_link_socket.echo = False

        self.slideshow_telemetry: collections.OrderedDict[str, dict[str, Any]] = collections.OrderedDict()
        self.slideshow_telemetry_ratelimit = (time.monotonic(), 200)
        # Variables to send to the slideshow.  They are UI only and
        # we don't have any reactive features
        self.web_variables: dict[str, Any] = {}

        def handleMediaLink(u, v, id):
            if v[0] == "telemetry":
                ts, remain = self.slideshow_telemetry_ratelimit
                remain = max(0, min(200, (time.monotonic() - ts) * 3 + remain - 1))

                if remain:
                    ip = kaithem.widget.ws_connections[id].peer_address
                    n = ip + "@" + sceneObj.name

                    if v[1]["status"] == "disconnect":
                        self.slideshow_telemetry.pop(n, None)
                        for board in core.iter_boards():
                            board.linkSend(["slideshow_telemetry", n, None])
                        return

                    self.slideshow_telemetry[n] = {
                        "status": str(v[1]["status"])[:128],
                        "name": str(v[1].get("name", ""))[:128],
                        "ip": ip,
                        "id": id,
                        "ts": time.time(),
                        "battery": kaithem.widget.ws_connections[id].batteryStatus,
                        "scene": sceneObj.name,
                    }
                    self.slideshow_telemetry.move_to_end(n)

                    if len(self.slideshow_telemetry) > 256:
                        k, x = self.slideshow_telemetry.popitem(False)
                        for board in core.iter_boards():
                            board.linkSend(["slideshow_telemetry", k, None])

                    try:
                        for board in core.iter_boards():
                            board.linkSend(["slideshow_telemetry", n, self.slideshow_telemetry[n]])
                    except Exception:
                        pass

            elif v[0] == "initial":
                self.sendVisualizations()

            elif v[0] == "ask":
                self.send_all_media_link_info()

            elif v[0] == "error":
                self.scene.event(
                    "system.error",
                    "Web media playback error in remote browser: " + v[1],
                )

        self.media_link_socket.attach2(handleMediaLink)

    def set_slideshow_variable(self, k: str, v: Any):
        self.media_link_socket.send(["web_var", k, v])
        self.web_variables[k] = v

    def send_all_media_link_info(self):
        self.media_link_socket.send(["volume", self.scene.alpha])

        self.media_link_socket.send(["text", self.scene.cue.markdown])

        self.media_link_socket.send(["cue_ends", self.scene.cuelen + self.scene.entered_cue, self.scene.cuelen])

        self.media_link_socket.send(["all_variables", self.web_variables])

        self.media_link_socket.send(
            [
                "mediaURL",
                self.allowed_remote_media_url,
                self.scene.entered_cue,
                max(0, self.scene.cue.fade_in or self.scene.cue.sound_fade_in or self.scene.crossfade),
            ]
        )
        self.media_link_socket.send(
            [
                "slide",
                self.scene.cue.slide,
                self.scene.entered_cue,
                max(0, self.scene.cue.fade_in or self.scene.crossfade),
            ]
        )
        self.media_link_socket.send(["overlay", self.scene.slide_overlay_url])

    def stop(self):
        self.media_link_socket.send(["text", ""])
        self.media_link_socket.send(["mediaURL", "", 0, 0])
        self.media_link_socket.send(["slide", "", 0, 0])

    def next(self, cue: Cue):
        self.media_link_socket.send(
            [
                "slide",
                cue.slide,
                self.scene.entered_cue,
                max(0, cue.fade_in or self.scene.crossfade),
            ]
        )

        self.media_link_socket.send(
            [
                "text",
                cue.markdown,
            ]
        )

        self.media_link_socket.send(["cue_ends", self.scene.cuelen + self.scene.entered_cue, self.scene.cuelen])

    def sendVisualizations(self):
        self.media_link_socket.send(
            [
                "butterchurnfiles",
                [i.split("milkdrop:")[-1] for i in self.scene.music_visualizations.split("\n") if i],
            ]
        )
