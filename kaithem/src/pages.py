#Copyright Daniel Dunn 2013. 2015
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

from mako.template import Template
from mako.lookup import TemplateLookup
import cherrypy,base64
from . import auth
from . import directories,auth,util

_Lookup = TemplateLookup(directories=[directories.htmldir])
get_template = _Lookup.get_template

def postOnly():
    """Redirect user to main page if the request is anything but POST"""
    if not cherrypy.request.method == "POST":
        raise cherrypy.HTTPRedirect("/errors/wrongmethod")

#Redirect user to an error message if he does not have the proper permission.
def require(permission, noautoreturn = False):
    """Get the user that is making the request bound to this thread,
        and then raise an interrupt if he does not have the permission specified.

        Normally this will prompt the user to go to a login page, and if they log in it takes them right back where they were
        trying to go. However if the place they were going has an effect, you might want them to confirm first, so set noauto to true
        to take them to the main page on successful login, or set it to a url to take them there instead.
        """

    #If the special __guest__ user can do it, anybody can.
    if '__guest__' in auth.Users:
        if permission in auth.Users['__guest__'].permissions:
            return
    #Don't autoreturn users that came here from a POST call.
    if not noautoreturn and cherrypy.request.method == 'POST':
        noautoreturn = True

    #Default to taking them to the main page.
    if noautoreturn is True:
        noautoreturn = '/'

    if noautoreturn:
        url = util.url(noautoreturn)
    else:
        url = util.url(cherrypy.url())

    if "Authorization" in cherrypy.request.headers:
        x = cherrypy.request.headers['Authorization'].split("Basic ")
        if len(x)>1:
            #Get username and password from http header
            b = base64.b64decode(x[1])
            b = b.split(";")
            if not cherrypy.request.scheme == 'https':
                raise cherrypy.HTTPRedirect("/errors/gosecure")
            #Get token using sername and password
            t = userLogin(b[0],b[1])
            #Check the credentials of that token
            if t not in auth.Tokens:
                raise cherrypy.HTTPRedirect("/login?"+url)
            if not auth.checkTokenPermission(t,permission):
                raise cherrypy.HTTPRedirect("/errors/permissionerror?")
            else:
                return True

    if not cherrypy.request.scheme == 'https':
        raise cherrypy.HTTPRedirect("/errors/gosecure")
    if not 'auth' in cherrypy.request.cookie:
        raise cherrypy.HTTPRedirect("/login?"+url)
    if cherrypy.request.cookie['auth'].value not in auth.Tokens:
        raise cherrypy.HTTPRedirect("/login?"+url)
    if not auth.checkTokenPermission(cherrypy.request.cookie['auth'].value,permission):
        raise cherrypy.HTTPRedirect("/errors/permissionerror?")

def canUserDoThis(permission):
        #If the special __guest__ user can do it, anybody can.
    if '__guest__' in auth.Users:
        if permission in auth.Users['__guest__'].permissions:
            return True
    #if we are using http, this should catch it beause the ookie is https only
    if not 'auth' in cherrypy.request.cookie:
        return False

    #Don't allow users to do things that require permission via HTTP
    if not cherrypy.request.scheme == 'https':
        return False

    if cherrypy.request.cookie['auth'].value not in auth.Tokens:
        return False

    if not auth.checkTokenPermission(cherrypy.request.cookie['auth'].value,permission):
        return False

    return True

def getAcessingUser():
    """Return the username of the user making the request bound to this thread or <UNKNOWN> if not logged in.
       The result of this function can be trusted because it uses the authentication token.
    """
    if (not 'auth' in cherrypy.request.cookie) or cherrypy.request.cookie['auth'].value not in auth.Tokens:
       return "<unknown>"
    return auth.whoHasToken(cherrypy.request.cookie['auth'].value)
