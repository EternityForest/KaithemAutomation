

# Copyright Daniel Dunn 2013. 2015,2017
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

from . import config as cfg
from mako.template import Template
from mako.lookup import TemplateLookup
import cherrypy
import base64
import weakref
import threading
import time
import logging
import os
import mimetypes
from . import auth, config
from . import directories, util
from mako import exceptions


_Lookup = TemplateLookup(directories=[directories.htmldir])
get_template = _Lookup.get_template

_varLookup = TemplateLookup(directories=[directories.vardir])


def get_vardir_template(fn):
    return _varLookup.get_template(os.path.relpath(fn, directories.vardir))


noSecurityMode = False

mode = int(cfg.argcmd.nosecurity) if cfg.argcmd.nosecurity else None
# limit nosecurity to localhost
if mode == 1:
    bindto = '127.0.0.1'
    noSecurityMode = 1

# Unless it's mode 2
if mode == 2:
    noSecurityMode = 2

# Unless it's mode 2
if mode == 3:
    noSecurityMode = 3


navBarPlugins = weakref.WeakValueDictionary()


#There are cases where this may not exactly be perfect, but the point is just an extra guard against user error.
def isHTTPAllowed(ip):
   return (ip.startswith("::1") or ip.startswith("127.") or ip =='::ffff:127.0.0.1' or ip.startswith("::ffff:192.") or  ip.startswith("::ffff:10.") or ip.startswith("192.") or ip.startswith("10.") or ip.startswith("fc") or ip.startswith("fd"))


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
        if i.isnumeric() or i.startswith('localhost:') or '[' in i:
            # Pad with fake TLD for numeric ip addr
            x.append(".faketld")
            break

    # Get rid of last two parts, the host and tld
    return list(reversed(x[:-2]))


def postOnly():
    """Redirect user to main page if the request is anything but POST"""
    if not cherrypy.request.method == "POST":
        raise cherrypy.HTTPRedirect("/errors/wrongmethod")


def canOverrideSecurity():
    "Check if nosecuritymode overrides for this request"
    global noSecurityMode

    if noSecurityMode:
        if noSecurityMode == 1:
            x=cherrypy.request.remote.ip
            if isHTTPAllowed(x):
                return True
            else:
                raise RuntimeError(
                    "Nosecurity 1 enabled, but got request from ext IP:" + str(cherrypy.request.remote.ip))
                return False

        if noSecurityMode == 2:
            x = cherrypy.request.remote.ip
            if cherrypy.request.remote.ip.startswith == "::1":
                return True
            if x.startswith("192."):
                return True
            if x.startswith("10."):
                return True
            if x.startswith("127."):
                return True
            return False

        if noSecurityMode == 3:
            return True


def require(permission, noautoreturn=False):
    """Get the user that is making the request bound to this thread,
        and then raise an interrupt if he does not have the permission specified.

        Normally this will prompt the user to go to a login page, and if they log in it takes them right back where they were
        trying to go. However if the place they were going has an effect, you might want them to confirm first, so set noauto to true
        to take them to the main page on successful login, or set it to a url to take them there instead.
        """

    if permission == "__never__":
        raise RuntimeError(
            "Nobody has the __never__ permission, ever, except in nosecurity mode.")

    if not isinstance(permission, str):
        p = permission
    else:
        p = [permission]
    for permission in p:
        if permission =='__guest__':
            continue

        user = getAcessingUser()

        if permission in auth.crossSiteRestrictedPermissions or not auth.getUserSetting(user, 'allow-cors'):
            noCrossSite()

        # If the special __guest__ user can do it, anybody can.
        if '__guest__' in auth.Users:
            if permission in auth.Users['__guest__'].permissions:
                return
            if "__all_permissions__" in auth.Users['__guest__'].permissions:
                return

        # Anything guest can't do needs https
        if not cherrypy.request.scheme == 'https':
            x = cherrypy.request.remote.ip
            # Allow localhost, and Yggdrasil mesh. This check is really just to be sure nobody accidentally uses HTTP,
            # But localhost and encrypted mesh are legitamate uses of HTTP.
            if not isHTTPAllowed(x):
                raise cherrypy.HTTPRedirect("/errors/gosecure")


        if user == "__guest__":
            # The login page can auto return people to what they were doing before logging in
            # Don't autoreturn users that came here from a POST call.
            if noautoreturn or cherrypy.request.method == 'POST':
                noautoreturn = True
            # Default to taking them to the main page.
            if noautoreturn:
                url = "/"
            else:
                url = cherrypy.url()
            # User has 5 minutes to log in.  Any more time than that and it takes him back to the main page.  This is so it can't auto redirect
            # To something you forgot about and no longer want.
            raise cherrypy.HTTPRedirect("/login?go=" + base64.b64encode(
                url.encode()).decode() + "&maxgotime-" + str(time.time() + 300))

        if not auth.canUserDoThis(user, permission):
            raise cherrypy.HTTPRedirect("/errors/permissionerror?")


# In NoSecurity mode we do things a bit differently
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


if noSecurityMode:
    def require(*args, **kwargs):
        if canOverrideSecurity():
            return True
        raise cherrypy.HTTPRedirect("/errors/permissionerror?")

    def require(permission, *args, **kwargs):
        if canOverrideSecurity():
            return True
        raise auth.canUserDoThis(getAcessingUser(), permission)



def noCrossSite():
    if cherrypy.request.headers.get("Origin",''):
        if not cherrypy.request.base == cherrypy.request.headers.get("Origin",''):
            raise PermissionError("Cannot make this request from a different origin")

def strictNoCrossSite():
    if not cherrypy.request.base == cherrypy.request.headers.get("Origin",''):
        raise PermissionError("Cannot make this request from a different origin, or from a requester that does not provide an origin")



def getAcessingUser():
    """Return the username of the user making the request bound to this thread or __guest__ if not logged in.
        The result of this function can be trusted because it uses the authentication token.
    """
    # Handle HTTP Basic Auth
    if "Authorization" in cherrypy.request.headers:
        x = cherrypy.request.headers['Authorization'].split("Basic ")
        if len(x) > 1:
            # Get username and password from http header
            b = base64.b64decode(x[1])
            b = b.split(";")

            if not cherrypy.request.scheme == 'https':
                # Basic auth over http is not secure at all, so we raise an error if we catch it.
                x = cherrypy.request.remote.ip
                if not isHTTPAllowed(x):
                    raise cherrypy.HTTPRedirect("/errors/gosecure")
            # Get token using username and password
            t = userLogin(b[0], b[1])
            # Check the credentials of that token
            try:
                return auth.whoHasToken(cherrypy.request.cookie['auth'].value)
            except KeyError:
                return "__guest__"
            except:
                logging.exception("Error finding accessing user")
                return "__guest__"

    if noSecurityMode:
        if canOverrideSecurity():
            return "admin"
    # Handle token based auth
    if not 'auth' in cherrypy.request.cookie or (not cherrypy.request.cookie['auth'].value):
        return "__guest__"
    try:
        user =  auth.whoHasToken(cherrypy.request.cookie['auth'].value)
        if not auth.getUserSetting(user, 'allow-cors'):
            if cherrypy.request.headers.get("Origin",''):
                if not cherrypy.request.base == cherrypy.request.headers.get("Origin",''):
                    return "__guest__"
        return user

    except KeyError:
            return "__guest__"
    except:
        logging.exception("Error in user lookup")
        return "__guest__"


class ServeFileInsteadOfRenderingPageException(Exception):
    pass


def serveFile(path, contenttype="", name=None):
    "Skip the rendering of the current page and Serve a static file instead."
    if name == None:
        name = path
    if not contenttype:
        c= mimetypes.guess_type(path, strict=True)
        if c[0]:
            contenttype = c[0]
            
    # Give it some text for when someone decides to call it from the wrong place
    e = ServeFileInsteadOfRenderingPageException(
        "If you see this exception, it means someone tried to serve a file from somewhere that was not a page.")
    e.f_filepath = path
    e.f_MIME = contenttype
    e.f_name = name
    raise e