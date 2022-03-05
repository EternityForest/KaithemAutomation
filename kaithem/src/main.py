

#!/usr/bin/python3
# Copyright Daniel Dunn 2013-2015
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

#



import os
import sys

from . import pathsetup

# Minimal path setup, to be able to even find the rest
x = os.path.abspath(__file__)
# This is ow we detect if we are running in "unzip+run mode" or installed on linux.
# If we are installed, then src is found in /usr/lib/kaithem
if x.startswith('/usr/bin'):
    x = "/usr/lib/kaithem"
    sys.path = [x] + sys.path


# Enable importing stuff directly from ./thirdparty,
# Since we include lots of dependancies that would normally be provided by the system.
# This must be done before CherryPy
pathsetup.setupPath(linuxpackage=os.path.abspath(
    __file__).startswith("/usr/bin"))


# Enable Cython JIT imports, needed by a few optional features.
# Pyximport may become required in the future.
pathsetup.setupCython()

from . import tweaks

# Enable logging when threads start and stop.
tweaks.installThreadLogging()

# Thhese happpen early so we cab start logging stuff soon
from . import messagelogging
from . import pylogginghandler
from . import notifications


import getpass
import atexit
import signal
import mimetypes
import time
import traceback
import sys
from . import util, workers
from . import selftest
from . import devices
import importlib
from scullery import messagebus
from . import statemachines
from . import auth
from . import directories

from .config import config
from . import config as cfg
import mako.exceptions
import cherrypy
import logging

from . import version_info
__version__ = version_info.__version__
__version_info__ = version_info.__version_info__

from .import tagpoints
from src import kaithemobj
from . import wifimanager




# Library that makes threading and lock operations, which we use a lot of, use native code on linux
try:
    import pthreading
    pthreading.monkey_patch()
except Exception:
    pass


logger = logging.getLogger("system")
logger.setLevel(0)

# Dump stuff to stderr when we get a segfault
try:
    import faulthandler
    faulthandler.enable()
except Exception:
    logger.exception(
        "Faulthandler not fount. Segfault error messages disabled. use pip3 install faulthandler to fix")


# This file is the main entry point of the app. It imports everything, loads configuration,
# sets up and starts the server, and contains page handlers for the main page.


# Make this not spew debug logs, I'm pretty sure that lib is well tested and
# Reliable and we don't need to know about every request.
urlliblogger = logging.getLogger("urllib3.connectionpool")
urlliblogger.setLevel(logging.INFO)


# This is a very slightly modified version with better socket cleanup properties


# Initialize the authorization module
auth.initializeAuthentication()
logger.info("Loaded auth data")

if cfg.argcmd.initialpackagesetup:
    util.drop_perms(config['run-as-user'], config['run-as-group'])
    auth.dumpDatabase()
    logger.info(
        "Kaithem users set up. Now exiting(May take a few seconds. You may start the service manually or via systemd/init")
    cherrypy.engine.exit()
    sys.exit()


plugins = {}
try:
    for i in os.listdir(pathsetup.startupPluginsPath):
        try:
            plugins[i] = importlib.import_module(i)
            logger.info("Loaded plugin " + i)
        except Exception:
            logger.exception("Error loading plugin " + i)
            messagebus.postMessage('/system/notifications/errors',
                                   "Error loading plugin " + i + "\n" + traceback.format_exc())
except Exception:
    messagebus.postMessage('/system/notifications/errors',
                           "Error loading plugins")
    logger.exception("Error loading plugins")


#Making drayer a standard, always-available part of Kaithem.
#This doesn't mean we actually do anything with it, we don't expose
#the service to the world till requested.
try:
    from . import drayer
    drayer.loadDrayerSetup()
except:
    logger.exception("Error loading DrayerDB Local Node")

devices.init_devices()


def dumpThreads(*a):
    from . import pages
    try:
        n = "/dev/shm/kaithemExitThreadsDump." + str(time.time()) + ".html"
        with open(n, 'w') as f:
            f.write(pages.get_template("settings/threads.html").render())
        os.chmod(n, 0o600)
    except Exception:
        print(traceback.format_exc())


def sigquit(*a):
    from . import pages

    try:
        n = "/dev/shm/kaithemExitThreadsDump." + str(time.time()) + ".html"
        with open(n, 'w') as f:
            f.write(pages.get_template("settings/threads.html").render())
        os.chmod(n, 0o600)

    except Exception:
        raise
    cherrypy.bus.exit()


signal.signal(signal.SIGQUIT, sigquit)
signal.signal(signal.SIGUSR1, dumpThreads)



#Enable the auto MIDI tagpoint/message bus features.
from src import rtmidimanager

def nop():
    pass
#from . import wifimanager


def webRoot():
    # We don't want Cherrypy writing temp files for no reason
    cherrypy._cpreqbody.Part.maxrambytes = 64 * 1024

    from cherrypy import _cperror

    logging.getLogger("cherrypy.access").propagate = False

    from . import tagpoints
    from . import builtintags

    def tagErrorHandler(tag, f, val):
        try:
            from . import newevt
            if f.__module__ in newevt.eventsByModuleName:
                newevt.eventsByModuleName[f.__module__]._handle_exception()
            else:
                if not hasattr(f, "_kaithemFirstErrorMarker"):
                    f._kaithemFirstErrorMarker = True
                    messagebus.postMessage("/system/notifications/errors", "First err in tag subscriber " + str(
                        f) + " from " + str(f.__module__) + " to " + tag.name)
        except:
            print(traceback.format_exc(chain=True))

    tagpoints.subscriberErrorHandlers = [tagErrorHandler]

    tagpoints.loadAllConfiguredTags(os.path.join(directories.vardir, "tags"))

    # We want a notification anytime every first error in a scheduled event.
    # This can stay even with real python logging, we want the front page notificaton.
    from . import scheduling

    def handleFirstError(f):
        "Callback to deal with the first error from any given event"
        m = f.__module__
        messagebus.postMessage("/system/notifications/errors",
                               "Problem in scheduled event function: " +
                               repr(f) + " in module: " + m
                               + ", check logs for more info.")
    scheduling.handleFirstError = handleFirstError

    from . import logviewer

    try:
        from . import timesync
    except:
        logger.exception("Could not start time sync module")
        messagebus.postMessage('/system/notifications/errors',
                               """Failed to initialize the time sync module or zeroconf discovery
        This may be because you are using a python version older than 3.3, or because
        netifaces is not installed. Some features may not work correctly.
        """)

    from . import pages
    from . import weblogin
    from . import pages

    from . import ManageUsers
    from . import newevt
    from . import registry
    from . import modules
    from . import modules_interface
    from . import settings
    from . import usrpages
    from . import systasks
    from . import widgets

    from . import alerts
    logger.info("Loaded core python code")
    from . import config as cfgmodule
    if not config['host'] == 'default':
        bindto = config['host']
    else:
        if config['local-access-only']:
            bindto = '127.0.0.1'
        else:
            bindto = '::'

    mode = int(
        cfgmodule.argcmd.nosecurity) if cfgmodule.argcmd.nosecurity else None
    # limit nosecurity to localhost
    if mode == 1:
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

    from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
    from ws4py.websocket import EchoWebSocket, WebSocket
    WebSocketPlugin(cherrypy.engine).subscribe()
    cherrypy.tools.websocket = WebSocketTool()
    logger.info("activated websockets")

    sys.modules['kaithem'] = sys.modules['__main__']

    # Load all modules from the active modules directory
    modules.initModules()
    logger.info("Loaded modules")

    def save():
        if config['save-before-shutdown']:
            messagebus.postMessage(
                '/system/notifications/important/', "System saving before shutting down")
            util.SaveAllState()

    # let the user choose to have the server save everything before a shutdown
    if config['save-before-shutdown']:
        atexit.register(save)
        cherrypy.engine.subscribe("exit", save)

    import collections

    # Super simple hacky cache. Maybe we should
    # Just mostly eliminate zips and use files directly?
    zipcache = collections.OrderedDict()

    # This class represents the "/" root of the web app
    class webapproot():

        # This lets users mount stuff at arbitrary points, so long
        # As it doesn't conflict with anything.

        # foo.bar.com/foo maps to foo,bar,/,foo
        # bar.com/foo is just foo
        def _cp_dispatch(self, vpath):

            sdpath = pages.getSubdomain()

            vpath2 = vpath[:]

            # For binding the root of subdomains

            while vpath2:
                # Check for any subdomain specific handling.
                if tuple(sdpath + ['/'] + vpath2) in pages.nativeHandlers:
                    # found match, remove N elements from the beginning of the path,
                    # where n is the length of the "mountpoint", becsause the mountpoint
                    # already consumed those.

                    # Don't do it for the fake one we add just to make this loop work though
                    for i in vpath2:
                        vpath.pop(0)

                    x = pages.nativeHandlers[tuple(sdpath + ['/'] + vpath2)]

                    # Traverse to the actual function, if there is a match, else return the index.

                    if vpath and hasattr(x, vpath[0]):
                        x2 = getattr(x, vpath[0])
                        if hasattr(x2, 'exposed') and x2.exposed:
                            vpath.pop(0)
                            x = x2
                    if not isinstance(x, Exception):
                        return x
                    else:
                        raise x

                if tuple(vpath2) in pages.nativeHandlers:
                    # found match, remove N elements from the beginning of the path,
                    # where n is the length of the "mountpoint", because the mountpoint
                    # already consumed those
                    for i in range(len(vpath2)):
                        vpath.pop(0)

                    x = pages.nativeHandlers[tuple(vpath2)]
                    if vpath and hasattr(x, vpath[0]):
                        x2 = getattr(x, vpath[0])
                        if vpath and hasattr(x2, 'exposed') and x2.exposed:
                            vpath.pop(0)
                            x = x2
                    if not isinstance(x, Exception):
                        return x
                    else:
                        raise x

                if None in pages.nativeHandlers:
                    return pages.nativeHandlers[None]

                # Successively remove things from the end till we get a
                # prefix match
                vpath2.pop(-1)

            return None

        @cherrypy.expose
        def default(self, *path, **data):
            return self._cp_dispatch(list(path))(*path, **data)

        # Keep the dispatcher from freaking out. The actual handling
        # Is done by a cherrypy tool. These just keeo cp_dispatch from being called
        # I have NO clue why the favicon doesn't have this issue.
        @cherrypy.expose
        def static(self, *path, **data):
            pass

        @cherrypy.expose
        def usr(self, *path, **data):
            pass

        @cherrypy.expose
        def index(self, *path, **data):
            pages.require("/admin/mainpage.view")
            cherrypy.response.cookie['LastSawMainPage'] = time.time()
            return pages.get_template('index.html').render(api=notifications.api, alertsapi=alerts.api)
        
        @cherrypy.expose
        def dropdownpanel(self, *path, **data):
            pages.require("/admin/mainpage.view")
            return pages.get_template('dropdownpanel.html').render(api=notifications.api, alertsapi=alerts.api)
        
        

        # @cherrypy.expose
        # def alerts(self, *path, **data):
        #     pages.require("/admin/mainpage.view")
        #     return pages.get_template('alerts.html').render(api=notifications.api, alertsapi=alerts.api)

        @cherrypy.expose
        def tagpoints(self, *path, show_advanced='', **data):
            # This page could be slow because of the db stuff, so we restrict it more
            pages.require("/admin/settings.edit")
            if "new_numtag" in data:
                pages.postOnly()
                return pages.get_template('settings/tagpoint.html').render(new_numtag=data['new_numtag'], tagname=data['new_numtag'], show_advanced=True)
            if "new_strtag" in data:
                pages.postOnly()
                return pages.get_template('settings/tagpoint.html').render(new_strtag=data['new_strtag'], tagname=data['new_strtag'], show_advanced=True)
            
            if data:
                pages.postOnly()

            if path:
                if not path[0] in tagpoints.allTags:
                    raise ValueError("This tag does not exist")
                return pages.get_template('settings/tagpoint.html').render(tagName=path[0], data=data, show_advanced=show_advanced)
            else:                    
                return pages.get_template('settings/tagpoints.html').render(data=data)

        @cherrypy.expose
        def tagpointlog(self, *path, **data):
            # This page could be slow because of the db stuff, so we restrict it more
            pages.require("/admin/settings.edit")
            pages.postOnly()
            if not 'exportRows' in data:
                return pages.get_template('settings/tagpointlog.html').render(tagName=path[0], data=data)
            else:

                import pytz
                import datetime
                import dateutil.parser

                for i in tagpoints.allTags[path[0]]().configLoggers:
                    if i.accumType == data['exportType']:
                        tz = pytz.timezone(auth.getUserSetting(
                            pages.getAcessingUser(), 'timezone'))
                        logtime = tz.localize(dateutil.parser.parse(
                            data['logtime'])).timestamp()
                        raw = i.getDataRange(
                            logtime, time.time() + 10000000, int(data['exportRows']))

                        if data['exportFormat'] == "csv.iso":
                            cherrypy.response.headers['Content-Disposition'] = 'attachment; filename="%s"' % path[0].replace("/", "_").replace(
                                ".", "_").replace(":", "_")[1:] + "_" + data['exportType'] + tz.localize(dateutil.parser.parse(data['logtime'])).isoformat() + ".csv"
                            cherrypy.response.headers['Content-Type'] = 'text/csv'
                            d = ["Time(ISO), " + path[0].replace(",", '') +
                                 ' <accum ' + data['exportType'] + '>']
                            for i in raw:
                                dt = datetime.datetime.fromtimestamp(i[0])
                                d.append(dt.isoformat() +
                                         "," + str(i[1])[:128])
                            return '\r\n'.join(d) + '\r\n'

        @cherrypy.expose
        def zipstatic(self, *path, **data):
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

            m = mimetypes.guess_type(path[-1])
            cherrypy.response.headers['Content-Type'] = m[0]
            p = os.path.join(ddn, 'static', *path[:-1])
            with zipfile.ZipFile(p) as f:
                d = f.read(path[-1])
            zipcache[path] = d
            if len(zipcache) > 64:
                zipcache.pop(last=False)
            return d

        @cherrypy.expose
        def pagelisting(self, *path, **data):
            # Pagelisting knows to only show pages if you have permissions
            return pages.get_template('pagelisting.html').render_unicode(modules=modules.ActiveModules)

        # docs, helpmenu, and license are just static pages.
        @cherrypy.expose
        def docs(self, *path, **data):
            if path:
                if path[0] == "thirdparty":
                    p = os.path.normpath(os.path.join(
                        directories.srcdir, "docs", "/".join(path)))
                    if not p.startswith(os.path.join(directories.srcdir, "docs")):
                        raise RuntimeError("Invalid URL")
                    cherrypy.response.headers['Content-Type'] = mimetypes.guess_type(p)[
                        0]

                    with open(p, "rb") as f:
                        return(f.read())
                return pages.get_template('help/' + path[0] + '.html').render(path=path, data=data)
            return pages.get_template('help/help.html').render()

        @cherrypy.expose
        def makohelp(self, *path, **data):
            return pages.get_template('help/makoreference.html').render()

        @cherrypy.expose
        def about(self, *path, **data):
            return pages.get_template('help/about.html').render(myip=MyExternalIPAdress)

        @cherrypy.expose
        def changelog(self, *path, **data):
            return pages.get_template('help/changes.html').render(myip=MyExternalIPAdress)

        @cherrypy.expose
        def helpmenu(self, *path, **data):
            return pages.get_template('help/index.html').render()

        @cherrypy.expose
        def license(self, *path, **data):
            return pages.get_template('help/license.html').render()

        @cherrypy.expose
        def aerolabs_blockrain(self, *path, **data):
            # There is no reason to be particularly concerned here, I have no reason not to trust
            # Aerolabs, this is just for the people that hate hidden games and such.
            cherrypy.response.headers['Content-Security-Policy'] = "connect-src none"
            return pages.get_template('blockrain.html').render()

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
        try:
            cherrypy.response.body = bytes(pages.get_template('errors/cperror.html').render(
                e=_cperror.format_exc(), mk=mako.exceptions.html_error_template().render().decode()), 'utf8')
        except:
            cherrypy.response.body = bytes(pages.get_template(
                'errors/cperror.html').render(e=_cperror.format_exc(), mk=""), 'utf8')

    import zipfile

    from . import devices,btadmin

    # There are lots of other objects ad classes represeting subfolders of the website so we attatch them
    root = webapproot()
    root.login = weblogin.LoginScreen()
    root.auth = ManageUsers.ManageAuthorization()
    root.modules = modules_interface.WebInterface()
    root.settings = settings.Settings()
    root.settings.bt = btadmin.WebUI()
    root.errors = Errors()
    root.pages = usrpages.KaithemPage()
    root.logs = messagelogging.WebInterface()
    root.notifications = notifications.WI()
    root.widgets = widgets.WebInterface()
    root.syslog = logviewer.WebInterface()
    root.devices = devices.WebDevices()

    if not os.path.abspath(__file__).startswith("/usr/bin"):
        sdn = os.path.join(os.path.dirname(
            os.path.dirname(os.path.realpath(__file__))), "src")
        ddn = os.path.join(os.path.dirname(
            os.path.dirname(os.path.realpath(__file__))), "data")
    else:
        sdn = "/usr/lib/kaithem/src"
        ddn = "/usr/share/kaithem"

    def allow_upload(*args, **kwargs):
        # Only do the callback if needed. Assume it's really big if no header.
        if int(cherrypy.request.headers.get("Content-Length", 2**32)) > cherrypy.request.body.maxbytes:
            cherrypy.request.body.maxbytes = cherrypy.request.config['tools.allow_upload.f'](
            )

    cherrypy.tools.allow_upload = cherrypy.Tool(
        'before_request_body', allow_upload)

    site_config = {
        "request.body.maxbytes": 64 * 1024,
        "tools.encode.on": True,
        "tools.encode.encoding": 'utf-8',
        "tools.decode.on": True,
        "tools.decode.encoding": 'utf-8',
        'request.error_response': cpexception,
        'log.screen': config['cherrypy-log-stdout'],
        'server.socket_host': bindto,
        'server.socket_port': config['https-port'],
        'server.ssl_module': 'builtin',
        'server.ssl_certificate': os.path.join(directories.ssldir, 'certificate.cert'),
        'server.ssl_private_key': os.path.join(directories.ssldir, 'certificate.key'),
        'server.thread_pool': config['https-thread-pool'],
        'engine.autoreload.frequency': 5,
        'engine.autoreload.on': False,
        'tools.allow_upload.on': True,
        'tools.allow_upload.f': lambda: auth.getUserLimit(pages.getAcessingUser(), "web.maxbytes") or 64 * 1024,
    }

    wscfg = {'tools.websocket.on': True,
                'tools.websocket.handler_cls': widgets.websocket}

    wscfg_raw = {'tools.websocket.on': True,
                'tools.websocket.handler_cls': widgets.rawwebsocket}


    try:
        from hardline import ws4py_drayer
        wscfg3={'tools.websocket.on': True,
                'tools.websocket.handler_cls': ws4py_drayer.DrayerAPIWebSocket}
        root.drayer_api = ws4py_drayer.WebInterface()
    except Exception as e:
        wscfg3={}
        logging.exception("Could not load the Drayer WS API")
        messagebus.postMessage("/system/notifications/errors", "Drayer Server API disabled due to loading error, see logs")



    cnf = {
        '/static':
            {'tools.staticdir.on': True,
             'tools.staticdir.dir': os.path.join(ddn, 'static'),
             "tools.sessions.on": False,
             "tools.addheader.on": True,
             'tools.expires.on': True,
             'tools.expires.secs': 3600+48  # expire in 48 hours
             },

        '/static/js':
            {'tools.staticdir.on': True,
             'tools.staticdir.dir': os.path.join(sdn, 'js'),
             "tools.sessions.on": False,
             "tools.addheader.on": True
             },
        '/static/vue':
            {'tools.staticdir.on': True,
             'tools.staticdir.dir': os.path.join(sdn, 'vue'),
             "tools.sessions.on": False,
             "tools.addheader.on": True
             },
        '/static/css':
            {'tools.staticdir.on': True,
             'tools.staticdir.dir': os.path.join(sdn, 'css'),
             "tools.sessions.on": False,
             "tools.addheader.on": True
             },

        '/static/docs':
            {'tools.staticdir.on': True,
             'tools.staticdir.dir': os.path.join(sdn, 'docs'),
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
                'tools.allow_upload.on': True,
                'tools.allow_upload.f': lambda: auth.getUserLimit(pages.getAcessingUser(), "web.maxbytes") or 64 * 1024,
                'request.dispatch': cherrypy.dispatch.MethodDispatcher()
            },

        '/widgets/ws': wscfg,
        '/widgets/wsraw': wscfg_raw,
        '/drayer_api': wscfg3

    }

    if not config['favicon-png'] == "default":
        cnf['/favicon.png'] = {
            'tools.staticfile.on': True,
            'tools.staticfile.filename': os.path.join(directories.datadir, "static", config['favicon-png']),
            'tools.expires.on': True,
            'tools.expires.secs': 3600  # expire in an hour
        }

    if not config['favicon-ico'] == "default":
        cnf['/favicon.ico'] = {
            'tools.staticfile.on': True,
            'tools.staticfile.filename': os.path.join(directories.datadir, "static", config['favicon-ico']),
            'tools.expires.on': True,
            'tools.expires.secs': 3600  # expire in an hour
        }

    # Let the user create additional static directories
    for i in config['serve-static']:
        if i not in cnf:
            cnf["/usr/static/" + i] = {
                'tools.staticdir.on': True,
                'tools.staticdir.dir': config['serve-static'][i],
                "tools.sessions.on": False,
                "tools.addheader.on": True
            }

    def addheader(*args, **kwargs):
        "This function's only purpose is to tell the browser to cache requests for an hour"
        cherrypy.response.headers['Cache-Control'] = "max-age=28800"
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"

        #del cherrypy.response.headers['Expires']

    def pageloadnotify(*args, **kwargs):
        systasks.aPageJustLoaded()

    # As far as I can tell, this second server inherits everything from the "implicit" server
    # except what we override.
    server2 = cherrypy._cpserver.Server()
    server2.socket_port = config['http-port']
    server2._socket_host = bindto
    server2.thread_pool = config['http-thread-pool']
    server2.subscribe()

    cherrypy.config.update(site_config)
    cherrypy.tools.pageloadnotify = cherrypy.Tool(
        'on_start_resource', pageloadnotify)
    cherrypy.config['tools.pageloadnotify.on'] = True

    cherrypy.tools.addheader = cherrypy.Tool('before_finalize', addheader)

    if hasattr(cherrypy.engine, 'signal_handler'):
        del cherrypy.engine.signal_handler.handlers['SIGUSR1']
        cherrypy.engine.signal_handler.subscribe()

    cherrypy.tree.mount(root, config=cnf)

    if time.time() < 1420070400:
        messagebus.postMessage('/system/notifications/errors',
                               "System Clock is wrong, some features may not work properly.")

    if time.time() < util.min_time:
        messagebus.postMessage('/system/notifications/errors',
                               "System Clock may be wrong, or time has been set backwards at some point. If system clock is correct and this error does not go away, you can fix it manually be correcting folder name timestamps in the var dir.")

    cherrypy.engine.start()

    # Unlike other shm stuff that only gets used after startup, this
    # Can be used both before and after we are fully loaded.
    # So we need to hand off everything to the user we will actually run as.

    # This is also useful for when someone directly modifies config
    # Over SSH and we want to adopt those changes to the kaithem usr.

    # It's even useful if we ever change the user for some reason.

    # We only do this if we start as root though.

    if not config['run-as-user'] == 'root' and getpass.getuser() == 'root':
        try:
            d = "/dev/shm/kaithem_pyx_" + config['run-as-user']
            directories.rchown(d, config['run-as-user'])
            directories.rchown(directories.vardir, config['run-as-user'])
            directories.rchown(directories.logdir, config['run-as-user'])
            # Might as well own our own SSL dir, that way we can change certs via the webUI.
            directories.rchown(directories.ssldir, config['run-as-user'])
            directories.rchown(directories.usersdir, config['run-as-user'])
            directories.rchown(directories.regdir, config['run-as-user'])
        except:
            logger.exception("This is normal on non-unix")

    # If configured that way on unix, check if we are root and drop root.
    util.drop_perms(config['run-as-user'], config['run-as-group'])
    pylogginghandler.onUserChanged()
    messagebus.postMessage('/system/startup', 'System Initialized')
    messagebus.postMessage(
        '/system/notifications/important', 'System Initialized')

    r = util.zeroconf

    import zeroconf
    # Register an NTP service
    desc = {}

    if cfg.config['advertise-webui']:
        try:
            import socket
            if not cfg.config['webui-servicename'] == "default":
                localserver_name = cfg.config['webui-servicename']
            else:
                localserver_name = "kaithem_" + socket.gethostname()

            info = zeroconf.ServiceInfo("_http._tcp.local.",
                                        localserver_name + "._http._tcp.local.",
                                        [None], cfg.config['http-port'], 0, 0, desc)
            r.register_service(info)
            info2 = zeroconf.ServiceInfo("_https._tcp.local.",
                                         localserver_name + "._https._tcp.local.",
                                         [None], cfg.config['https-port'], 0, 0, desc)
            r.register_service(info2)
        except:
            logger.exception("Error advertising MDNS service")

    # Open a port to the outside world. Note that this can only be enabled through the webUI,
    # You are safe unless someone turns it on..
    workers.do(systasks.doUPnP)


webRoot()

# Wait till everything is set up to start the self test

cherrypy.engine.block()

logger.info("Cherrypy engine stopped")
