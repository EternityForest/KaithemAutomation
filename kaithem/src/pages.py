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

from src import config as cfg
from mako.template import Template
from mako.lookup import TemplateLookup
import cherrypy
import base64
import weakref
import threading
import time
import logging
import os
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


webResources = {}

webResourceLock = threading.Lock()

# Indexed by (time, name, url) pairs
allWebResources = {}


class WebResource():
    """
    Represents a pointer to a URL that can be looked up by name, so that looking up 'jquery' could tell you the actual URL.
    Creating this class registers it in the list.
    """

    def __init__(self, name, url, priority=50):
        self.url = url
        self.priority = 50
        self.identifier = (time.time(), name, url)

        with webResourceLock:
            allWebResources[self.identifier] = self

            if name in webResources:
                o = webResources[name]
                if o.priority <= self.priority:
                    webResources[name] = self
            else:
                webResources[name] = self

    def __del__(self):
        with webResourceLock:
            if self.name in webResources and webResources[self.name] == self:
                del webResources[self.name]
            # Deletion should be rare, and we should only have a few thousand at most.
            # we can afford to rescan the whole list under lock.
            for i in allWebResources:
                if i[1] == self.name:
                    if not self.name in webResources:
                        webResources[self.name] = allWebResources[i]
                    else:
                        if i[3] >= webResources[self.name.priority]:
                            webResources[self.name] = allWebResources[i]


vue = WebResource("vue-2.5.16", "/static/js/vue-2.6.10.js")
vue2 = WebResource("vue-default", "/static/js/vue-2.6.10.js")
vue3 = WebResource("vue2-default", "/static/js/vue-2.6.10.js")


#
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
            if cherrypy.request.remote.ip.startswith("127."):
                return True
            elif cherrypy.request.remote.ip == "::1":
                return True
            else:
                raise RuntimeError(
                    "Nosecurity 1 enabled, but got request from ext IP:"+str(cherrypy.request.remote.ip))
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
            if not x.startswith == "::1" or x.startswith("127.") or x.startswith("200::") or x.startswith("300::"):
                raise cherrypy.HTTPRedirect("/errors/gosecure")

        user = getAcessingUser()

        if user == "__guest__":
            # The login page can auto return people to what they were doing before logging in
            # Don't autoreturn users that came here from a POST call.
            if noautoreturn or cherrypy.request.method == 'POST':
                noautoreturn = True
            # Default to taking them to the main page.
            if noautoreturn:
                url = util.url("/")
            else:
                url = util.url(cherrypy.url())
            raise cherrypy.HTTPRedirect("/login?go="+url)

        if not auth.canUserDoThis(user, permission):
            raise cherrypy.HTTPRedirect("/errors/permissionerror?")


# In NoSecurity mode we do things a bit differently
def canUserDoThis(permissions, user=None):
    "None means get the user from the request context"

    if not isinstance(permissions, (list, tuple)):
        permissions = (permissions,)

    for permission in permissions:
        if not auth.canUserDoThis(user or getAcessingUser(), permission):
            return False
    return True


if noSecurityMode:
    def require(*args, **kwargs):
        if canOverrideSecurity():
            return True
        raise cherrypy.HTTPRedirect("/errors/permissionerror?")

    def require(*args, **kwargs):
        if canOverrideSecurity():
            return True
        raise auth.canUserDoThis(getAcessingUser(), permission)


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
                raise cherrypy.HTTPRedirect("/errors/gosecure")
            # Get token using username and password
            t = userLogin(b[0], b[1])
            # Check the credentials of that token
            try:
                return auth.whoHasToken(cherrypy.request.cookie['auth'].value)
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
        return auth.whoHasToken(cherrypy.request.cookie['auth'].value)
    except:
        return "__guest__"
