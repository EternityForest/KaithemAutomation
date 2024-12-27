from __future__ import annotations

import importlib as _importlib
import os as _os
import socket as _socket
from collections.abc import Callable
from typing import Any

import jinja2 as _jinja2

from kaithem.src import directories as _directories
from kaithem.src import pages as _pages
from kaithem.src import theming
from kaithem.src.quart_app import app as quart_app  # noqa: F401

theming = theming


nav_bar_plugins = _pages.nav_bar_plugins

_asgi_apps = []
_wsgi_apps = []

_module_plugin_links = []
_file_resource_links = []
_file_preview_plugins = []

# This is for plugins to use and extend pageheader.
_jl = _jinja2.FileSystemLoader(
    [_os.path.join(_directories.htmldir, "jinjatemplates"), "/"],
    encoding="utf-8",
    followlinks=False,
)


class MyCache(_jinja2.BytecodeCache):
    def __init__(self):
        self.cache = {}

    def load_bytecode(self, bucket):
        k = bucket.key
        if k in self.cache:
            bucket.bytecode_from_string(self.cache[k])

    def dump_bytecode(self, bucket):
        k = bucket.key
        self.cache[k] = bucket.bytecode_to_string()


_env = _jinja2.Environment(
    loader=_jl, autoescape=False, bytecode_cache=MyCache()
)


def render_jinja_template(template_filename: str, **kw):
    """Given the filename of a template, render it in a context where it has
    access to certain Kaithem standard templates

    Example template that uses the standard kaithem template everything else does.

    {% extends "pagetemplate.j2.html" %}

    {% block title %}Title Here{% endblock %}

    {% block body %}
    <main>
        Content here
    </main>
    {% endblock %}
    """
    return _jl.load(_env, template_filename, _env.globals).render(
        imp0rt=_importlib.import_module, **kw
    )


def render_html_file(body_fn: str, title: str = "Kaithem"):
    """Given a file raw html, render it in completed page, with header and footer"""
    with open(body_fn) as f:
        body = f.read()

    title = title or _socket.gethostname()
    return render_jinja_template("generic_page.j2.html", body=body, title=title)


def render_html_string(body: str, title: str = "Kaithem"):
    """Given a string raw html, render it in completed page, with header and footer"""
    return render_jinja_template("generic_page.j2.html", body=body, title=title)


def add_asgi_app(prefix: str, app, permission="system_admin"):
    "Mount an ASGI application to handle all URLs matching the prefix"
    if prefix.endswith(".*"):
        prefix = prefix[:-2]
    _asgi_apps.append((prefix, app, permission))


def add_wsgi_app(prefix: str, app, permission="system_admin"):
    "Mount a WSGI application to handle all URLs matching the prefix"
    if prefix.endswith(".*"):
        prefix = prefix[:-2]
    _wsgi_apps.append((prefix, app, permission))


def add_module_plugin_link(link: str, destination: str):
    """Add a link to module pages. Destination must be an absolute URL with no params
    It will get the module and dir params added to it.

    Link must be HTML content of the link.
    """
    _module_plugin_links.append((link, destination))


def add_file_resource_link(
    filter: None | Callable[[str, str], tuple[str, str] | None] = None,
):
    """Add a link to every file resource if filter matches
    Return value is link html, destination tuple or None.

    Input is module, resource
    """
    _file_resource_links.append(filter)


def add_file_resource_preview_plugin(
    filter: None | Callable[[dict[str, Any]], str | None] = None,
):
    """Add a preview box to every file resource if filter matches
    Return value is embedded html or None.

    Input is a dict that may have none to any of the following keys:
        module, resource, size, timestamp, path
        access_url, thumbnail_url

    You should use the access_url rather than getting it yourself,
    if it exists, because it may give you a url with specific permissions
    """
    _file_preview_plugins.append(filter)


def serve_file(path, contenttype="", name=None):
    "Call from within a Quart handler to server a file."
    _pages.serveFile(path=path, contenttype=contenttype, name=name)


def user(asgi=None) -> str:
    """
    asgi: The ASGI scope object that is currently active, required if
          this is called from outside a Quart context.

    Returns:
        str: Username of this active web request, or empty string if unknown
    """
    x = _pages.getAcessingUser(asgi)
    if x:
        return x
    else:
        return ""


def has_permission(permission: str, asgi=None, user=None) -> bool:
    """Return True if the user accessing the current web request
    has the permssion specified.

    If not running in a Quart context, you must use the asgi parameter
    and specify a scope, or specify a user directly.
    """
    if user:
        return _pages.canUserDoThis(permission, user)
    return _pages.canUserDoThis(permission, asgi)


def require(permission: str):
    """Raise an exception if the user accessing the current web request in a Quart context
    does not have the permssion specified"""
    return _pages.require(permission)
