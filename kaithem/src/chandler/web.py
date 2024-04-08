import cherrypy
from .. import pages
import os
from mako.lookup import TemplateLookup

from ..kaithemobj import kaithem
from . import core
from . import blendmodes
from . import scenes


from .. import directories

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
            m = rtmidi.MidiIn(rtmidi.API_UNIX_JACK)
        except Exception:
            m = rtmidi.MidiIn(rtmidi.API_UNIX_JACK)

        x = [(m.get_port_name(i)) for i in range(m.get_port_count())]
        m.close_port()
        return x
    except Exception:
        core.logger.exception("Error in MIDI system")
        return []


from kaithem.src import tagpoints


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
        if x.subtype == "event":
            if len(v) > 250:
                break
            v.append(i)
    return v


from .. import directories


class Web:
    def header(self, l, v):
        return get_template("dlmaker.html").render(__datalists__=l, __jsvars__=v)

    def scriptheader(self, v):
        return get_template("global_vars_maker.js").render(__jsvars__=v)

    @cherrypy.expose
    def editor(self):
        """Index page for web interface"""
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        pages.require("system_admin")
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
            lists=self.header(datalists, {}),
            boardname="default",
            core=core,
            blendmodes=blendmodes,
        )

    @cherrypy.expose
    def config(self):
        """Config page for web interface"""
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
        pages.require("system_admin")
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
            lists=self.header(datalists, {}),
            boardname="default",
            core=core,
            blendmodes=blendmodes,
        )

    @cherrypy.expose
    def dyn_js(self, file):
        if file == "boardapi.js":
            pages.require("view_admin_info")

            vars = {
                "KaithemSoundCards": [i for i in kaithem.sound.outputs()],
                "availableTags": limitedTagsListing(),
            }

            return get_template("boardapi.js").render(
                vars=self.scriptheader(vars),
            )

    @cherrypy.expose
    def default(self, path, **kwargs):
        if path in ("webmediadisplay", "WebMediaServer"):
            pass
        else:
            pages.require("chandler_operator")
        if "." not in path:
            path = path + ".html"
        try:
            r = get_template(path).render(
                module=core,
                kaithem=kaithem,
                kwargs=kwargs,
                scenes=scenes,
                request=cherrypy.request,
            )
            if isinstance(r, str):
                r = r.encode()
            return r
        except pages.ServeFileInsteadOfRenderingPageException as e:
            if not isinstance(e.f_filepath, (str, os.PathLike)):
                # bytesio not a real path....
                return e.f_filepath
            # cherrypy.response.headers['Content-Type'] = e.f_MIME
            # cherrypy.response.headers['Content-Disposition'] = 'attachment ; filename = "' + e.f_name + '"'
            return cherrypy.lib.static.serve_file(
                e.f_filepath, content_type=e.f_MIME, name=e.f_name
            )

    # @cherrypy.expose
    # def butterchurn(self, file):
    #     if '..' in file or '/' in file or '\\' in file:
    #         return "confuse a hacker script"
    #     try:
    #         return get_template("butterchurnserver.html").render(file=file, kaithem=kaithem, request= cherrypy.request)
    #     except pages.ServeFileInsteadOfRenderingPageException as e:
    #         #cherrypy.response.headers['Content-Type'] = e.f_MIME
    #         #cherrypy.response.headers['Content-Disposition'] = 'attachment ; filename = "' + e.f_name + '"'
    #         return cherrypy.lib.static.serve_file(e.f_filepath, e.f_MIME, e.f_name)

    @cherrypy.expose
    def static(self, file):
        if ".." in file or "/" in file or "\\" in file:
            return "confuse a hacker script"
        with open(os.path.join(os.path.dirname(__file__), "html", file)) as f:
            return f.read()
