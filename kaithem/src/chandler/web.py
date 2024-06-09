import os

import quart
import quart.utils
from mako.lookup import TemplateLookup

from kaithem.src import quart_app, tagpoints

from .. import directories, pages
from ..kaithemobj import kaithem
from . import blendmodes, core, scenes

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


# @quart_app.app.route("/chandler/downloadOneScene")
# def download_one_scene():
#     kwargs = quart.request.args
#     r=yaml.dump({kwargs['name']:board.scenememory[kwargs['id']].toDict()})
#     return quart.Response(r, mimetype="text/yaml", headers={"Content-Disposition": "attachment; filename="+kwargs['name']+".yaml"})


# @quart_app.app.route("/chandler/downloadm3u")
# def download_one_scene():
#     kwargs = quart.request.args
#     r=m3u_io.get_m3u(module.board.scenememory[kwargs['id']] ,kwargs['rel'])
#     return quart.Response(r, mimetype="text/yaml",  headers={"Content-Disposition": "attachment; filename="+kwargs['name']+".m3u"})


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


@quart_app.app.route("/chandler/<path:path>")
async def default(path):
    kwargs = quart.request.args
    if path in ("webmediadisplay", "WebMediaServer"):
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
                scenes=scenes,
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
