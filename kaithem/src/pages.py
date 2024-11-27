# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import base64
import importlib
import logging
import mimetypes
import os
import time
import weakref

import jinja2
import quart
from mako.lookup import TemplateLookup
from starlette.requests import Request
from starlette.websockets import WebSocket

from . import auth, directories, settings_overrides

_Lookup = TemplateLookup(
    directories=[
        directories.htmldir,
        os.path.join(directories.htmldir, "makocomponents"),
        "/",
    ]
)
get_template = _Lookup.get_template

_varLookup = TemplateLookup(directories=[directories.vardir])


class KaithemUserPermissionError(PermissionError):
    pass


class HTTPRedirect(Exception):
    def __init__(self, url):
        Exception.__init__(self)
        self.url = url


class MyCache(jinja2.BytecodeCache):
    def __init__(self):
        self.cache = {}

    def load_bytecode(self, bucket):
        k = bucket.key
        if k in self.cache:
            bucket.bytecode_from_string(self.cache[k])

    def dump_bytecode(self, bucket):
        k = bucket.key
        self.cache[k] = bucket.bytecode_to_string()


#
_jl = jinja2.FileSystemLoader(
    [
        directories.htmldir,
        os.path.join(directories.htmldir, "jinjatemplates"),
        "/",
    ],
    encoding="utf-8",
    followlinks=False,
)


env = jinja2.Environment(loader=_jl, autoescape=False, bytecode_cache=MyCache())


env.globals["len"] = len
env.globals["str"] = str
env.globals["hasattr"] = hasattr

# These get imported by the page header template, which is also what imp0rt is for
list = list
sorted = sorted
len = len
hasattr = hasattr
str = str


def render_jinja_template(n, **kw):
    return _jl.load(env, n, env.globals).render(
        imp0rt=importlib.import_module, **kw
    )


def get_vardir_template(fn):
    return _varLookup.get_template(os.path.relpath(fn, directories.vardir))


nav_bar_plugins = weakref.WeakValueDictionary()


def get_bar_plugins():
    nbp = []
    c = settings_overrides.get_by_prefix("/core/navbar_links/")
    for i in c:
        v = c[i]
        v = v.strip()

        icon = ""
        if v.startswith("mdi-"):
            icon, v = v.split(" ", 1)
            # Remove mdi- part
            icon = icon[4:]

        try:
            nbp.append(
                (
                    i,
                    f"""<a href="{v.split(':',1)[-1].strip()}">
                        <i class="mdi mdi-{icon}"></i>{v.split(':',1)[0].strip()}</a>""",
                )
            )
        except Exception:
            pass

    for i in nav_bar_plugins:
        x = nav_bar_plugins[i]()
        if x:
            nbp.append((i, x))
    nbp = sorted(nbp)

    for i in nbp:
        yield i[1]


# There are cases where this may not exactly be perfect,
# but the point is just an extra guard against user error.
def isHTTPAllowed(ip):
    return (
        ip.startswith(
            (
                "::1",
                "127.",
                "::ffff:192.",
                "::ffff:10.",
                "192.",
                "10.",
                "fc",
                "fd",
            )
        )
        or ip == "::ffff:127.0.0.1"
    )


def getSubdomain():
    x = quart.request.base_url.split("://", 1)[-1]

    sdpath = x.split(".")

    x = []
    for i in sdpath:
        if not i:
            continue
        x.append(i)
        # Only put one part of the ip addr, host,tld need to be exactly
        # 2 entries
        if i.isnumeric() or i.startswith("localhost:") or "[" in i:
            # Pad with fake TLD for numeric ip addr
            x.append(".faketld")
            break

    # Get rid of last two parts, the host and tld
    return list(reversed(x[:-2]))


def postOnly():
    """Redirect user to main page if the request is anything but POST"""
    if not quart.request.method == "POST":
        user = getAcessingUser()
        # This is not a web request, this is the server itself
        if user == "__no_request__":
            return
        return quart.redirect("/errors/wrongmethod")


def require(permission):
    """Get the user that is making the request bound to this thread,
    and then raise an interrupt if he does not have the permission specified.

    Normally this will prompt the user to go to a login page,
    and if they log in it takes them right back where they were
    trying to go. However if the place they were going has an effect,
    you might want them to confirm first, so set noauto to true
    to take them to the main page on successful login,
    or set it to a url to take them there instead.
    """

    if permission == "__never__":
        raise RuntimeError(
            "Nobody has the __never__ permission, ever, except in nosecurity mode."
        )

    if not isinstance(permission, str):
        p = permission
    else:
        p = [permission]
    for permission in p:
        if permission == "__guest__":
            continue

        user = getAcessingUser()

        # This is not a web request, this is the server itself
        if user == "__no_request__":
            return

        if (
            permission in auth.crossSiteRestrictedPermissions
            or not auth.getUserSetting(user, "allow-cors")
        ):
            noCrossSite()

        # If the special __guest__ user can do it, anybody can.
        if "__guest__" in auth.Users:
            if permission in auth.Users["__guest__"].permissions:
                return
            if "__all_permissions__" in auth.Users["__guest__"].permissions:
                return

        # Anything guest can't do needs https
        if not quart.request.scheme == "https":
            x = quart.request.remote_addr
            # Allow localhost, and Yggdrasil mesh.
            # This check is really just to be sure nobody accidentally uses HTTP,
            # But localhost and encrypted mesh are legitamate uses of HTTP.
            if not isHTTPAllowed(x):
                raise KaithemUserPermissionError(permission)

        if not auth.canUserDoThis(user, permission):
            raise KaithemUserPermissionError(permission)


def loginredirect(url):
    if quart.request and not quart.request.method == "GET":
        return quart.redirect("/login")

    return quart.redirect(
        "/login?go="
        + base64.b64encode(url.encode()).decode()
        + "&maxgotime-"
        + str(time.time() + 300)
    )


def geturl():
    return quart.request.url


def canUserDoThis(permissions, user=None, asgi=None):
    "None means get the user from the request context"

    # If we are in context aware mode also check for cross site permissions
    # As an extra layer of protection in case SameSite=Strict
    # and any other protections wasn't enough
    if (not user) or asgi:
        for permission in permissions:
            if permission in auth.crossSiteRestrictedPermissions:
                noCrossSite(asgi)

    # If a disallowed CORS post is detected here, we get __guest__
    user = user or getAcessingUser(asgi=asgi)

    if not isinstance(permissions, (list, tuple)):
        permissions = (permissions,)

    for permission in permissions:
        if not auth.canUserDoThis(user, permission):
            return False
    return True


def noCrossSite(asgi=None):
    if asgi:
        if asgi:
            try:
                r = Request(asgi)
            except Exception:
                r = WebSocket(asgi, None, None)

            headers = asgi["headers"]
            headers = {i.decode(): j.decode() for i, j in headers}
            if headers.get("Origin", ""):
                if not r.base_url == headers.get("Origin", ""):
                    raise PermissionError(
                        "Cannot make this request from a different origin"
                    )

    else:
        if quart.request.headers.get("Origin", ""):
            # Remove trailing slash
            if not quart.request.host_url[:-1] == quart.request.headers.get(
                "Origin", ""
            ):
                raise PermissionError(
                    "Cannot make this request from a different origin"
                )


def strictNoCrossSite():
    if not quart.request.base_url == quart.request.headers.get("Origin", ""):
        raise PermissionError(
            "Cannot make this request from a different origin, or from a requester that does not provide an origin"
        )


def getAcessingUser(asgi=None, quart_req=None):
    """Return the username of the user making the request bound to this thread or __guest__ if not logged in.
    The result of this function can be trusted because it uses the authentication token.
    """
    # Handle HTTP Basic Auth

    if asgi:
        try:
            r = Request(asgi)
        except Exception:
            r = WebSocket(asgi, None, None)

        headers = asgi["headers"]
        headers = {i.decode(): j.decode() for i, j in headers}
        scheme = asgi["scheme"]
        remote_ip = asgi["client"][0]
        cookie = r.cookies
        host = headers["host"]

    else:
        quart_req = quart_req or quart.request
        if not quart_req:
            return "__no_request__"

        headers = dict(quart_req.headers)
        scheme = quart_req.scheme
        remote_ip = quart_req.remote_addr
        cookie = quart_req.cookies
        host = quart_req.host

    if "Authorization" in headers:
        x = headers["Authorization"].split("Basic ")
        if len(x) > 1:
            # Get username and password from http header
            b = base64.b64decode(x[1]).decode()
            b = b.split(";")

            if not scheme == "https":
                # Basic auth over http is not secure at all, so we raise an error if we catch it.
                x = remote_ip
                if not isHTTPAllowed(x):
                    raise PermissionError(
                        "Cannot make this request from plain http"
                    )
            # Get token using username and password
            auth.userLogin(b[0], b[1])
            # Check the credentials of that token
            try:
                return auth.whoHasToken(cookie["kaithem_auth"])
            except KeyError:
                return "__guest__"
            except Exception:
                logging.exception("Error finding accessing user")
                return "__guest__"

    # Handle token based auth
    if "kaithem_auth" not in cookie or (not cookie["kaithem_auth"]):
        return "__guest__"
    try:
        user = auth.whoHasToken(cookie["kaithem_auth"])
        if not auth.getUserSetting(user, "allow-cors"):
            if headers.get("Origin", ""):
                x = (
                    headers.get("Origin", "")
                    .replace("http://", "")
                    .replace("https://", "")
                    .replace("ws://", "")
                    .replace("wss://", "")
                )
                x2 = headers.get("Origin", "")
                # Cherrypy and tornado compatibility
                if host not in (x, x2):
                    return "__guest__"
        return user

    except KeyError:
        return "__guest__"
    except Exception:
        logging.exception("Error in user lookup")
        return "__guest__"


class ServeFileInsteadOfRenderingPageException(Exception):
    def __init__(self, *args: object) -> None:
        self.f_filepath: str
        self.f_MIME: str
        self.f_name: str
        super().__init__(*args)


def serveFile(path, contenttype="", name=None):
    "Skip the rendering of the current page and Serve a static file instead."
    if name is None:
        name = path
    if not contenttype:
        c = mimetypes.guess_type(path, strict=True)
        if c[0]:
            contenttype = c[0]

    # Give it some text for when someone decides to call it from the wrong place
    e = ServeFileInsteadOfRenderingPageException(
        "If you see this exception, it means someone tried to serve a file from somewhere that was not a page."
    )
    e.f_filepath = path
    e.f_MIME = contenttype
    e.f_name = name
    raise e
