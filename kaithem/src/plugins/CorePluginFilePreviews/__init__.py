import mimetypes
import os
from typing import Any

import quart

from kaithem.api.web import add_file_resource_preview_plugin, quart_app
from kaithem.src.util import url


@quart_app.route("/file-preview-plugin/hls-player.html")
async def serve_hls_player():
    return await quart.send_file(
        os.path.join(os.path.dirname(__file__), "hls_player.html")
    )


thumbnailable = set(
    [
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "bmp",
        "tiff",
        "ico",
        "svg",
        "tif",
        "avif",
        "mp3",
        "opus",
        "wav",
        "m4a",
        "flac",
    ]
)

video_ext = set(
    ["mp4", "mkv", "webm", "ogg", "flv", "avi", "mov", "mpg", "mpeg"]
)

thumbnailable_mime = set()

if os.path.isdir("/usr/share/thumbnailers"):
    for i in os.listdir("/usr/share/thumbnailers"):
        if i.endswith(".thumbnailer"):
            with open(f"/usr/share/thumbnailers/{i}") as f:
                d = f.read().splitlines()
                for j in d:
                    if j.lower().startswith("mimetype="):
                        for mime in j.split("=")[1].split(";"):
                            thumbnailable_mime.add(mime)


def previewer(kw: dict[str, Any]) -> str | None:
    if "resource" not in kw:
        return None
    if "module" not in kw:
        return None
    resource = kw["resource"]
    module = kw["module"]

    mime = mimetypes.guess_type(resource)[0]
    o = '<div class="flex-col">'

    if "access_url" in kw:
        file_url = kw["access_url"]
    else:
        file_url = f"/modules/module/{ url(module) }/getfileresource/{resource}?timestamp={kw.get('timestamp', 0)}"

    if "thumbnail_url" in kw:
        thumb_url = kw["thumbnail_url"]
    else:
        thumb_url = f"/modules/module/{ url(module) }/getfileresourcethumb/{resource}?timestamp={kw.get('timestamp', 0)}"

    if resource.split(".")[-1] in thumbnailable or mime in thumbnailable_mime:
        if resource.split(".")[-1] not in video_ext:
            o += f"""<img class="max-h-6rem"
            src="{thumb_url}"
            alt="{resource}"></img>"""

    if resource.split(".")[-1] in (
        "mp3",
        "opus",
        "wav",
        "m4a",
        "flac",
        "ogg",
        "mid",
        "midi",
    ):
        o += f"""<audio controls preload="none"
        src="{file_url}">
        </audio>"""

    elif resource.split(".")[-1] in video_ext:
        o += f"""<video controls preload="none"  class="max-h-18rem"
        src="{file_url}"
        poster="{thumb_url}"
        ></video>"""

    elif resource.split(".")[-1] in ("m3u8", "m3u"):
        o += f"""<iframe
        src="/file-preview-plugin/hls-player.html?url={file_url}">
        </iframe>"""

    if o:
        return o + "</div>"
    return None


add_file_resource_preview_plugin(previewer)
