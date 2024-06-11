import importlib as _importlib
import os as _os

import jinja2 as _jinja2

from kaithem.src import directories as _directories
from kaithem.src import pages as _pages
from kaithem.src import theming

theming = theming


nav_bar_plugins = _pages.nav_bar_plugins

_asgi_apps = []
_wsgi_apps = []


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


_env = _jinja2.Environment(loader=_jl, autoescape=False, bytecode_cache=MyCache())


def render_jinja_template(template_filename: str, **kw):
    """Given the filename of a template, render it in a context where it has
    access to certain Kaithm standard templates

    Example template that uses the standard kaithem template everything else does.

    {% extends "pagetemplate.j2.html" %}

    {% block title %}Title Here{% endblock %}

    {% block body %}
    <main>
        Content here
    </main>
    {% endblock %}
    """
    return _jl.load(_env, template_filename, _env.globals).render(imp0rt=_importlib.import_module, **kw)


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
