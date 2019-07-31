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

__version__ = "0.63.1 Production"
__version_info__ = (0,63,1,"release",0)

#Library that makes threading and lock operations, which we use a lot of, use native code on linux
try:
    import pthreading
    pthreading.monkey_patch()
except:
    pass

#Dump stuff to stderr when we get a segfault
try:
    import faulthandler
    faulthandler.enable()
except:
    pass



#This file is the main entry point of the app. It imports everything, loads configuration,
#sets up and starts the server, and contains page handlers for the main page.



import sys,os,threading,traceback,logging,time,mimetypes

logger = logging.getLogger("system")
logger.setLevel(0)

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

#Avoid having to rename six.py by treating it's folder as a special case.
sys.path = [os.path.join(x,'thirdparty','six')] + sys.path

sys.path = [os.path.join(x,'plugins','ondemand')] + sys.path
sys.path = [os.path.join(x,'plugins','startup')] + sys.path

startupPluginsPath = os.path.join(x,'plugins','startup')

sys.path = sys.path+ [os.path.join(x,'plugins','lowpriority')]


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

import src

import time,signal
import cherrypy,validictory

#We don't want Cherrypy writing temp files for no reason
cherrypy._cpreqbody.Part.maxrambytes = 64*1024

from cherrypy import _cperror
from src import util

from src import config as cfg

logging.getLogger("cherrypy.access").propagate = False


#WE have to get the workers set up early because a lot of things depend on it.
from src import workers
def handleError(f,exc):
        from src import messagebus
        try:
            messagebus.postMessage('system/errors/workers',
                                        {"function":f.__name__,
                                        "module":f.__module__,
                                        "traceback":traceback.format_exception(*exc, limit=6)})

        except:
            messagebus.postMessage('system/errors/workers',{
                                "traceback":traceback.format_exception(*exc, limit=s6)})

workers.handleError = handleError

#Attempt to make pavillion work in a sane way that takes advantage of the thread pooling
try:
    import pavillion
    pavillion.daemon = True
    pavillion.execute = workers.do
except:
    pass

#We want a notification anytime every first error in a scheduled event
from src import scheduling
def handleFirstError(f):
    "Callback to deal with the first error from any given event"
    m = f.__module__
    messagebus.postMessage("/system/notifications/errors",
    "Problem in scheduled event function: "+repr(f)+" in module: "+ m
            +", check logs for more info.")
scheduling.handleFirstError = handleFirstError

qsize = cfg.config['task-queue-size']
count = cfg.config['worker-threads']
wait =  cfg.config['wait-for-workers']
workers.start(count,qsize,wait)

from src import messagebus
from src import messagelogging
from src import notifications

from src import pylogginghandler
from src import logviewer


threadlogger = logging.getLogger("system.threading")

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
                threadlogger.info("Thread starting: "+self.name)
                messagebus.postMessage("/system/threads/start",self.name)
                run_old(*args, **kw)
                threadlogger.info("Thread stopping: "+self.name)
                messagebus.postMessage("/system/threads/stop",self.name)
            except Exception as e:
                threadlogger.exception("Thread stopping due to exception: "+self.name)
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




try:
    from src import timesync
except:
    logger.exception("Could not start time sync module")
    messagebus.postMessage('/system/notifications/errors',
    """Failed to initialize the time sync module or zeroconf discovery
    This may be because you are using a python version older than 3.3, or because
    netifaces is not installed. Some features may not work correctly.
    """)


from src import pages
from src import weblogin
from src import auth
from src import directories
from src import pages


#Initialize the authorization module
auth.initializeAuthentication()
logger.info("Loaded auth data")

if cfg.argcmd.initialpackagesetup:
    util.drop_perms(cfg.config['run-as-user'], cfg.config['run-as-group'])
    auth.dumpDatabase()
    logger.info("Kaithem users set up. Now exiting(May take a few seconds. You may start the service manually or via systemd/init")
    cherrypy.engine.exit()
    sys.exit()

from src import ManageUsers
from src import statemachines
from src import newevt
from src import registry
from src import modules
from src import modules_interface
from src import settings
from src import usrpages
from src import systasks
from src import widgets

from src import alerts
logger.info("Loaded core python code")
from src.config import config
import src.config as cfgmodule
if not config['host'] == 'default':    
    bindto = config['host']
else:
    if config['local-access-only']:
        bindto = '127.0.0.1'
    else:
        bindto = '::'

#limit nosecurity to localhost
if cfgmodule.argcmd.nosecurity == 1:
    bindto = '127.0.0.1'

#cherrypy.process.servers.check_port(bindto, config['http-port'], timeout=1.0)
#cherrypy.process.servers.check_port(bindto, config['https-port'], timeout=1.0)
logger.info("Ports are free")

MyExternalIPAdress = util.updateIP()

if config['change-process-title']:
    try:
        import setproctitle
        setproctitle.setproctitle("kaithem")
        logger.info("setting process title")
    except:
        logger.warning("error setting process title")

if config['enable-websockets']:
    from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
    from ws4py.websocket import EchoWebSocket, WebSocket
    WebSocketPlugin(cherrypy.engine).subscribe()
    cherrypy.tools.websocket = WebSocketTool()
    logger.info("activated websockets")


sys.modules['kaithem'] = sys.modules['__main__']
from src import kaithemobj
kaithemobj.kaithem.states.StateMachine = statemachines.StateMachine
kaithemobj.kaithem.misc.version      = __version__
kaithemobj.kaithem.misc.version_info = __version_info__

#Load all modules from the active modules directory
modules.initModules()
logger.info("Loaded modules")

import mimetypes

import collections

#Super simple hacky cache. Maybe we should
#Just mostly eliminate zips and use files directly?
zipcache = collections.OrderedDict()

#This class represents the "/" root of the web app
class webapproot():
    #"/" is mapped to this
    @cherrypy.expose
    def index(self,*path,**data):
        pages.require("/admin/mainpage.view")
        cherrypy.response.cookie['LastSawMainPage'] = time.time()
        return pages.get_template('index.html').render()
    
    #"/" is mapped to this
    @cherrypy.expose
    def tagpoints(self,*path,**data):
        pages.require("/admin/settings.view")
        return pages.get_template('settings/tagpoints.html').render()


    @cherrypy.expose
    def zipstatic(self,*path,**data):
        """
        take everything but the last path element, use it as a path relative to static dir
        open as a zip, use the last as filename in the zip, return it.
        """
        if ".." in path:
            return
        try:
            if path in zipcache:
                zipcache.move_to_end(path)
                return zipcache[path]
        except:
            print("err in cache for zip")
        cherrypy.response.headers['Cache-Control'] = "max-age=28800"

        m =mimetypes.guess_type(path[-1])
        cherrypy.response.headers['Content-Type'] = m[0]
        p = os.path.join(ddn,'static',*path[:-1])
        with zipfile.ZipFile(p) as f:
            d = f.read(path[-1])
        zipcache[path]=d
        if len(zipcache)> 64:
            zipcache.pop(last=False)
        return d

    @cherrypy.expose
    def pagelisting(self,*path,**data):
        #Pagelisting knows to only show pages if you have permissions
        return pages.get_template('pagelisting.html').render_unicode(modules = modules.ActiveModules)

    #docs, helpmenu, and license are just static pages.
    @cherrypy.expose
    def docs(self,*path,**data):
        if path:
            if path[0]=="thirdparty":
                p = os.path.normpath(os.path.join(directories.srcdir,"docs","/".join(path)))
                if not p.startswith(os.path.join(directories.srcdir,"docs")):
                    raise RuntimeError("Invalid URL")
                cherrypy.response.headers['Content-Type']= mimetypes.guess_type(p)[0]

                with open(p,"rb") as f:
                    return(f.read())
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


import zipfile


from src import remotedevices

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
root.syslog = logviewer.WebInterface()
root.devices = remotedevices.WebDevices()

if not linuxpackage:
    sdn = os.path.join(os.path.dirname(os.path.realpath(__file__)),"src")
    ddn = os.path.join(os.path.dirname(os.path.realpath(__file__)),"data")
else:
    sdn = "/usr/lib/kaithem/src"
    ddn = "/usr/share/kaithem"

def allow_upload(*args,**kwargs):
    #Only do the callback if needed. Assume it's really big if no header.
    if int(cherrypy.request.headers.get("Content-Length",2**32))> cherrypy.request.body.maxbytes:
        cherrypy.request.body.maxbytes = cherrypy.request.config['tools.allow_upload.f']()

cherrypy.tools.allow_upload = cherrypy.Tool('before_request_body', allow_upload)

site_config={
        "request.body.maxbytes": 64*1024,
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
        'tools.allow_upload.on':True,
        'tools.allow_upload.f': lambda: auth.getUserLimit(pages.getAcessingUser(),"web.maxbytes") or 64*1024,
}

if config['enable-websockets']:
    wscfg={'tools.websocket.on': True,
            'tools.websocket.handler_cls': widgets.websocket}

    wscfg2={'tools.websocket.on': True,
            'tools.websocket.handler_cls':notifications.websocket}
else:
    wscfg = {}
    wscfg2 = {}

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

        '/static/docs':
        {'tools.staticdir.on': True,
        'tools.staticdir.dir':os.path.join(sdn,'docs'),
        "tools.sessions.on": False,
        "tools.addheader.on": True
        },
    '/static/zip':
        {
        'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
        "tools.addheader.on": True

        },
    '/pages':
        {
        'tools.allow_upload.on':True,
        'tools.allow_upload.f': lambda: auth.getUserLimit(pages.getAcessingUser(),"web.maxbytes") or 64*1024,
        'request.dispatch': cherrypy.dispatch.MethodDispatcher()
        },

    '/widgets/ws': wscfg,
    '/notifications/ws':wscfg2
}

if not config['favicon-png']=="default":
    cnf['/favicon.png']={
    'tools.staticfile.on' : True,
    'tools.staticfile.filename' : os.path.join(directories.datadir,"static",config['favicon-png']),
    'tools.expires.on'    : True,
    'tools.expires.secs'  : 3600# expire in an hour
    }

if not config['favicon-ico']=="default":
    cnf['/favicon.ico']={
    'tools.staticfile.on' : True,
    'tools.staticfile.filename' : os.path.join(directories.datadir,"static",config['favicon-ico']),
    'tools.expires.on'    : True,
    'tools.expires.secs'  : 3600# expire in an hour
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
    cherrypy.response.headers['Cache-Control'] = "max-age=28800"
    #del cherrypy.response.headers['Expires']

def pageloadnotify(*args,**kwargs):
    systasks.aPageJustLoaded()


#As far as I can tell, this second server inherits everything from the "implicit" server
#except what we override.
server2 = cherrypy._cpserver.Server()
server2.socket_port= config['http-port']
server2._socket_host= bindto
server2.thread_pool=config['http-thread-pool']
server2.subscribe()



cherrypy.config.update(site_config)
cherrypy.tools.pageloadnotify = cherrypy.Tool('on_start_resource', pageloadnotify)
cherrypy.config['tools.pageloadnotify.on'] = True

cherrypy.tools.addheader = cherrypy.Tool('before_finalize', addheader)

if hasattr(cherrypy.engine, 'signal_handler'):
    cherrypy.engine.signal_handler.subscribe()

cherrypy.tree.mount(root,config=cnf)




if time.time() < 1420070400:
    messagebus.postMessage('/system/notifications/errors',"System Clock is wrong, some features may not work properly.")

if time.time() < util.min_time:
        messagebus.postMessage('/system/notifications/errors',"System Clock may be wrong, or time has been set backwards at some point. If system clock is correct and this error does not go away, you can fix it manually be correcting folder name timestamps in the var dir.")


cherrypy.engine.start()
#If configured that way on unix, check if we are root and drop root.
util.drop_perms(config['run-as-user'], config['run-as-group'])
messagebus.postMessage('/system/startup','System Initialized')
messagebus.postMessage('/system/notifications/important','System Initialized')

import importlib
plugins = {}
try:
    for i in os.listdir(startupPluginsPath):
        try:
            plugins[i] = importlib.import_module(i)
        except:
            logger.exception("Error loading plugin "+i)
            messagebus.postMessage('/system/notifications/errors',"Error loading plugin "+i)
except:
    messagebus.postMessage('/system/notifications/errors',"Error loading plugins")



r = util.zeroconf

import zeroconf
#Register an NTP service
desc = {}

if cfg.config['advertise-webui']:
    try:
        import socket
        if not cfg.config['webui-servicename']=="default":
            localserver_name = cfg.config['webui-servicename']
        else:
            localserver_name = "kaithem_"+socket.gethostname()

        info = zeroconf.ServiceInfo("_http._tcp.local.",
                localserver_name+"._http._tcp.local.",
                [None], cfg.config['http-port'], 0, 0, desc)
        r.register_service(info)
        info2 = zeroconf.ServiceInfo("_https._tcp.local.",
                localserver_name+"._https._tcp.local.",
                [None], cfg.config['https-port'], 0, 0, desc)
        r.register_service(info2)
    except:
        logger.exception("Error advertising MDNS service")

#Open a port to the outside world. Note that this can only be enabled through the webUI,
#You are safe unless someone turns it on..
systasks.doUPnP()
cherrypy.engine.block()

#Old workaround for things not stopping on python3 that no longer appears to be needed.
# cherrypy.engine.exit()
# time.sleep(1)
# cherrypy.engine.exit()
logger.info("Cherrypy engine stopped")
#
# #Partial workaround for a bug where it won't exit in python3. This probably won't work on windows
# if sys.version_info > (3,0):
#     #Wait until all non daemon threads are finished shutting down.
#     while 1:
#         exit = True
#         for i in sorted(threading.enumerate(),key=lambda d:d.name):
#             if (not i.daemon) and (not(i.name=="MainThread")):
#                 exit=False
#         if exit:
#             break

    #
    # #If still not stopped, try to stop
    # try:
    #     #Try the most graceful way first.
    #     for i in threading.enumerate():
    #         print("Waiting on thread: "+str(i))
    #     print("Still running, sending signals")
    #     os.kill(os.getpid(), signal.SIGINT)
    #     time.sleep(0.5)
    #     os.kill(os.getpid(), signal.SIGTERM)
    #     time.sleep(1)
    #     os.kill(os.getpid(), signal.SIGKILL)
    #
    # except:
    #     raise
