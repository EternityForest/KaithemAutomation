#!/usr/bin/python3
#Copyright Daniel Dunn 2013-2015
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

#
__version__ = "0.55 Develpoment"
__version_info__ = (0,5,5,"dev",0)

#Library that makes threading and lock operations, which we use a lot of, use native code on linux
try:
    import pthreading
    pthreading.monkey_patch()
except:
    pass

#This file is the main entry point of the app. It imports everything, loads configuration,
#sets up and starts the server, and contains page handlers for the main page.


import sys,os,threading,traceback

#There are some libraries that are actually different for 3 and 2, so we use the appropriate one
#By changing the pathe to include the proper ones.

#Also, when we install on linux, everything gets moved around, so we change the paths accordingly.
x = sys.path[0]
linuxpackage = False
#This is ow we detect if we are running in "unzip+run mode" or installed on linux.
#If we are installed, then src is found in /usr/lib/kaithem

if x.startswith('/usr/bin'):
    x = "/usr/lib/kaithem"
    linuxpackage = True
    sys.path = [x] + sys.path

x = os.path.join(x,'src')

if sys.version_info < (3,0):
    sys.path = [os.path.join(x,'thirdparty','python2')] + sys.path
    from gzip import open as opengzip
    import thread
else:
    from gzip import GzipFile as opengzip
    import _thread as thread
    sys.path = [os.path.join(x,'thirdparty','python3')] + sys.path

#There is actually a very good reason to change the import path here.
#It means we can refer to an installed copy of a library by the same name
#We use for the copy we include. Normally we use our version.
#If not, it will fall back to theirs.
sys.path = [os.path.join(x,'thirdparty')] + sys.path

#Low priority modules will default to using the version installed on the user's computer.
sys.path =  sys.path + [os.path.join(x,'thirdparty',"lowpriority")]

if sys.version_info < (3,0):
    sys.path = sys.path+[os.path.join(x,'thirdparty','lowpriority','python2')]
else:
    sys.path = sys.path+[os.path.join(x,'thirdparty','lowpriority','python3')]


import time,signal
import cherrypy,validictory
from cherrypy import _cperror
from src import util
from src import messagebus


def installThreadExcepthook():
    """
    Workaround for sys.excepthook thread bug
    From
    http://spyced.blogspot.com/2007/06/workaround-for-sysexcepthook-bug.html
    (https://sourceforge.net/tracker/?func=detail&atid=105470&aid=1230540&group_id=5470).
    Call once from __main__ before creating any threads.
    If using psyco, call psyco.cannotcompile(threading.Thread.run)
    since this replaces a new-style class method.

    Modified by kaithem project to do something slightly different. Credit to Ian Beaver.
    What our version does is posts to the message bus when a thread starts, stops, or has an exception.
    """
    init_old = threading.Thread.__init__
    def init(self, *args, **kwargs):
        init_old(self, *args, **kwargs)
        run_old = self.run
        def run_with_except_hook(*args, **kw):
            try:
                messagebus.postMessage("/system/threads/start",self.name)
                run_old(*args, **kw)
                messagebus.postMessage("/system/threads/stop",self.name)
            except Exception as e:
                messagebus.postMessage("/system/notifications/errors","Exception in thread %s, thread stopped. More details in logs."%self.name)
                messagebus.postMessage("/system/threads/errors","Exception in thread %s:\n%s"%(self.name, traceback.format_exc(6)))
                raise e
        #Rename thread so debugging works
        try:
            if self._target:
                run_with_except_hook.__name__ = self._target.__name__
                run_with_except_hook.__module__ =self._target.__module__
        except:
            try:
                run_with_except_hook.__name__ = "run"
            except:
                pass
        self.run = run_with_except_hook
    threading.Thread.__init__ = init

installThreadExcepthook()

from src import notifications
from src import pages
from src import weblogin
from src import auth
from src import config as cfg
from src import directories
#Initialize the authorization module
auth.initializeAuthentication()
if cfg.argcmd.initialpackagesetup:
    util.drop_perms(cfg.config['run-as-user'], cfg.config['run-as-group'])
    auth.dumpDatabase()
    print("Kaithem users set up. Now exiting(May take a few seconds. You may start the service manually or via systemd/init")
    cherrypy.engine.exit()
    sys.exit()

from src import ManageUsers
from src import newevt
from src import modules
from src import modules_interface
from src import settings
from src import usrpages
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
thread.stack_size(256000)

if config['change-process-title']:
    try:
        import setproctitle
        setproctitle.setproctitle("kaithem")
    except:
        pass

if config['enable-websockets']:
    from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
    from ws4py.websocket import EchoWebSocket
    WebSocketPlugin(cherrypy.engine).subscribe()
    cherrypy.tools.websocket = WebSocketTool()





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
        cherrypy.response.status = 400
        return pages.get_template('errors/alreadyexists.html').render()

    @cherrypy.expose
    def gosecure(self,):
        cherrypy.response.status = 426
        return pages.get_template('errors/gosecure.html').render()

    @cherrypy.expose
    def loginerror(self,):
        cherrypy.response.status = 400
        return pages.get_template('errors/loginerror.html').render()

    @cherrypy.expose
    def nofoldermoveerror(self,):
        cherrypy.response.status = 400
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
root.modules = modules_interface.WebInterface()
root.settings = settings.Settings()
root.errors = Errors()
root.pages = usrpages.KaithemPage()
root.logs = messagelogging.WebInterface()
root.notifications = notifications.WI()
root.widgets = widgets.WebInterface()


if not linuxpackage:
    sdn = os.path.join(os.path.dirname(os.path.realpath(__file__)),"src")
    ddn = os.path.join(os.path.dirname(os.path.realpath(__file__)),"data")
else:
    sdn = "/usr/lib/kaithem/src"
    ddn = "/usr/share/kaithem"

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
        'tools.staticdir.dir':os.path.join(ddn,'static'),
        "tools.sessions.on": False,
        "tools.addheader.on": True,
        'tools.expires.on'    : True,
        'tools.expires.secs'  : 3600# expire in an hour
        },

    '/static/js':
        {'tools.staticdir.on': True,
        'tools.staticdir.dir':os.path.join(sdn,'js'),
        "tools.sessions.on": False,
        "tools.addheader.on": True
        },

    '/static/css':
        {'tools.staticdir.on': True,
        'tools.staticdir.dir':os.path.join(sdn,'css'),
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




if time.time() < 1420070400:
    messagebus.postMessage('/system/notifications/errors',"System Clock is wrong, some features may not work properly.")

if time.time() < util.min_time:
        messagebus.postMessage('/system/notifications/errors',"System Clock may be wrong, or time has been set backwards at some point. If system clock is correct and this error does not go away, you can fix it manually be correcting folder name timestamps in the var dir.")

sys.modules['kaithem'] = sys.modules['__main__']
from src import kaithemobj
kaithemobj.kaithem.misc.version      = __version__
kaithemobj.kaithem.misc.version_info = __version_info__
cherrypy.engine.start()
#If configured that way on unix, check if we are root and drop root.
util.drop_perms(config['run-as-user'], config['run-as-group'])
messagebus.postMessage('/system/startup','System Initialized')
messagebus.postMessage('/system/notifications/important','System Initialized')
cherrypy.engine.block()
cherrypy.engine.exit()
time.sleep(1)
cherrypy.engine.exit()
print("Cherrypy engine stopped")

#Partial workaround for a bug where it won't exit in python3. This probably won't work on windows
if sys.version_info > (3,0):
    #Wait until all non daemon threads are finished shutting down.
    while 1:
        exit = True
        for i in sorted(threading.enumerate(),key=lambda d:d.name):
            if (not i.daemon) and (not(i.name=="MainThread")):
                exit=False
        if exit:
            break

    #If still not stopped, try to stop
    try:
        #Try the most graceful way first.
        print("Still running, sending signals")
        os.kill(os.getpid(), signal.SIGINT)
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(1)
        os.kill(os.getpid(), signal.SIGKILL)

    except:
        raise
