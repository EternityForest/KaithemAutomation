import os

import quart

from kaithem.api.web import quart_app

htmldir = os.path.join(os.path.dirname(__file__), "html")


@quart_app.route("/beholder-plugin/mpeg-ts-stream", methods=["GET"])
async def mpeg_ts_widget_stream():
    """This lets us stream any mpeg-ts stream to the browser"""
    return await quart.send_file(os.path.join(htmldir, "rtplayer.html"))


@quart_app.route("/beholder-plugin/mpegts.js", methods=["GET"])
async def mpegtslib():
    return await quart.send_file(os.path.join(htmldir, "mpegts.min.js"))
