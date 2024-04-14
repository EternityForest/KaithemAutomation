import importlib as _importlib
import os as _os
import typing as _typing

import beartype as _beartype
import cherrypy as _cherrypy
import jinja2 as _jinja2

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
    access to certain Kaithm standard templates

    Example template that uses the standard kaithem template everything else does.

    {{% extends "pagetemplate.j2.html" %}}

    {{% block title %}}Title Here{{% endblock %}}

    {{% block body %}}
    <main>
        Content here
    </main>
    {{% endblock %}}
    """
    return _jl.load(_env, template_filename, _env.globals).render(imp0rt=_importlib.import_module, **kw)


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


def goto(url):
    "Call from within a CherryPy handler to raise an exception to go to another URL"
    raise _cherrypy.HTTPRedirect(url)


def serve_file(path, contenttype="", name=None):
    "Call from within a CherryPy handler to server a file."
    _pages.serveFile(path=path, contenttype=contenttype, name=name)


def user() -> str:
    """

    Returns:
        str: Username of this active web request, or empty string if unknown
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
