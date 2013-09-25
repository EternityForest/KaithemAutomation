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

import cherrypy
from . import pages, auth,util

class LoginScreen():

    @cherrypy.expose
    def index(self,**kwargs):
        if not cherrypy.request.scheme == 'https':
            raise cherrypy.HTTPRedirect("/errors/gosecure")
        return pages.get_template("login.html").render()
        
    @cherrypy.expose
    def login(self,**kwargs):
        if not cherrypy.request.scheme == 'https':
            raise cherrypy.HTTPRedirect("/errors/gosecure")
        x = auth.userLogin(kwargs['username'],kwargs['pwd'])
        if not x=='failure':
            #Give the user the security token.
            #AFAIK this is and should at least for now be the
            #ONLY place in which the auth cookie is set.
            cherrypy.response.cookie['auth'] = x
            cherrypy.response.cookie['auth']['path'] = '/'
            #This auth cookie REALLY does not belong anywhere near an unsecured connection.
            #For some reason, empty strings seem to mean "Don't put this attribute in.
            #Always test, folks!
            cherrypy.response.cookie['auth']['secure'] = ' '
            cherrypy.response.cookie['auth']['httponly'] = ' '
            raise cherrypy.HTTPRedirect(util.unurl(kwargs['go']))
        else:
            raise cherrypy.HTTPRedirect("/errors/loginerror")
            
    @cherrypy.expose
    def logout(self,**kwargs):
        #Change the securit token to make the old one invalid and thus log user out.
        if cherrypy.request.cookie['auth'].value in auth.Tokens:
            auth.assignNewToken(auth.whoHasToken(cherrypy.request.cookie['auth'].value))
        raise cherrypy.HTTPRedirect("/")
