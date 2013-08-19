#!/usr/bin/python3
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



#This file is the main entry point of the app

import sys,os

#There is actually a very good reason to change the import path here.
#It means we can refer to an installed copy of a library by the same name
#We use for the copy we include. If the user has an installed version, his will be used.
#If not, it will fall back to ours.
sys.path.append(os.path.join(sys.path[0],'src','thirdparty'))

#There are some libraries that are actually different for 3 and 2, so we use the apprpriate one
#By changing the pathe to include the proper ones.
if sys.version_info < (3,0):
    sys.path.append(os.path.join(sys.path[0],'src','thirdparty','python2'))
else:
    sys.path.append(os.path.join(sys.path[0],'src','thirdparty','python3'))

import time
import cherrypy
from src import util
from src import pages
from src import weblogin
from src import auth
from src import ManageUsers
from src import directories
from src import modules
from src import settings
from src import usrpages
from src import messagebus
from src import notifications
from src import messagelogging
from src import systasks

from src.config import config

def updateIP():
    global MyExternalIPAdress
    #2 and 3 have basically the same module with diferent names
    if sys.version_info < (3,0):
        from urllib2 import urlopen
    else:
        from urllib.request import urlopen
        
    #Yes, This really is the only way i know of to get your public IP.
    try:
        if config['get-public-ip']:
            u= urlopen("http://ipecho.net/plain", timeout = 60)
        MyExternalIPAdress = u.read()
        
        if sys.version_info > (3,0):
            MyExternalIPAdress = MyExternalIPAdress.decode('utf8')
    except:
        MyExternalIPAdress = "unknown"
    finally:
        try:
            u.close()
        except Exception:
            pass
        
updateIP()
        

port = config['port']

#Initialize the authorization module
auth.initializeAuthentication()

#Load all modules from the active modules directory
modules.loadAll()

#This class represents the "/" root o the web app
class webapproot():
    
   #"/" is mapped to this 
    @cherrypy.expose 
    def index(self,*path,**data):
        #Was there a reason not to use pages.require
        if 'auth' in cherrypy.request.cookie.keys():
            if auth.checkTokenPermission(cherrypy.request.cookie['auth'].value,"/admin/mainpage.view"):
                return pages.get_template('index.html').render(
                user = cherrypy.request.cookie['user'].value,
                                )
            else:
                return self.pagelisting()
        else:
            return self.login.index()

    @cherrypy.expose 
    def save(self,*path,**data):
        pages.require('/admin/settings.edit')
        return pages.get_template('save.html').render()
        
    @cherrypy.expose 
    def pagelisting(self,*path,**data):
        pages.require('/users/pagelisting.view')
        return pages.get_template('pagelisting.html').render(modules = modules.ActiveModules)
        
    #docs,about,helpmenu, and license are just static pages
    @cherrypy.expose 
    def docs(self,*path,**data):
        return pages.get_template('help/help.html').render()
    
    @cherrypy.expose 
    def makohelp(self,*path,**data):
        return pages.get_template('help/makoreference.html').render()
    
    @cherrypy.expose 
    def about(self,*path,**data):
        return pages.get_template('help/about.html').render(myip = MyExternalIPAdress)
    @cherrypy.expose 
    def helpmenu(self,*path,**data):
        return pages.get_template('help/index.html').render()
    @cherrypy.expose 
    def license(self,*path,**data):
        return pages.get_template('help/license.html').render()

class Errors():
    @cherrypy.expose 
    def permissionerror(self,):
        return pages.get_template('errors/permissionerror.html').render()
    @cherrypy.expose 
    def alreadyexists(self,):
        return pages.get_template('errors/alreadyexists.html').render()
    @cherrypy.expose 
    def loginerror(self,):
        return pages.get_template('errors/loginerror.html').render()
    @cherrypy.expose 
    def wrongmethod(self,):
        cherrypy.response.status = 405
        return pages.get_template('errors/wrongmethod.html').render()
    @cherrypy.expose 
    def error(self,):
        cherrypy.response.status = 500
        return pages.get_template('errors/wrongmethod.html').render()
       
#There are lots of other objects ad classes represeting subfolders of the website so we attatch them        
root = webapproot()
root.login = weblogin.LoginScreen()
root.auth = ManageUsers.ManageAuthorization()
root.modules = modules.WebInterface()
root.settings = settings.Settings()
root.errors = Errors()
root.pages = usrpages.KaithemPage()
root.logs = messagelogging.WebInterface()

#Start cherrrypy
dn = os.path.dirname(os.path.realpath(__file__))

if config['local-access-only']:
    bindto = '127.0.0.1'
else:
    bindto = '0.0.0.0'
    
if __name__ == '__main__':
    server_config={
        'server.socket_host': bindto,
        'server.socket_port':port,
        'server.ssl_module':'builtin',
        'server.ssl_certificate':os.path.join(directories.ssldir,'certificate.cert'),
        'server.ssl_private_key':os.path.join(directories.ssldir,'certificate.key'),
        'server.thread_pool':config['cherrypy-thread-pool']
    }
    
cherrypy.config["tools.encode.on"] = True
cherrypy.config["tools.encode.encoding"] = "utf-8"
cherrypy.config["tools.decode.on"] = True
cherrypy.config["tools.decode.encoding"] = "utf-8"

    

def addheader(*args,**kwargs):
    "This function's only purpose is to tell the browser to cache requests for an hour"
    cherrypy.response.headers['Cache-Control'] = "max-age=3600"
    #del cherrypy.response.headers['Expires']
    
def pageloadnotify(*args,**kwargs):
    systasks.aPageJustLoaded()
    
cherrypy.tools.pageloadnotify = cherrypy.Tool('on_start_resource', pageloadnotify)
cherrypy.config['tools.pageloadnotify.on'] = True

cherrypy.tools.addheader = cherrypy.Tool('before_finalize', addheader)

conf = {
        '/static':
        {'tools.staticdir.on': True,
        'tools.staticdir.dir':os.path.join(dn,'data/static'),
        "tools.sessions.on": False,
        'tools.caching.on' : True,
        'tools.caching.delay' : 3600,
        "tools.caching.expires": 3600,
        "tools.addheader.on": True
        }
        }
#Let the user create additional static directories
for i in config['serve-static']:
    if i not in conf:
        conf["/usr/static/"+i]= {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': config['serve-static'][i],
        "tools.sessions.on": False,
        'tools.caching.on' : True,
        'tools.caching.delay' : 3600,
        "tools.addheader.on": True
        }

cherrypy.config.update(server_config)

messagebus.postMessage('/system/startup','System Initialized')
messagebus.postMessage('/system/notifications','System Initialized at ' + time.strftime(config['time-format']))
cherrypy.quickstart(root,'/',config=conf)
