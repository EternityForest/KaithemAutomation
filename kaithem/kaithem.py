#!/usr/bin/python3
#Copyright Daniel Dunn 2013
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

#There are some libraries that are actually different for 3 and 2, so we use the appropriate one
#By changing the pathe to include the proper ones.
x = sys.path[0]
if sys.version_info < (3,0):
    sys.path = [os.path.join(x,'src','thirdparty','python2')] + sys.path
    from gzip import open as opengzip
    import thread
else:
    from gzip import GzipFile as opengzip
    import _thread as thread
    sys.path = [os.path.join(x,'src','thirdparty','python3')] + sys.path

#There is actually a very good reason to change the import path here.
#It means we can refer to an installed copy of a library by the same name
#We use for the copy we include. Normally we use our version.
#If not, it will fall back to theirs.
sys.path = [os.path.join(x,'src','thirdparty')] + sys.path

#Low priority modules will default to using the version installed on the user's computer.
sys.path =  sys.path + [os.path.join(x,'src','thirdparty',"lowpriority")]

if sys.version_info < (3,0):
    sys.path = sys.path+[os.path.join(x,'src','thirdparty','lowpriority','python2')]
else:
    sys.path = sys.path+[os.path.join(x,'src','thirdparty','lowpriority','python3')]


import time,signal
import cherrypy,validictory
from cherrypy import _cperror
from src import util
from src import pages
from src import weblogin
from src import auth
from src import ManageUsers
from src import directories
from src import newevt
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

if config['local-access-only']:
    bindto = '127.0.0.1'
else:
    bindto = '0.0.0.0'

cherrypy.process.servers.check_port(bindto, config['http-port'], timeout=1.0)
cherrypy.process.servers.check_port(bindto, config['https-port'], timeout=1.0)


MyExternalIPAdress = util.updateIP()
thread.stack_size(64000)


if config['enable-websockets']:
    from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
    from ws4py.websocket import EchoWebSocket
    WebSocketPlugin(cherrypy.engine).subscribe()
    cherrypy.tools.websocket = WebSocketTool()



#Initialize the authorization module
auth.initializeAuthentication()

#Load all modules from the active modules directory
modules.initModules()

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
        return pages.get_template('pagelisting.html').render_unicode(modules = modules.ActiveModules)

    #docs,about,helpmenu, and license are just static pages
    @cherrypy.expose
    def docs(self,*path,**data):
        if path:
            return pages.get_template('help/'+path[0]+'.html').render()
        return pages.get_template('help/help.html').render()

    @cherrypy.expose
    def makohelp(self,*path,**data):
        return pages.get_template('help/makoreference.html').render()

    @cherrypy.expose
    def about(self,*path,**data):
        return pages.get_template('help/about.html').render(myip = MyExternalIPAdress)
    @cherrypy.expose
    def changelog(self,*path,**data):
        return pages.get_template('help/changes.html').render(myip = MyExternalIPAdress)
    @cherrypy.expose
    def helpmenu(self,*path,**data):
        return pages.get_template('help/index.html').render()
    @cherrypy.expose
    def license(self,*path,**data):
        return pages.get_template('help/license.html').render()

class Errors():
    @cherrypy.expose
    def permissionerror(self,):
        cherrypy.response.status = 403
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
    def nofoldermoveerror(self,):
        return pages.get_template('errors/nofoldermove.html').render()
    @cherrypy.expose
    def wrongmethod(self,):
        cherrypy.response.status = 405
        return pages.get_template('errors/wrongmethod.html').render()
    @cherrypy.expose
    def error(self,):
        cherrypy.response.status = 500
        return pages.get_template('errors/error.html').render(info="An Error Occurred")


def cpexception():
    cherrypy.response.status = 500
    if sys.version_info < (3,0):
        cherrypy.response.body= bytes(pages.get_template('errors/cperror.html').render(e=_cperror.format_exc()))
    else:
        cherrypy.response.body= bytes(pages.get_template('errors/cperror.html').render(e=_cperror.format_exc()),'utf8')




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



dn = os.path.dirname(os.path.realpath(__file__))



site_config={
        "tools.encode.on" :True,
        "tools.encode.encoding":'utf-8',
        "tools.decode.on": True,
        "tools.decode.encoding": 'utf-8',
        'request.error_response': cpexception,
        'log.screen': config['cherrypy-log-stdout'],
        'server.socket_host': bindto,
        'server.socket_port': config['https-port'],
        'server.ssl_module':'builtin',
        'server.ssl_certificate':os.path.join(directories.ssldir,'certificate.cert'),
        'server.ssl_private_key':os.path.join(directories.ssldir,'certificate.key'),
        'server.thread_pool':config['https-thread-pool'],
        'engine.autoreload.frequency' : 5,

}
if config['enable-websockets']:
    wscfg={'tools.websocket.on': True,
           'tools.websocket.handler_cls': widgets.websocket}
else:
    wscfg = {}

cnf={
    '/static':
        {'tools.staticdir.on': True,
        'tools.staticdir.dir':os.path.join(dn,'data/static'),
        "tools.sessions.on": False,
        "tools.addheader.on": True
        },

    '/static/js':
        {'tools.staticdir.on': True,
        'tools.staticdir.dir':os.path.join(dn,'src/js'),
        "tools.sessions.on": False,
        "tools.addheader.on": True
        },

    '/static/css':
        {'tools.staticdir.on': True,
        'tools.staticdir.dir':os.path.join(dn,'src/css'),
        "tools.sessions.on": False,
        "tools.addheader.on": True
        },

     '/pages':
        {
         'request.dispatch': cherrypy.dispatch.MethodDispatcher()
        },

    '/widgets/ws': wscfg
}
#Let the user create additional static directories
for i in config['serve-static']:
    if i not in cnf:
        cnf["/usr/static/"+i]= {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': config['serve-static'][i],
        "tools.sessions.on": False,
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
messagebus.postMessage('/system/notifications/important','System Initialized')

if time.time() < 1420070400:
    messagebus.postMessage('/system/notifications/errors',"System Clock is wrong, some features may not work properly.")

if time.time() < util.min_time:
        messagebus.postMessage('/system/notifications/errors',"System Clock may be wrong, or time has been set backwards at some point. If system clock is correct and this error does not go away, you can fix it manually be correcting folder name timestamps in the var dir.")



cherrypy.engine.start()
cherrypy.engine.block()
