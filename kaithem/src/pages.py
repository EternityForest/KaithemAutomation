#Copyright Daniel Dunn 2013. 2015,2017
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
import cherrypy,base64,weakref,threading,time
from . import auth,config
from . import directories,util

_Lookup = TemplateLookup(directories=[directories.htmldir])
get_template = _Lookup.get_template

webResources = {}

webResourceLock = threading.Lock()

#Indexed by (time, name, url) pairs
allWebResources = {}

class WebResource():
    """
    Represents a pointer to a URL that can be looked up by name, so that looking up 'jquery' could tell you the actual URL.
    Creating this class registers it in the list.
    """
    def __init__(self,name,url,priority=50):
        self.url = url
        self.priority = 50
        self.identifier = (time.time(), name,url)
        
        with webResourceLock:
            allWebResources[self.identifier]=self
        
            if name in webResources:
                o =webResources[name]
                if o.priority <= self.priority:
                    webResources[name] = self
            else:
                webResources[name] = self


    def __del__(self):
        with webResourceLock:
            if self.name in webResources and webResources[self.name]==self:
                del webResources[self.name]
            #Deletion should be rare, and we should only have a few thousand at most.
            #we can afford to rescan the whole list under lock.
            for i in allWebResources:
                if i[1]==self.name:
                    if not self.name in webResources:
                        webResources[self.name] = allWebResources[i]
                    else:
                        if i[3]>=webResources[self.name.priority]:
                            webResources[self.name] = allWebResources[i]

vue = WebResource("vue-2.5.16","/static/js/vue-2.6.10.js")
vue2 = WebResource("vue-default","/static/js/vue-2.6.10.js")
vue3 = WebResource("vue2-default","/static/js/vue-2.6.10.js")


#
nativeHandlers = weakref.WeakValueDictionary()

   


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

    if not isinstance(permission,str):
        p=permission
    else:
        p = [permission]
    for permission in p:

        #If the special __guest__ user can do it, anybody can.
        if '__guest__' in auth.Users:
            if permission in auth.Users['__guest__'].permissions:
                return
            if "__all_permissions__" in auth.Users['__guest__'].permissions:
                return

        #Anything guest can't do needs https
        if not cherrypy.request.scheme == 'https':
            raise cherrypy.HTTPRedirect("/errors/gosecure")

        user = getAcessingUser()

        if user=="<unknown>":
            #The login page can auto return people to what they were doing before logging in
            #Don't autoreturn users that came here from a POST call.
            if noautoreturn or cherrypy.request.method == 'POST':
                noautoreturn = True
            #Default to taking them to the main page.
            if noautoreturn:
                url = util.url("/")
            else:
                url = util.url(cherrypy.url())
            raise cherrypy.HTTPRedirect("/login?go="+url)

        if not auth.canUserDoThis(user,permission):
            raise cherrypy.HTTPRedirect("/errors/permissionerror?")


if config.argcmd.nosecurity:
    def require(*args,**kwargs):
        return


def canUserDoThis(permission):
    return auth.canUserDoThis(getAcessingUser(),permission)

def getAcessingUser():
    """Return the username of the user making the request bound to this thread or <UNKNOWN> if not logged in.
        The result of this function can be trusted because it uses the authentication token.
    """
    #Handle HTTP Basic Auth
    if "Authorization" in cherrypy.request.headers:
        x = cherrypy.request.headers['Authorization'].split("Basic ")
        if len(x)>1:
            #Get username and password from http header
            b = base64.b64decode(x[1])
            b = b.split(";")
            if not cherrypy.request.scheme == 'https':
                #Basic auth over http is not secure at all, so we raise an error if we catch it.
                raise cherrypy.HTTPRedirect("/errors/gosecure")
            #Get token using username and password
            t = userLogin(b[0],b[1])
            #Check the credentials of that token
            try:
                return auth.whoHasToken(cherrypy.request.cookie['auth'].value)
            except:
                return "<unknown>"
                
    #Handle token based auth
    if not 'auth' in cherrypy.request.cookie or (not cherrypy.request.cookie['auth'].value):
        return "<unknown>"
    try:
        return auth.whoHasToken(cherrypy.request.cookie['auth'].value)
    except:
        return "<unknown>"
