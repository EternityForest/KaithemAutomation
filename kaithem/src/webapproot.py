import cherrypy
import mako

import os
import traceback
import time
import mimetypes

from . import (
    pages,
    directories,
    settings,
    notifications,
    auth,
    config,
    tagpoints,
    modules,
    alerts,
    logviewer,
    weblogin,
    ManageUsers,
    modules_interface,
    usrpages,
    widgets,
    messagelogging,
    btadmin,
    devices,
)


from .chandler import web as cweb

from cherrypy.lib.static import serve_file
from cherrypy import _cperror


class Errors:
    @cherrypy.expose
    def permissionerror(
        self,
    ):
        cherrypy.response.status = 403
        return pages.get_template("errors/permissionerror.html").render()

    @cherrypy.expose
    def alreadyexists(
        self,
    ):
        cherrypy.response.status = 400
        return pages.get_template("errors/alreadyexists.html").render()

    @cherrypy.expose
    def gosecure(
        self,
    ):
        cherrypy.response.status = 426
        return pages.get_template("errors/gosecure.html").render()

    @cherrypy.expose
    def loginerror(
        self,
    ):
        cherrypy.response.status = 400
        return pages.get_template("errors/loginerror.html").render()

    @cherrypy.expose
    def nofoldermoveerror(
        self,
    ):
        cherrypy.response.status = 400
        return pages.get_template("errors/nofoldermove.html").render()

    @cherrypy.expose
    def wrongmethod(
        self,
    ):
        cherrypy.response.status = 405
        return pages.get_template("errors/wrongmethod.html").render()

    @cherrypy.expose
    def error(
        self,
    ):
        cherrypy.response.status = 500
        return pages.get_template("errors/error.html").render(info="An Error Occurred")


class Utils:
    @cherrypy.expose
    def video_signage(self, *a, **k):
        return pages.get_template("utils/video_signage.html").render(
            vid=k["src"], mute=int(k.get("mute", 1))
        )


def cpexception():
    cherrypy.response.status = 500
    try:
        cherrypy.response.body = bytes(
            pages.get_template("errors/cperror.html").render(
                e=_cperror.format_exc(),
                mk=mako.exceptions.html_error_template().render().decode(),
            ),
            "utf8",
        )
    except Exception:
        cherrypy.response.body = bytes(
            pages.get_template("errors/cperror.html").render(
                e=_cperror.format_exc(), mk=""
            ),
            "utf8",
        )


# This class represents the "/" root of the web app
class webapproot:
    login = weblogin.LoginScreen()
    auth = ManageUsers.ManageAuthorization()
    modules = modules_interface.WebInterface()
    settings = settings.Settings()
    settings.bt = btadmin.WebUI()
    errors = Errors()
    utils = Utils()
    pages = usrpages.KaithemPage()
    logs = messagelogging.WebInterface()
    notifications = notifications.WI()
    widgets = widgets.WebInterface()
    syslog = logviewer.WebInterface()
    devices = devices.WebDevices()
    chandler = cweb.Web()

    # This lets users mount stuff at arbitrary points, so long
    # As it doesn't conflict with anything.

    # foo.bar.com/foo maps to foo,bar,/,foo
    # bar.com/foo is just foo

    def _cp_dispatch(self, vpath):
        sdpath = pages.getSubdomain()

        vpath2 = vpath[:]

        # For binding the root of subdomains

        while vpath2:
            # Check for any subdomain specific handling.
            if tuple(sdpath + ["/"] + vpath2) in pages.nativeHandlers:
                # found match, remove N elements from the beginning of the path,
                # where n is the length of the "mountpoint", becsause the mountpoint
                # already consumed those.

                # Don't do it for the fake one we add just to make this loop work though
                for i in vpath2:
                    vpath.pop(0)

                x = pages.nativeHandlers[tuple(sdpath + ["/"] + vpath2)]

                # Traverse to the actual function, if there is a match, else return the index.

                if vpath and hasattr(x, vpath[0]):
                    x2 = getattr(x, vpath[0])
                    if hasattr(x2, "exposed") and x2.exposed:
                        vpath.pop(0)
                        x = x2
                if not isinstance(x, Exception):
                    return x
                else:
                    raise x

            if tuple(vpath2) in pages.nativeHandlers:
                # found match, remove N elements from the beginning of the path,
                # where n is the length of the "mountpoint", because the mountpoint
                # already consumed those
                for i in range(len(vpath2)):
                    vpath.pop(0)

                x = pages.nativeHandlers[tuple(vpath2)]
                if vpath and hasattr(x, vpath[0]):
                    x2 = getattr(x, vpath[0])
                    if vpath and hasattr(x2, "exposed") and x2.exposed:
                        vpath.pop(0)
                        x = x2
                if not isinstance(x, Exception):
                    return x
                else:
                    raise x

            if None in pages.nativeHandlers:
                return pages.nativeHandlers[None]

            # Successively remove things from the end till we get a
            # prefix match
            vpath2.pop(-1)

        return None

    @cherrypy.expose
    def default(self, *path, **data):
        return self._cp_dispatch(list(path))(*path, **data)

    @cherrypy.expose
    @cherrypy.config(**{"response.timeout": 7200})
    def user_static(self, *args, **kwargs):
        "Very simple file server feature!"

        if not args:
            if os.path.exists(os.path.join(directories.vardir, "static", "index.html")):
                return serve_file(
                    os.path.join(directories.vardir, "static", "index.html")
                )

        try:
            dir = "/".join(args)
            for i in dir:
                if "/" in i:
                    raise RuntimeError("Security violation")

            for i in dir:
                if ".." in i:
                    raise RuntimeError("Security violation")

            dir = os.path.join(directories.vardir, "static", dir)

            if not os.path.normpath(dir).startswith(
                os.path.join(directories.vardir, "static")
            ):
                raise RuntimeError("Security violation")

            if os.path.isfile(dir):
                return serve_file(dir)
            else:
                x = [
                    (i + "/" if os.path.isdir(os.path.join(dir, i)) else i)
                    for i in os.listdir(dir)
                ]
                x = "\r\n".join(['<a href="' + i + '">' + i + "</a><br>" for i in x])
                return x
        except Exception:
            return traceback.format_exc()

    # Keep the dispatcher from freaking out. The actual handling
    # Is done by a cherrypy tool. These just keeo cp_dispatch from being called
    # I have NO clue why the favicon doesn't have this issue.
    @cherrypy.expose
    def static(self, *path, **data):
        pass

    @cherrypy.expose
    def usr(self, *path, **data):
        pass

    @cherrypy.expose
    def index(self, *path, **data):
        r = settings.redirects.get("/", {}).get("url", "")
        if (
            r
            and not path
            and not cherrypy.url().endswith("/index")
            or cherrypy.url().endswith("/index/")
        ):
            raise cherrypy.HTTPRedirect(r)

        pages.require("/admin/mainpage.view")
        cherrypy.response.cookie["LastSawMainPage"] = time.time()
        return pages.get_template("index.html").render(
            api=notifications.api, alertsapi=alerts.api
        )

    @cherrypy.expose
    def dropdownpanel(self, *path, **data):
        pages.require("/admin/mainpage.view")
        return pages.get_template("dropdownpanel.html").render(
            api=notifications.api, alertsapi=alerts.api
        )

    # @cherrypy.expose
    # def alerts(self, *path, **data):
    #     pages.require("/admin/mainpage.view")
    #     return pages.get_template('alerts.html').render(api=notifications.api, alertsapi=alerts.api)

    @cherrypy.expose
    def tagpoints(self, *path, show_advanced="", **data):
        # This page could be slow because of the db stuff, so we restrict it more
        pages.require("/admin/settings.edit")
        if "new_numtag" in data:
            pages.postOnly()
            return pages.get_template("settings/tagpoint.html").render(
                new_numtag=data["new_numtag"],
                tagname=data["new_numtag"],
                show_advanced=True,
            )
        if "new_strtag" in data:
            pages.postOnly()
            return pages.get_template("settings/tagpoint.html").render(
                new_strtag=data["new_strtag"],
                tagname=data["new_strtag"],
                show_advanced=True,
            )

        if data:
            pages.postOnly()

        if path:
            tn = '/'.join(path)
            if not tn.startswith('='):
                tn = '/'+tn
            if not tn in tagpoints.allTags:
                raise ValueError("This tag does not exist")
            return pages.get_template("settings/tagpoint.html").render(
                tagName=tn, data=data, show_advanced=show_advanced
            )
        else:
            return pages.get_template("settings/tagpoints.html").render(data=data)

    @cherrypy.expose
    def tagpointlog(self, *path, **data):
        # This page could be slow because of the db stuff, so we restrict it more
        pages.require("/admin/settings.edit")
        pages.postOnly()
        if "exportRows" not in data:
            return pages.get_template("settings/tagpointlog.html").render(
                tagName=path[0], data=data
            )
        else:
            import pytz
            import datetime
            import dateutil.parser

            for i in tagpoints.allTags[path[0]]().configLoggers:
                if i.accumType == data["exportType"]:
                    tz = pytz.timezone(
                        auth.getUserSetting(pages.getAcessingUser(), "timezone")
                    )
                    logtime = tz.localize(
                        dateutil.parser.parse(data["logtime"])
                    ).timestamp()
                    raw = i.getDataRange(
                        logtime, time.time() + 10000000, int(data["exportRows"])
                    )

                    if data["exportFormat"] == "csv.iso":
                        cherrypy.response.headers["Content-Disposition"] = (
                            'attachment; filename="%s"'
                            % path[0]
                            .replace("/", "_")
                            .replace(".", "_")
                            .replace(":", "_")[1:]
                            + "_"
                            + data["exportType"]
                            + tz.localize(
                                dateutil.parser.parse(data["logtime"])
                            ).isoformat()
                            + ".csv"
                        )
                        cherrypy.response.headers["Content-Type"] = "text/csv"
                        d = [
                            "Time(ISO), "
                            + path[0].replace(",", "")
                            + " <accum "
                            + data["exportType"]
                            + ">"
                        ]
                        for i in raw:
                            dt = datetime.datetime.fromtimestamp(i[0])
                            d.append(dt.isoformat() + "," + str(i[1])[:128])
                        return "\r\n".join(d) + "\r\n"

    @cherrypy.expose
    def pagelisting(self, *path, **data):
        # Pagelisting knows to only show pages if you have permissions
        return pages.get_template("pagelisting.html").render_unicode(
            modules=modules.ActiveModules
        )

    # docs, helpmenu, and license are just static pages.
    @cherrypy.expose
    def docs(self, *path, **data):
        if path:
            if path[0] == "thirdparty":
                p = os.path.normpath(
                    os.path.join(directories.srcdir, "docs", "/".join(path))
                )
                if not p.startswith(os.path.join(directories.srcdir, "docs")):
                    raise RuntimeError("Invalid URL")
                cherrypy.response.headers["Content-Type"] = mimetypes.guess_type(p)[0]

                with open(p, "rb") as f:
                    return f.read()
            return pages.get_template("help/" + path[0] + ".html").render(
                path=path, data=data
            )
        return pages.get_template("help/help.html").render()

    @cherrypy.expose
    def makohelp(self, *path, **data):
        return pages.get_template("help/makoreference.html").render()

    @cherrypy.expose
    def about(self, *path, **data):
        return pages.get_template("help/about.html").render()

    @cherrypy.expose
    def changelog(self, *path, **data):
        return pages.get_template("help/changes.html").render()

    @cherrypy.expose
    def helpmenu(self, *path, **data):
        return pages.get_template("help/index.html").render()

    @cherrypy.expose
    def license(self, *path, **data):
        return pages.get_template("help/license.html").render()

    @cherrypy.expose
    def aerolabs_blockrain(self, *path, **data):
        # There is no reason to be particularly concerned here, I have no reason not to trust
        # Aerolabs, this is just for the people that hate hidden games and such.
        cherrypy.response.headers["Content-Security-Policy"] = "connect-src none"
        return pages.get_template("blockrain.html").render()


root = webapproot()

if not os.path.abspath(__file__).startswith("/usr/bin"):
    sdn = os.path.join(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src"
    )
    ddn = os.path.join(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "data"
    )
else:
    sdn = "/usr/lib/kaithem/src"
    ddn = "/usr/share/kaithem"

conf = {
        "/static": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": os.path.join(ddn, "static"),
            "tools.sessions.on": False,
            "tools.addheader.on": True,
            "tools.expires.on": True,
            "tools.expires.secs": 3600 + 48,  # expire in 48 hours
        },
        "/static/js": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": os.path.join(sdn, "js"),
            "tools.sessions.on": False,
            "tools.addheader.on": True,
        },
        "/static/vue": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": os.path.join(sdn, "vue"),
            "tools.sessions.on": False,
            "tools.addheader.on": True,
        },
        "/static/css": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": os.path.join(sdn, "css"),
            "tools.sessions.on": False,
            "tools.addheader.on": True,
        },
        "/static/docs": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": os.path.join(sdn, "docs"),
            "tools.sessions.on": False,
            "tools.addheader.on": True,
        },
        "/static/zip": {
            "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
            "tools.addheader.on": True,
        },
        "/pages": {
            "tools.allow_upload.on": True,
            "tools.allow_upload.f": lambda: auth.getUserLimit(
                pages.getAcessingUser(), "web.maxbytes"
            )
            or 64 * 1024,
            "request.dispatch": cherrypy.dispatch.MethodDispatcher(),
        },
    }

    if not config["favicon-png"] == "default":
        cnf["/favicon.png"] = {
            "tools.staticfile.on": True,
            "tools.staticfile.filename": os.path.join(
                directories.datadir, "static", config["favicon-png"]
            ),
            "tools.expires.on": True,
            "tools.expires.secs": 3600,  # expire in an hour
        }

    if not config["favicon-ico"] == "default":
        cnf["/favicon.ico"] = {
            "tools.staticfile.on": True,
            "tools.staticfile.filename": os.path.join(
                directories.datadir, "static", config["favicon-ico"]
            ),
            "tools.expires.on": True,
            "tools.expires.secs": 3600,  # expire in an hour
        }
}