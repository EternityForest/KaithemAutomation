import hashlib
import os
import time

import quart
import quart.utils
import vignette
from mako.lookup import TemplateLookup
from tinytag import TinyTag

from kaithem.src import quart_app, tagpoints

from .. import directories, pages
from ..kaithemobj import kaithem
from . import blendmodes, core, groups, universes

_Lookup = TemplateLookup(
    directories=[
        os.path.join(os.path.dirname(__file__), "html"),
        os.path.join(directories.htmldir, "makocomponents"),
    ]
)

get_template = _Lookup.get_template

once = [0]


def listRtmidi():
    try:
        import rtmidi
    except ImportError:
        if once[0] == 0:
            kaithem.message.post(
                "/system/notifications/errors/",
                "python-rtmidi is missing. Most MIDI related features will not work.",
            )
            once[0] = 1
        return []
    try:
        try:
            m = rtmidi.MidiIn()
        except Exception:
            m = rtmidi.MidiIn()

        x = [(m.get_port_name(i)) for i in range(m.get_port_count())]
        m.close_port()
        return x
    except Exception:
        core.logger.exception("Error in MIDI system")
        return []


def limitedTagsListing():
    # Make a list of all the tags,
    # Unless there's way too many
    # Then only list some of them

    v = []
    for i in tagpoints.allTagsAtomic:
        if len(v) > 1024:
            break
        v.append(i)
    return v


def command_tagsListing():
    # Make a list of all the tags,
    # Unless there's way too many
    # Then only list some of them

    v = []
    t = tagpoints.allTagsAtomic
    for i in t:
        x = t[i]()
        if x:
            if x.subtype == "event":
                if len(v) > 250:
                    break
                v.append(i)
    return v


def header(datalists, v):
    return get_template("dlmaker.html").render(__datalists__=datalists, __jsvars__=v)


def scriptheader(v):
    return get_template("global_vars_maker.js").render(__jsvars__=v)


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


@quart_app.app.route("/chandler/label_image_update_callback/<path:path>", methods=["POST"])
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


@quart_app.app.route("/chandler/editor/<board>")
def editor(board: str):
    """Index page for web interface"""
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    v = limitedTagsListing()
    c = command_tagsListing()

    datalists = {"midiinputs": [], "tagslisting": [], "commandtagslisting": []}

    for i in listRtmidi():
        datalists["midiinputs"].append({"value": str(i)})

    for i in v:
        datalists["tagslisting"].append({"value": str(i)})

    for i in c:
        datalists["commandtagslisting"].append({"value": str(i)})

    return get_template("console.html").render(
        lists=header(datalists, {}),
        boardname=board,
        core=core,
        blendmodes=blendmodes,
    )


@quart_app.app.route("/chandler/commander/<board>")
def commander(board: str):
    """Index page for web interface"""
    try:
        pages.require("chandler_operator")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    return get_template("commander.html").render(boardname=board, core=core)


@quart_app.app.route("/chandler/config/<board>")
def config(board: str):
    """Config page for web interface"""
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    v = limitedTagsListing()
    c = command_tagsListing()

    datalists = {"midiinputs": [], "tagslisting": [], "commandtagslisting": []}

    for i in listRtmidi():
        datalists["midiinputs"].append({"value": str(i)})

    for i in v:
        datalists["tagslisting"].append({"value": str(i)})

    for i in c:
        datalists["commandtagslisting"].append({"value": str(i)})

    return get_template("config.html").render(
        lists=header(datalists, {}),
        boardname=board,
        core=core,
        blendmodes=blendmodes,
    )


@quart_app.app.route("/chandler/config/opz_import/<board>")
def opz_import(board: str):
    pages.require("system_admin")
    link = core.boards[board].link
    return get_template("opz_import.html").render(
        boardname=board,
        api_link=link,
    )


@quart_app.app.route("/chandler/dyn_js/<file>")
def dyn_js(file):
    if file == "boardapi.js":
        try:
            pages.require("view_admin_info")
        except PermissionError:
            return pages.loginredirect(pages.geturl())

        vars = {
            "KaithemSoundCards": [i for i in kaithem.sound.outputs()],
            "availableTags": limitedTagsListing(),
        }

        return get_template("boardapi.js").render(
            vars=scriptheader(vars),
        )
    raise RuntimeError("File not found")


@quart_app.app.route("/chandler/WebMediaServer")
async def media():
    kwargs = quart.request.args

    @quart.ctx.copy_current_request_context
    def get_file():
        if "labelImg" in kwargs:
            pages.require("enumerate_endpoints")
            pages.require("chandler_operator")

            label_image = groups.cues[kwargs["labelImg"]].label_image
            grp = groups.cues[kwargs["labelImg"]].group()

            if grp:
                return grp.resolve_media(label_image)

        if "albumArt" in kwargs:
            pages.require("enumerate_endpoints")
            pages.require("chandler_operator")

            sound = groups.cues[kwargs["albumArt"]].sound
            if not sound:
                return ""
            grp = groups.cues[kwargs["albumArt"]].group()

            if grp:
                sound = grp.resolve_media(sound)

            if vignette:
                t = vignette.try_get_thumbnail(sound)
                if t:
                    return t

            soundMeta = TinyTag.get(sound, image=True)
            t = soundMeta.get_image()
            if not t:
                return os.path.join(directories.datadir, "static", "img", "ai_default_album_art.jpg")

            return t

        else:
            # TODO: Is the timing attack resistance here enough?

            if "group" in kwargs and groups.groups[kwargs["group"]].media_link.allowed_remote_media_url == kwargs["file"]:
                return kwargs["file"]
            elif "group" in kwargs and groups.groups[kwargs["group"]].cue.slide == kwargs["file"]:
                return groups.groups[kwargs["group"]].resolve_media(kwargs["file"])
            # elif 'group' in kwargs and kwargs['file'] in groups.groups[kwargs['group']].musicVisualizations:
            #     return(kwargs['file'],name= os.path.basename(kwargs['file']))
            else:
                # Todo this should be a global api
                x = None
                for i in groups.groups:
                    x = i
                    break
                assert x
                f = groups.groups[x].resolve_media(kwargs["file"])
                if kaithem.web.has_permission("view_admin_info"):
                    for i in core.getSoundFolders(groups.groups[x].board.media_folders):
                        if not i.endswith("/"):
                            i = i + "/"
                        if os.path.normpath(f).startswith(i):
                            # If this is a cloud asset pack asset, get it.
                            # Only do this under the chandler admin permission
                            if not os.path.isfile(f):
                                pages.require("system_admin")

                            kaithem.assetpacks.ensure_file(f)
                            return f

                # Resist discovering what scenes exist
                time.sleep(hashlib.md5(kwargs["group"].encode("utf-8")).digest()[0] / 1000)
                return f

    r = await get_file()
    if isinstance(r, str):
        return await quart_app.send_file_range(r)
    elif isinstance(r, bytes):
        return r
    else:
        raise RuntimeError("???")


@quart_app.app.route("/chandler/<path:path>")
async def default(path):
    kwargs = quart.request.args
    if path in ("webmediadisplay",):
        pass
    else:
        try:
            pages.require("chandler_operator")
        except PermissionError:
            return pages.loginredirect(pages.geturl())
    if "." not in path:
        path = path + ".html"
    try:

        def f():
            r = get_template(path).render(
                module=core,
                kaithem=kaithem,
                kwargs=kwargs,
                groups=groups,
                request=quart.request,
            )
            if isinstance(r, str):
                r = r.encode()
            return r

        r = await quart.utils.run_sync(f)()
        return quart.Response(r, mimetype="text/html")
    except pages.ServeFileInsteadOfRenderingPageException as e:
        if not isinstance(e.f_filepath, (str, os.PathLike)):
            # bytesio not a real path....
            return quart.Response(e.f_filepath)
        return await quart.send_file(e.f_filepath, mimetype=e.f_MIME, as_attachment=True, attachment_filename=e.f_name)


@quart_app.app.route("/chandler/static/<path:file>")
async def static_chandler_files(file):
    if ".." in file or "/" in file or "\\" in file:
        raise RuntimeError("confuse a hacker script")
    return await quart.send_file(os.path.join(os.path.dirname(__file__), "html", file))
