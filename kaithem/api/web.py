import html as _html
import json as _json
import os as _os
import re as _re
import typing as _typing

import beartype as _beartype
import cherrypy as _cherrypy
import jinja2 as _jinja2
import yaml as _yaml

from kaithem.src import directories as _directories
from kaithem.src import pages as _pages
from kaithem.src import theming

theming = theming


nav_bar_plugins = _pages.nav_bar_plugins


_wsgi_apps = []
_tornado_apps = []

_simple_handlers = {}


# This is for plugins to use and extend pageheader.
_jl = _jinja2.FileSystemLoader(
    [_os.path.join(_directories.htmldir, "jinjatemplates"), "/"],
    encoding="utf-8",
    followlinks=False,
)

_env = _jinja2.Environment(loader=_jl, autoescape=False)


def render_jinja_template(template_filename: str, **kw):
    """Given the filename of a template, render it in a context where it has
    access to certain Kaithm standard templates.
    """
    return _jl.load(_env, template_filename, _env.globals).render(**kw)


def add_wsgi_app(pattern: str, app, permission="system_admin"):
    "Mount a WSGI application to handle all URLs matching the pattern regex"
    _wsgi_apps.append((pattern, app, permission))


def add_tornado_app(pattern: str, app, args, permission="system_admin"):
    "Mount a Tornado application to handle all URLs matching the pattern regex"
    _tornado_apps.append((pattern, app, args, permission))


@_beartype.beartype
def add_simple_cherrypy_handler(prefix: str, permissions: str, handler: _typing.Callable[[list[str], dict[str, str]], str]):
    """
    Register handler for all requests that look like /prefix.
    handler must look like:
    f(*path, **kwargs)

    It will by in a cherrypy context.

    This function is alpha.

    """

    _simple_handlers[prefix] = (permissions, handler)


def go_back():
    raise _cherrypy.HTTPRedirect(_cherrypy.request.headers["Referer"])


def goto(url):
    raise _cherrypy.HTTPRedirect(url)


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
    if _cherrypy.request.method == "POST":
        _pages.require("system_admin")
        c = _re.sub(
            r"<\s*freeboard-data\s*>[\s\S]*<\s*\/freeboard-data\s*>",
            "<freeboard-data>\n" + _html.escape(_yaml.dump(_json.loads(kwargs["bd"]))) + "\n</freeboard-data>",
            page.getContent(),
        )
        page.setContent(c)
    else:
        return _pages.get_template("freeboard/app.html").render(plugins=plugins)
