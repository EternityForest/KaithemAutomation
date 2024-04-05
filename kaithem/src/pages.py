# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import importlib
from . import config as cfg
from mako.lookup import TemplateLookup
import cherrypy
import base64
import weakref
import time
import logging
import os
import mimetypes
import jinja2
from . import auth, config
from . import directories, util
from typing import Dict

_Lookup = TemplateLookup(
    directories=[
        directories.htmldir,
        os.path.join(directories.htmldir, "makocomponents"),
    ]
)
get_template = _Lookup.get_template

_varLookup = TemplateLookup(directories=[directories.vardir])


#
_jl = jinja2.FileSystemLoader(
    [directories.htmldir, os.path.join(directories.htmldir, "jinjatemplates")],
    encoding="utf-8",
    followlinks=False,
)


env = jinja2.Environment(loader=_jl, autoescape=False)


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
    return _jl.load(env, n, env.globals).render(imp0rt=importlib.import_module, **kw)


def get_vardir_template(fn):
    return _varLookup.get_template(os.path.relpath(fn, directories.vardir))


nav_bar_plugins = weakref.WeakValueDictionary()


# There are cases where this may not exactly be perfect,
# but the point is just an extra guard against user error.
def isHTTPAllowed(ip):
    return (
        ip.startswith(
            ("::1", "127.", "::ffff:192.", "::ffff:10.", "192.", "10.", "fc", "fd")
        )
        or ip == "::ffff:127.0.0.1"
    )


nativeHandlers = weakref.WeakValueDictionary()


def getSubdomain():
    x = cherrypy.request.base.split("://", 1)[-1]

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
    if not cherrypy.request.method == "POST":
        user = getAcessingUser()
        # This is not a web request, this is the server itself
        if user == "__no_request__":
            return
        raise cherrypy.HTTPRedirect("/errors/wrongmethod")


def require(permission, noautoreturn=False):
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

        if permission in auth.crossSiteRestrictedPermissions or not auth.getUserSetting(
            user, "allow-cors"
        ):
            noCrossSite()

        # If the special __guest__ user can do it, anybody can.
        if "__guest__" in auth.Users:
            if permission in auth.Users["__guest__"].permissions:
                return
            if "__all_permissions__" in auth.Users["__guest__"].permissions:
                return

        # Anything guest can't do needs https
        if not cherrypy.request.scheme == "https":
            x = cherrypy.request.remote.ip
            # Allow localhost, and Yggdrasil mesh.
            # This check is really just to be sure nobody accidentally uses HTTP,
            # But localhost and encrypted mesh are legitamate uses of HTTP.
            if not isHTTPAllowed(x):
                raise cherrypy.HTTPRedirect("/errors/gosecure")

        if user == "__guest__":
            # The login page can auto return people to what they were doing before logging in
            # Don't autoreturn users that came here from a POST call.
            if noautoreturn or cherrypy.request.method == "POST":
                noautoreturn = True
            # Default to taking them to the main page.
            if noautoreturn:
                url = "/"
            else:
                url = cherrypy.url()
            # User has 5 minutes to log in.  Any more time
            # than that and it takes him back to the main page.
            # This is so it can't auto redirect
            # To something you forgot about and no longer want.
            raise cherrypy.HTTPRedirect(
                "/login?go="
                + base64.b64encode(url.encode()).decode()
                + "&maxgotime-"
                + str(time.time() + 300)
            )

        if not auth.canUserDoThis(user, permission):
            raise cherrypy.HTTPRedirect("/errors/permissionerror?")


def canUserDoThis(permissions, user=None):
    "None means get the user from the request context"

    # If a disallowed CORS post is detected here, we get __guest__
    user = user or getAcessingUser()

    if not isinstance(permissions, (list, tuple)):
        permissions = (permissions,)

    for permission in permissions:
        if permission in auth.crossSiteRestrictedPermissions:
            noCrossSite()
        if not auth.canUserDoThis(user, permission):
            return False
    return True


def noCrossSite():
    if cherrypy.request.headers.get("Origin", ""):
        if not cherrypy.request.base == cherrypy.request.headers.get("Origin", ""):
            raise PermissionError("Cannot make this request from a different origin")


def strictNoCrossSite():
    if not cherrypy.request.base == cherrypy.request.headers.get("Origin", ""):
        raise PermissionError(
            "Cannot make this request from a different origin, or from a requester that does not provide an origin"
        )


def getAcessingUser(tornado_mode=None):
    """Return the username of the user making the request bound to this thread or __guest__ if not logged in.
    The result of this function can be trusted because it uses the authentication token.
    """
    # Handle HTTP Basic Auth

    # Directly pass tornado request. Normally not needed, just for websocket stuff
    if tornado_mode:
        headers = tornado_mode.headers
        scheme = tornado_mode.protocol
        remote_ip = tornado_mode.remote_ip
        cookie = tornado_mode.cookies
        base = tornado_mode.host

    else:
        if (
            (not cherrypy.request.request_line)
            and (not cherrypy.request.app)
            and (not cherrypy.request.config)
        ):
            return "__no_request__"
        headers = cherrypy.request.headers
        scheme = cherrypy.request.scheme
        remote_ip = cherrypy.request.remote.ip
        cookie = cherrypy.request.cookie
        base = cherrypy.request.base

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
                    raise cherrypy.HTTPRedirect("/errors/gosecure")
            # Get token using username and password
            auth.userLogin(b[0], b[1])
            # Check the credentials of that token
            try:
                return auth.whoHasToken(cookie["kaithem_auth"].value)
            except KeyError:
                return "__guest__"
            except Exception:
                logging.exception("Error finding accessing user")
                return "__guest__"

    # Handle token based auth
    if "kaithem_auth" not in cookie or (not cookie["kaithem_auth"].value):
        return "__guest__"
    try:
        user = auth.whoHasToken(cookie["kaithem_auth"].value)
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
                if base not in (x, x2):
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
