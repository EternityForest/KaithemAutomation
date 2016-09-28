#Copyright Daniel Dunn 2013, 2015
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

import cherrypy, time
from . import pages, auth,util,messagebus


#Experimenal code not implemented, intended to send warning if the ratio of failed logins to real logins is excessive
#in a short period.
lastCleared = time.time()
recentAttempts = 0
alreadySent = 0

def onAttempt():
    if time.time()-lastCleared > 60*30:
        lastCleared = time.time()
        if recentAttempts < 50:
            alreadySent = 0
        recentAttempts = 0
    recentAttempts += 1
    if recentAttempts > 150 and not alreadysent:
        messagebus.postMessage("/system/notifications/warnings","Excessive number of failed attempts in the last 30 minutes.")

def onLogin():
    if time.time()-lastCleared > 60*30:
        lastCleared = 0
        if recentAttempts < 50:
            alreadySent = 0
        recentAttempts = 0
    recentAttempts -= 1.5


class LoginScreen():

    @cherrypy.expose
    def index(self,**kwargs):
        if not cherrypy.request.scheme == 'https':
            raise cherrypy.HTTPRedirect("/errors/gosecure")
        return pages.get_template("login.html").render(target=kwargs.get("go","/"))

    @cherrypy.expose
    def login(self,**kwargs):
        if auth.getUserSetting(pages.getAcessingUser(),"restrict-lan"):
            if not util.iis_private_ip(cherrypy.request.remote.ip):
                raise cherrypy.HTTPRedirect("/errors/localonly")

        if not cherrypy.request.scheme == 'https':
            raise cherrypy.HTTPRedirect("/errors/gosecure")
        time.sleep(0.005)
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
            x = auth.Users[kwargs['username']]
            if not 'loginhistory' in x:
                x['loginhistory'] = [(time.time(), cherrypy.request.remote.ip)]
            else:
                x['loginhistory'].append((time.time(), cherrypy.request.remote.ip))
                x['loginhistory'] = x['loginhistory'][:100]

            messagebus.postMessage("/system/auth/login",[kwargs['username'],cherrypy.request.remote.ip])
            if not "/errors/loginerror" in util.unurl(kwargs['go']):
                raise cherrypy.HTTPRedirect(util.unurl(kwargs['go']))
            else:
                raise cherrypy.HTTPRedirect("/")
        else:
            messagebus.postMessage("/system/auth/loginfail",[kwargs['username'],cherrypy.request.remote.ip])
            raise cherrypy.HTTPRedirect("/errors/loginerror")

    @cherrypy.expose
    def logout(self,**kwargs):
        #Change the security token to make the old one invalid and thus log user out.
        if cherrypy.request.cookie['auth'].value in auth.Tokens:
            messagebus.postMessage("/system/auth/logout",[auth.whoHasToken(cherrypy.request.cookie['auth'].value),cherrypy.request.remote.ip])
            auth.assignNewToken(auth.whoHasToken(cherrypy.request.cookie['auth'].value))
        raise cherrypy.HTTPRedirect("/")
