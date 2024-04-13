import html
import json
import re

import cherrypy
import yaml

from .. import pages as _pages
from .. import theming

theming = theming

controllers = _pages.nativeHandlers

nav_bar_plugins = _pages.nav_bar_plugins


wsgi_apps = []
tornado_apps = []


def add_wsgi_app(pattern: str, app, permission="system_admin"):
    "Mount a WSGI application to handle all URLs matching the pattern regex"
    wsgi_apps.append((pattern, app, permission))


def add_tornado_app(pattern: str, app, args, permission="system_admin"):
    "Mount a Tornado application to handle all URLs matching the pattern regex"
    tornado_apps.append((pattern, app, args, permission))


def go_back():
    raise cherrypy.HTTPRedirect(cherrypy.request.headers["Referer"])


def goto(url):
    raise cherrypy.HTTPRedirect(url)


def serve_file(*a, **k):
    _pages.serveFile(*a, **k)


def user():
    """

    Returns:
        _type_: Username of this active web request, or empty string if unknown
    """
    x = _pages.getAcessingUser()
    if x:
        return x
    else:
        return ""


def has_permission(permission: str):
    """Return True if the user accessing the current web request
    has the permssion specified"""
    return _pages.canUserDoThis(permission)


# Used for freeboard self modifying pages, should not
def freeboard(page, kwargs, plugins=[]):
    """Returns the ready-to-embed code for freeboard.
    Used to unclutter user created pages that use it.
    Should not be messed with manually most likely
    """
    if cherrypy.request.method == "POST":
        _pages.require("system_admin")
        c = re.sub(
            r"<\s*freeboard-data\s*>[\s\S]*<\s*\/freeboard-data\s*>",
            "<freeboard-data>\n" + html.escape(yaml.dump(json.loads(kwargs["bd"]))) + "\n</freeboard-data>",
            page.getContent(),
        )
        page.setContent(c)
    else:
        return _pages.get_template("freeboard/app.html").render(plugins=plugins)
