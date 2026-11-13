from __future__ import annotations

import importlib as _importlib
import os as _os
import socket as _socket
import threading as _threading
import weakref as _weakref
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

# Maps a subdomain (like "myapp") to the ASGI application that should
# handle all requests arriving on that subdomain.  Weak values so that
# an application is automatically unmounted when nothing references it.
_subdomain_apps: _weakref.WeakValueDictionary[str, Any] = (
    _weakref.WeakValueDictionary()
)

# Maps a path prefix (like "/apps/myapp") to the ASGI application that
# should handle every request under it.  Unlike _asgi_apps, which is read
# once when the server starts, this registry can be changed at any time,
# so resources can mount and unmount applications as they load.  Guarded
# by _path_apps_lock because resources load on their own threads while the
# server serves requests on the event loop thread.
_path_apps: _weakref.WeakValueDictionary[str, Any] = (
    _weakref.WeakValueDictionary()
)
_path_apps_lock = _threading.Lock()

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
    prefix = prefix.removesuffix(".*")
    _asgi_apps.append((prefix, app, permission))


def add_wsgi_app(prefix: str, app, permission="system_admin"):
    "Mount a WSGI application to handle all URLs matching the prefix"
    prefix = prefix.removesuffix(".*")
    _wsgi_apps.append((prefix, app, permission))


def add_subdomain_app(subdomain: str, app: Any) -> None:
    """Mount an ASGI application to handle all requests arriving on the
    given subdomain (for example "myapp" handles "myapp.example.com").
    The subdomain must be a single DNS label with no dots.
    """
    if not subdomain or "." in subdomain:
        raise ValueError(
            f"Subdomain must be a single DNS label, got {subdomain!r}"
        )
    if subdomain in _subdomain_apps:
        raise ValueError(f"Subdomain {subdomain!r} is already in use")
    _subdomain_apps[subdomain] = app


def remove_subdomain_app(subdomain: str, app: Any) -> None:
    """Unmount an ASGI application previously added with
    add_subdomain_app.  Does nothing if the subdomain is not currently
    mapped to the given app.
    """
    if _subdomain_apps.get(subdomain) is app:
        del _subdomain_apps[subdomain]


def add_path_app(prefix: str, app: Any) -> None:
    """Mount a dynamic ASGI application to handle every request whose
    path is exactly ``prefix`` or starts with ``prefix`` followed by a
    slash (for example ``"/apps/myapp"``).  The longest matching prefix
    wins, so more specific mounts take precedence.

    Unlike :func:`add_asgi_app`, which is only consulted once when the
    server starts, this can be called at any time.  The mount is released
    either with :func:`remove_path_app` or automatically when nothing
    references ``app`` any more.
    """
    if not prefix.startswith("/"):
        raise ValueError(f"Path prefix must start with '/', got {prefix!r}")
    prefix = prefix.rstrip("/")
    if not prefix:
        raise ValueError("Path prefix must not be empty")
    with _path_apps_lock:
        if prefix in _path_apps:
            raise ValueError(f"Path prefix {prefix!r} is already in use")
        _path_apps[prefix] = app


def remove_path_app(prefix: str, app: Any) -> None:
    """Unmount an application previously added with add_path_app.

    Does nothing if the prefix is not currently mapped to the given app.
    """
    prefix = prefix.rstrip("/")
    with _path_apps_lock:
        if _path_apps.get(prefix) is app:
            del _path_apps[prefix]


def lookup_path_app(path: str) -> Any | None:
    """Return the application mounted for ``path``, or None.

    Chooses the longest registered prefix that matches; a prefix matches
    when the path equals it or continues past it with a ``/`` boundary, so
    a mount at ``/apps/app`` never captures ``/apps/app2``.
    """
    with _path_apps_lock:
        prefixes = list(_path_apps.keys())
        best = None
        for prefix in prefixes:
            if path == prefix or path.startswith(prefix + "/"):
                if best is None or len(prefix) > len(best):
                    best = prefix
        if best is None:
            return None
        return _path_apps.get(best)


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


def has_permission(permission: str, asgi=None, user: str | None = None) -> bool:
    """Return True if the user accessing the current web request
    has the permssion specified.

    If not running in a Quart context, you must use the asgi parameter
    and specify a scope, or specify a user directly.
    """
    if user:
        return _pages.canUserDoThis(permission, user)
    return _pages.canUserDoThis(permission, asgi=asgi)


def require(permission: str):
    """Raise an exception if the user accessing the current web request in a Quart context
    does not have the permssion specified"""
    return _pages.require(permission)
