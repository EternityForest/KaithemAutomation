from __future__ import annotations

import datetime
import hashlib
import os
import time
from typing import TYPE_CHECKING

import quart
import quart.utils
import vignette
from mako.lookup import TemplateLookup
from tinytag import TinyTag

if TYPE_CHECKING:
    pass

from kaithem.api.web import has_permission, render_html_file
from kaithem.src import quart_app

from .. import directories, pages, util
from . import (
    core,
    groups,
    universes,
    web_api,  # noqa: F401
)

_Lookup = TemplateLookup(
    directories=[
        os.path.join(os.path.dirname(__file__), "html"),
        os.path.join(directories.htmldir, "makocomponents"),
    ]
)

get_template = _Lookup.get_template


# @quart_app.app.route("/chandler/downloadOneGroup")
# def download_one_group():
#     kwargs = quart.request.args
#     r=yaml.dump({kwargs['name']:board.groupmemory[kwargs['id']].toDict()})
#     return quart.Response(r, mimetype="text/yaml", headers={"Content-Disposition": "attachment; filename="+kwargs['name']+".yaml"})


# @quart_app.app.route("/chandler/downloadm3u")
# def download_one_group():
#     kwargs = quart.request.args
#     r=m3u_io.get_m3u(module.board.groupmemory[kwargs['id']] ,kwargs['rel'])
#     return quart.Response(r, mimetype="text/yaml",  headers={"Content-Disposition": "attachment; filename="+kwargs['name']+".m3u"})


@quart_app.app.route("/chandler/universe_info/<universe>")
def debug_universe_values(universe):
    pages.require("chandler_operator")
    u = universes.universes[universe]
    if u:
        return get_template("universe_status.html").render(universe=u)
    return "Universe not found"


@quart_app.app.route(
    "/chandler/label_image_update_callback/<path:path>", methods=["POST"]
)
async def label_update_callback(path: str):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    kwargs = dict(await quart.request.form)
    kwargs.update(quart.request.args)

    @quart.ctx.copy_current_request_context
    def f():
        path2 = path.split("/")

        if path2[0] == "cue":
            cue = groups.cues[path2[1]]
            cue.label_image = kwargs["resource"][len("media/") :]
            gr = cue.group()
            if gr:
                gr.board.pushCueMeta(path2[1])
        elif path2[0] == "preset":
            preset = core.boards[path2[1]].fixture_presets[path2[2]]
            preset["label_image"] = kwargs["resource"][len("media/") :]
            core.boards[path2[1]].pushPreset(path2[2])
        elif path2[0] == "fixture":
            fixture = core.boards[path2[1]].fixture_assignments[path2[2]]
            fixture["label_image"] = kwargs["resource"][len("media/") :]
            core.boards[path2[1]].pushPreset(path2[2])
        return ""

    return await f()


html_dir = os.path.join(os.path.dirname(__file__), "html")

console_fn = os.path.join(html_dir, "editor.html")

schedule_fn = os.path.join(html_dir, "schedulemanager.html")


icon_types = {
    "png",
    "jpg",
    "jpeg",
    "avif",
    "webp",
    "svg",
    "gif",
    "heic",
    "heif",
    "tiff",
    "bmp",
    "ico",
}


@quart_app.app.route("/chandler/file_thumbnail")
async def get_file_thumbnail():
    fn = quart.request.args["file"]

    if fn.split(".")[-1] in icon_types:
        if os.path.isfile(fn):
            if os.path.getsize(fn) < 1024 * 32:
                return await quart.send_file(fn)

    try:
        t = vignette.get_thumbnail(fn)
    except Exception:
        t = None
    if t:
        return await quart.send_file(t)
    return await quart.send_file(
        os.path.join(directories.datadir, "static/img/1x1.png")
    )


@quart_app.app.route("/chandler/static/<fn>")
async def static_file(fn):
    if ".." in fn or "/" in fn or "\\" in fn:
        return quart.abort(404)
    return await quart.send_file(
        os.path.join(os.path.dirname(__file__), "html", fn)
    )


@quart_app.app.route("/chandler/api/eval-cue-length")
def erd():
    cuelen_str = quart.request.args["rule"]
    v = 0

    try:
        v = float(cuelen_str)
    except ValueError:
        pass

    if cuelen_str.startswith("@"):
        ref = datetime.datetime.now()
        selector = util.get_rrule_selector(cuelen_str[1:], ref)
        nextruntime = selector.after(ref, True)

        if nextruntime <= ref:
            nextruntime = selector.after(nextruntime, False)

        t2 = nextruntime.timestamp()

        nextruntime = t2

        v = nextruntime - time.time()

    v = time.time() + v
    t = datetime.datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M:%S")

    return t


@quart_app.app.route("/chandler/WebMediaServer")
async def media():
    kwargs = quart.request.args

    @quart.ctx.copy_current_request_context
    def get_file():
        if "labelImg" in kwargs:
            pages.require("enumerate_endpoints")
            pages.require("chandler_operator")
            cue = groups.cues[kwargs["labelImg"]]

            label_image = cue.label_image
            grp = cue.group()

            if grp:
                return grp.resolve_media(label_image, cue)

        if "albumArt" in kwargs:
            pages.require("enumerate_endpoints")
            pages.require("chandler_operator")
            cue = groups.cues[kwargs["albumArt"]]

            sound = cue.sound
            if not sound:
                return ""
            grp = cue.group()

            if grp:
                sound = grp.resolve_media(sound, cue)

            if vignette:
                t = vignette.try_get_thumbnail(sound)
                if t:
                    return t

            soundMeta = TinyTag.get(sound, image=True)
            t = soundMeta.images.any
            if not t:
                return os.path.join(
                    directories.datadir,
                    "static",
                    "img",
                    "ai_default_album_art.jpg",
                )

            return t

        else:
            # TODO: Is the timing attack resistance here enough?

            if kwargs.get("file") == "1x1.png":
                return os.path.join(directories.datadir, "static/img/1x1.png")

            if (
                "group" in kwargs
                and groups.groups[
                    kwargs["group"]
                ].media_link.allowed_remote_media_url
                == kwargs["file"]
            ):
                return kwargs["file"]
            elif (
                "group" in kwargs
                and groups.groups[kwargs["group"]].cue.slide == kwargs["file"]
            ):
                return groups.groups[kwargs["group"]].resolve_media(
                    kwargs["file"]
                )
            # elif 'group' in kwargs and kwargs['file'] in groups.groups[kwargs['group']].musicVisualizations:
            #     return(kwargs['file'],name= os.path.basename(kwargs['file']))
            else:
                if "board" not in kwargs:
                    if has_permission("chandler_operator"):
                        if core.resolve_sound(kwargs["file"]):
                            return core.resolve_sound(kwargs["file"])

                else:
                    board = core.boards[kwargs["board"]]

                    f = core.resolve_sound(kwargs["file"], board.media_folders)

                # Resist discovering what scenes exist
                time.sleep(
                    hashlib.md5(kwargs["group"].encode("utf-8")).digest()[0]
                    / 1000
                )
                return f

    r = await get_file()
    if isinstance(r, str):
        return await quart_app.send_file_range(r)
    elif isinstance(r, bytes):
        return r
    else:
        raise RuntimeError("???")


staticdir = os.path.join(directories.datadir, "static")


# This whole thing is more complicated than it seems like it should be,
# pretty much entirely to keep templates and static files in the same relative
# namespace
@quart_app.app.route("/chandler/<path:path>")
async def default(path: str):
    # Use the dot to distinguish templates vs static files
    if "." not in path.split("/")[-1]:
        # Todo template rendering on the server should really be
        # gone
        try:
            pages.require("chandler_operator")
        except PermissionError:
            return pages.loginredirect(pages.geturl())

        path = path.split("/")[0] + ".html"

        def f():
            if "webmedia" not in path:
                r = render_html_file(
                    os.path.join(
                        staticdir, "vite/kaithem/src/chandler/html", path
                    )
                )
            else:
                with open(
                    os.path.join(
                        staticdir, "vite/kaithem/src/chandler/html", path
                    )
                ) as f:
                    r = f.read()
            if isinstance(r, str):
                r = r.encode()
            return r

        r = await quart.utils.run_sync(f)()
        return quart.Response(r, mimetype="text/html")

    else:
        if ".." in path or "/" in path or "\\" in path:
            raise RuntimeError("confuse a hacker script")
        return await quart.send_file(
            os.path.join(os.path.dirname(__file__), "html", path)
        )


@quart_app.app.route("/chandler/static/<path:file>")
async def static_chandler_a(file):
    if ".." in file or "/" in file or "\\" in file:
        raise RuntimeError("confuse a hacker script")
    return await quart.send_file(
        os.path.join(os.path.dirname(__file__), "html", file)
    )


@quart_app.app.route("/chandler/static/<version>/<path:file>")
async def static_chandler_files_dummy_version(version, file):
    if ".." in file or "/" in file or "\\" in file:
        raise RuntimeError("confuse a hacker script")
    return await quart.send_file(
        os.path.join(os.path.dirname(__file__), "html", file)
    )
