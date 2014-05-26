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



#This file is the main entry point of the app. It imports everything, loads configuration,
#sets up and starts the server, and contains page handlers for the main page.

import sys,os,threading

#There is actually a very good reason to change the import path here.
#It means we can refer to an installed copy of a library by the same name
#We use for the copy we include. If the user has an installed version, his will be used.
#If not, it will fall back to ours.
sys.path.append(os.path.join(sys.path[0],'src','thirdparty'))

#There are some libraries that are actually different for 3 and 2, so we use the appropriate one
#By changing the pathe to include the proper ones.
if sys.version_info < (3,0):
    sys.path.append(os.path.join(sys.path[0],'src','thirdparty','python2'))
    from gzip import open as opengzip
else:
    from gzip import GzipFile as opengzip
    sys.path.append(os.path.join(sys.path[0],'src','thirdparty','python3'))

    
import time,signal
import cherrypy,validictory
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
from src import registry
from src import widgets

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
        


#Initialize the authorization module
auth.initializeAuthentication()

#Load all modules from the active modules directory
modules.loadAll()

#This class represents the "/" root of the web app
class webapproot():
    
   #"/" is mapped to this 
    @cherrypy.expose 
    def index(self,*path,**data):
        pages.require("/admin/mainpage.view")
        cherrypy.response.cookie['LastSawMainPage'] = time.time()
        return pages.get_template('index.html').render()
        
    @cherrypy.expose 
    def pagelisting(self,*path,**data):
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
    def gosecure(self,):
        return pages.get_template('errors/gosecure.html').render()
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
root.notifications = notifications.WI()
root.widgets = widgets.WebInterface()

#Start cherrrypy
dn = os.path.dirname(os.path.realpath(__file__))

if config['local-access-only']:
    bindto = '127.0.0.1'
else:
    bindto = '0.0.0.0'


site_config={
        "tools.encode.on" :True,
        "tools.encode.encoding":'utf-8',
        "tools.decode.on": True,
        "tools.decode.encoding": 'utf-8',
        'log.screen': config['cherrypy-log-stdout'],
        'server.socket_host': bindto,
        'server.socket_port': config['https-port'],
        'server.ssl_module':'builtin',
        'server.ssl_certificate':os.path.join(directories.ssldir,'certificate.cert'),
        'server.ssl_private_key':os.path.join(directories.ssldir,'certificate.key'),
        'server.thread_pool':config['https-thread-pool']
}

cnf={
    '/static':
        {'tools.staticdir.on': True,
        'tools.staticdir.dir':os.path.join(dn,'data/static'),
        "tools.sessions.on": False,
        'tools.caching.on' : True,
        'tools.caching.delay' : 3600,
        "tools.caching.expires": 3600,
        "tools.addheader.on": True
        },
     '/pages':
        {
         'request.dispatch': cherrypy.dispatch.MethodDispatcher()
        }
     
}
#Let the user create additional static directories
for i in config['serve-static']:
    if i not in cnf:
        cnf["/usr/static/"+i]= {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': config['serve-static'][i],
        "tools.sessions.on": False,
        'tools.caching.on' : True,
        'tools.caching.delay' : 3600,
        "tools.addheader.on": True
        }    

def addheader(*args,**kwargs):
    "This function's only purpose is to tell the browser to cache requests for an hour"
    cherrypy.response.headers['Cache-Control'] = "max-age=3600"
    #del cherrypy.response.headers['Expires']
    
def pageloadnotify(*args,**kwargs):
    systasks.aPageJustLoaded()
cherrypy.config.update(site_config)    
cherrypy.tools.pageloadnotify = cherrypy.Tool('on_start_resource', pageloadnotify)
cherrypy.config['tools.pageloadnotify.on'] = True

cherrypy.tools.addheader = cherrypy.Tool('before_finalize', addheader)

if hasattr(cherrypy.engine, 'signal_handler'):
    cherrypy.engine.signal_handler.subscribe()

cherrypy.tree.mount(root,config=cnf)


#As far as I can tell, this second server inherits everything from the "implicit" server
#except what we override.
server2 = cherrypy._cpserver.Server()
server2.socket_port= config['http-port']
server2._socket_host= bindto
server2.thread_pool=config['http-thread-pool']
server2.subscribe()


messagebus.postMessage('/system/startup','System Initialized')
messagebus.postMessage('/system/notifications','System Initialized')

cherrypy.engine.start()
cherrypy.engine.block()