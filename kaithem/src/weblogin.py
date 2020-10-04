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

import cherrypy, time,collections,threading,logging
from . import pages, auth,util,messagebus


#Experimenal code not implemented, intended to send warning if the ratio of failed logins to real logins is excessive
#in a short period.
lastCleared = time.time()
recentAttempts = 0
alreadySent = 0

logger = logging.getLogger("system.auth")
failureRecords = collections.OrderedDict()
recordslock = threading.Lock()

#indexed by username, they are numbers of what time to lock out logins until
lockouts = {}



def onAttempt():
    if time.time()-lastCleared > 60*30:
        lastCleared = time.time()
        if recentAttempts < 50:
            alreadySent = 0
        recentAttempts = 0
    recentAttempts += 1
    if recentAttempts > 150 and not alreadysent:
        logging.warning("Many failed login attempts have occurred")
        messagebus.postMessage("/system/notifications/warnings","Excessive number of failed attempts in the last 30 minutes.")

def onLogin():
    if time.time()-lastCleared > 60*30:
        lastCleared = 0
        if recentAttempts < 50:
            alreadySent = 0
        recentAttempts = 0
    recentAttempts -= 1.5

def onFail(ip,user,lockout=True):
    with recordslock:
        if ip in failureRecords:
            r = failureRecords[ip]
            failureRecords[ip] = (time.time(), r[1]+1,user)
        else:
            failureRecords[ip] = (time.time(), 1,user)

        if len(failureRecords)> 1000:
            failureRecords.popitem(last=False)
    if lockout:
        if user in auth.Users:
            lockouts[user]=time.time()+3
class LoginScreen():

    @cherrypy.expose
    def index(self,**kwargs):
        if not cherrypy.request.scheme == 'https':
            raise cherrypy.HTTPRedirect("/errors/gosecure")
        return pages.get_template("login.html").render(target=kwargs.get("go","/"))

    @cherrypy.expose
    def login(self,**kwargs):
        #Handle some nuisiance errors.

        if not 'username' in kwargs:
            raise cherrypy.HTTPRedirect("/")
        
        if "__nologin__" in pages.getSubdomain():
            raise RuntimeError("To prevent XSS attacks, login is forbidden from any subdomain containing __nologin__")

        #Empty fields try the default. But don't autofill username if password is set.
        #If that actually worked because someone didn't fill the username in, they might be confused and
        #feel like the thing wasn't validating input at all.
        if not kwargs['username'] and not kwargs['password']:
            kwargs['username']='admin'
        if not kwargs['password']:
            kwargs['password']='password'

        if auth.getUserSetting(pages.getAcessingUser(),"restrict-lan"):
            if not util.iis_private_ip(cherrypy.request.remote.ip):
                raise cherrypy.HTTPRedirect("/errors/localonly")

        if not cherrypy.request.scheme == 'https':
            raise cherrypy.HTTPRedirect("/errors/gosecure")
        #Insert a delay that has a random component of up to 256us that is derived from the username
        #and password, to prevent anyone from being able to average it out, as it is the same per
        #query
        auth.resist_timing_attack(kwargs['username'].encode("utf8")+kwargs['password'].encode("utf8"))
        x = auth.userLogin(kwargs['username'],kwargs['password'])
        #Don't ratelimit very long passwords, we'll just assume they are secure
        #Someone might still make a very long insecure password, but
        #for now lets assume that people with long passwords know what they're doing.
        if len(kwargs['password'])<32:
            if kwargs['username'] in lockouts:
                if time.time()<lockouts[kwargs['username']]:
                    raise RuntimeError("Maximum 1 login attempt per 3 seconds per account.")
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
            #tokens are good for 90 days
            cherrypy.response.cookie['auth']['expires'] = 24*60*60*90
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
            onFail(cherrypy.request.remote.ip,kwargs['username'])
            messagebus.postMessage("/system/auth/loginfail",[kwargs['username'],cherrypy.request.remote.ip])
            raise cherrypy.HTTPRedirect("/errors/loginerror")

    @cherrypy.expose
    def logout(self,**kwargs):
        #Change the security token to make the old one invalid and thus log user out.
        if cherrypy.request.cookie['auth'].value in auth.Tokens:
            messagebus.postMessage("/system/auth/logout",[auth.whoHasToken(cherrypy.request.cookie['auth'].value),cherrypy.request.remote.ip])
            auth.assignNewToken(auth.whoHasToken(cherrypy.request.cookie['auth'].value))
        raise cherrypy.HTTPRedirect("/")
