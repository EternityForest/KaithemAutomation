from mako.template import Template
from mako.lookup import TemplateLookup
import auth
import cherrypy

_Lookup = TemplateLookup(directories=['pages'])
get_template = _Lookup.get_template

#Redirect user to an error message if he does not have the proper permission.
def require(permission):
    if (not 'auth' in cherrypy.request.cookie) or cherrypy.request.cookie['auth'].value not in auth.Tokens:
       raise cherrypy.HTTPRedirect("/login/")
    if not auth.checkTokenPermission(cherrypy.request.cookie['auth'].value,permission):
        raise cherrypy.HTTPRedirect("/errors/permissionerror")