#Copyright Daniel Black 2013
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
import cherrypy

from . import directories,auth,util

_Lookup = TemplateLookup(directories=[directories.htmldir])
get_template = _Lookup.get_template

#Redirect user to an error message if he does not have the proper permission.
def require(permission):
    """Get the user that is making the request bound to this thread, 
        and then raise an interrupt if he does not have the permission specified"""
        
    if not cherrypy.request.scheme == 'https':
        raise cherrypy.HTTPRedirect("/errors/gosecure")
    if (not 'auth' in cherrypy.request.cookie) or cherrypy.request.cookie['auth'].value not in auth.Tokens:
       raise cherrypy.HTTPRedirect("/login?"+util.url(cherrypy.url()))
    if not auth.checkTokenPermission(cherrypy.request.cookie['auth'].value,permission):
        raise cherrypy.HTTPRedirect("/errors/permissionerror")
    
def getAcessingUser():
    """Return the username of the user making the request bound to this thread or <UNKNOWN> if not logged in.
       The result of this function can be trusted because it uses the authentication token.
    """
    if (not 'auth' in cherrypy.request.cookie) or cherrypy.request.cookie['auth'].value not in auth.Tokens:
       return "<unknown>"
    return auth.whoHasToken(cherrypy.request.cookie['auth'].value)