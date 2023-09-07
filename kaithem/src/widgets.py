# Copyright Daniel Dunn 2014-2015, 2018,2019
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
from typing import Any, Callable, Dict, Union, List
import tornado
from tornado import httputil
from tornado.concurrent import Future
from typeguard import typechecked
from .unitsofmeasure import convert, unitTypes
import ws4py.messaging
import ws4py
from ws4py.websocket import WebSocket
import weakref
import time
import json
import base64
import cherrypy
import os
import traceback
import threading
import logging
import socket
import copy
import collections
from . import auth, pages, unitsofmeasure, util, messagebus, workers
from .config import config

logger = logging.getLogger("system.widgets")

# Modify lock for any websocket's subscriptions
subscriptionLock = threading.Lock()
widgets = weakref.WeakValueDictionary()
n = 0

# We can keep track of how many. If more than 10, we stop making new ones for every
# connection.
wsrunners = weakref.WeakValueDictionary()


class WSActionRunner:
    """Class for running actions in a separate thread under a lock"""

    def __init__(self) -> None:
        self.wsActionSerializer = threading.Lock()
        self.wsActionQueue: List[Callable] = []
        wsrunners[id(self)] = self

    # We must serialize  actions to avoid out of order,
    # but for performance we really need to do them in the background
    def dowsAction(self, g):
        if len(self.wsActionQueue) > 10:
            time.sleep(1)

        self.wsActionQueue.append(g)

        # Somebody else got it
        if self.wsActionSerializer.locked():
            return

        def f():
            # As long as we have the lock ir means we are going to check at least one more time
            # to see if anyone else put something in the queue before we quit
            # Therefore if we can't get the lock, we can return, whoever has it will do the action
            # for us
            while self.wsActionQueue:
                if self.wsActionSerializer.acquire(blocking=False):
                    try:
                        while self.wsActionQueue:
                            x = self.wsActionQueue.pop(False)
                            x()
                    finally:
                        self.wsActionSerializer.release()

        workers.do(f)


# All guests share a runner, logged in users get their own per-connection
guestWSRunner = WSActionRunner()


def eventErrorHandler(f):
    # If we can, try to send the exception back whence it came
    try:
        from . import newevt

        if f.__module__ in newevt.eventsByModuleName:
            newevt.eventsByModuleName[f.__module__]._handle_exception()
    except:
        print(traceback.format_exc())


defaultDisplayUnits = {
    "temperature": "degC|degF",
    "length": "m",
    "weight": "g",
    "pressure": "psi|Pa",
    "voltage": "V",
    "current": "A",
    "power": "W",
    "frequency": "Hz",
    "ratio": "%",
}

server_session_ID = str(time.time()) + str(os.urandom(8))


def mkid():
    global n
    n = (n + 1) % 10000
    return "id" + str(n)


class ClientInfo:
    def __init__(self, user, cookie=None):
        self.user = user
        self.cookie = cookie


lastLoggedUserError = 0

lastPrintedUserError = 0


class WebInterface:
    @cherrypy.expose
    def ws(self):
        pages.strictNoCrossSite()
        # you can access the class instance through
        handler = cherrypy.request.ws_handler
        x = cherrypy.request.remote.ip
        try:
            handler.user_agent = cherrypy.request.headers["User-Agent"]
        except Exception:
            pass

        if cherrypy.request.scheme == "https" or pages.isHTTPAllowed(x):
            handler.user = pages.getAcessingUser()
            handler.cookie = cherrypy.request.cookie
        else:
            handler.cookie = None
            handler.user = "__guest__"

        handler.clientinfo = ClientInfo(handler.user, handler.cookie)
        clients_info[handler.uuid] = handler.clientinfo

    @cherrypy.expose
    def wsraw(self, *a, **k):
        pages.strictNoCrossSite()
        # you can access the class instance through
        handler = cherrypy.request.ws_handler
        x = cherrypy.request.remote.ip
        try:
            handler.user_agent = cherrypy.request.headers["User-Agent"]
        except:
            pass

        if cherrypy.request.scheme == "https" or pages.isHTTPAllowed(x):
            handler.user = pages.getAcessingUser()
            handler.cookie = cherrypy.request.cookie
        else:
            handler.cookie = None
            handler.user = "__guest__"
        handler.clientinfo = ClientInfo(handler.user, handler.cookie)
        clients_info[handler.uuid] = handler.clientinfo

    @cherrypy.expose
    def session_id(self):
        return server_session_ID


def subsc_closure(self, i, widget):
    def f(msg, raw):
        try:
            self.send(msg)
        except socket.error:
            # These happen sometimes when things are disconnecting it seems,
            # And there's no need to waste log space or send a notification.
            pass
        except:
            if not widget.errored_send:
                widget.errored_send = True
                messagebus.postMessage(
                    "/system/notifications/errors",
                    "Problem in widget " + repr(widget) + ", see logs",
                )
                logger.exception(
                    "Error sending data from widget " + repr(widget) + " via websocket"
                )
            else:
                logging.exception("Error sending data from websocket")

    return f


def raw_subsc_closure(self, i, widget):
    def f(msg, raw):
        try:
            if isinstance(raw, bytes):
                self.send(raw)
            else:
                self.send(json.dumps(raw))

        except socket.error as e:
            if e.errno == 32:
                self.closeUnderLock()
            # These happen sometimes when things are disconnecting it seems,
            # And there's no need to waste log space or send a notification.
            print("wtimeout", traceback.format_exc())
        except:
            if not widget.errored_send:
                widget.errored_send = True
                messagebus.postMessage(
                    "/system/notifications/errors",
                    "Problem in widget " + repr(widget) + ", see logs",
                )
                logger.exception(
                    "Error sending data from widget " + repr(widget) + " via websocket"
                )
            else:
                logging.exception("Error sending data from websocket")

    return f


clients_info = weakref.WeakValueDictionary()

ws_connections = weakref.WeakValueDictionary()


def getConnectionRefForID(id, deleteCallback=None):
    try:
        return weakref.ref(ws_connections[id], deleteCallback)
    except KeyError:
        return None


usingmp = False
try:
    import msgpack

    usingmp = True
except:
    logging.exception("No msgpack support, using JSON fallback")


# Message, start time, duration
lastGlobalAlertMessage = ["", 0, 0]


def sendToAll(d):
    d = json.dumps(d)
    x = {}

    # Retry against the dict changed size during iteration thing
    for i in range(50):
        try:
            for j in ws_connections:
                if not j in x:
                    ws_connections[j].send(d)
                    x[j] = True
            break
        except:
            logging.exception("Error in global broadcast")


def sendGlobalAlert(msg, duration=60):
    lastGlobalAlertMessage[0] = msg
    lastGlobalAlertMessage[1] = time.monotonic()
    lastGlobalAlertMessage[2] = duration

    sendToAll([["__SHOWSNACKBAR__", [msg, float(duration)]]])


def sendTo(topic, value, target):
    "Send a value to one subscriber by the connection ID"
    if usingmp:
        d = msgpack.packb([[topic, value]])
    else:
        d = json.dumps([[topic, value]])
    if len(d) > 32 * 1024 * 1024:
        raise ValueError("Data is too large, refusing to send")
    ws_connections[target].send(d)


userBatteryAlerts = {}


class websocket_impl:
    def __init__(self, parent, user, *args, **kwargs):
        self.subscriptions = []
        self.lastPushedNewData = 0
        self.uuid = (
            "id"
            + base64.b64encode(os.urandom(16))
            .decode()
            .replace("/", "")
            .replace("-", "")
            .replace("+", "")[:-2]
        )
        self.parent = parent
        self.user = user
        self.widget_wslock = threading.Lock()
        self.subCount = 0
        ws_connections[self.uuid] = self
        messagebus.subscribe("/system/permissions/rmfromuser", self.onPermissionRemoved)

        self.pageURL = "UNKNOWN"

        self.usedPermissions = collections.defaultdict(lambda: 0)

        if auth.getUserSetting(self.user, "telemetry-alerts"):
            from . import alerts

            if not self.user in userBatteryAlerts:
                userBatteryAlerts[self.user] = alerts.Alert(
                    "Low battery on client browser device for: " + self.user,
                    priority="warning",
                )
            self.batteryAlertRef = userBatteryAlerts[self.user]
        else:
            try:
                del userBatteryAlerts[self.user]
            except KeyError:
                pass

    def onPermissionRemoved(self, t, v):
        "Close the socket if the user no longer has the permission"
        if v[0] == self.user and v[1] in self.usedPermissions:
            self.closeUnderLock()

    def send(self, b, *a, **k):
        with self.widget_wslock:
            self.parent.send_data(b, binary=isinstance(b, bytes))

    def closed(self, *a):
        with subscriptionLock:
            for i in self.subscriptions:
                try:
                    widgets[i].subscriptions.pop(self.uuid)
                    widgets[i].subscriptions_atomic = widgets[i].subscriptions.copy()

                    if not widgets[i].subscriptions:
                        widgets[i].lastSubscribedTo = time.monotonic()
                except Exception:
                    pass

    def closeUnderLock(self):
        def f():
            with self.widget_wslock:
                self.close()

    def received_message(self, message):
        global lastLoggedUserError
        global lastPrintedUserError
        try:
            if isinstance(message, ws4py.messaging.BinaryMessage):
                d = message.data
            else:
                d = message

            if isinstance(d, bytes):
                o = msgpack.unpackb(d, raw=False)
            else:
                o = json.loads(d)

            resp = []
            user = self.user

            upd = o["upd"]
            for i in upd:
                if i[0] in widgets:
                    widgets[i[0]]._onUpdate(user, i[1], self.uuid)
                elif i[0] == "__url__":
                    self.pageURL = i[1]

                elif i[0] == "__geo__":
                    self.geoLocation = i[1]

                elif i[0] == "__BATTERY__":
                    self.batteryStatus = i[1]
                    if self.user in userBatteryAlerts:
                        try:
                            if i[1]["level"] < 0.2 and not i[1]["charging"]:
                                userBatteryAlerts[self.user].trip()
                            elif i[1]["level"] > 0.4 and i[1]["charging"]:
                                userBatteryAlerts[self.user].release()
                        except:
                            logging.exception("Error in battery status telemetry")

                elif i[0] == "__USERIDLE__":
                    self.userState = i[1]["userState"]
                    self.screenState = i[1]["screenState"]
                elif i[0] == "__ERROR__":
                    # Only log one user error per minute, globally.  It's not meant to catch *everything*,
                    # just to give you a decent change
                    if lastLoggedUserError < time.time() - 10:
                        logger.error(
                            "Client side err(These are globally ratelimited):\r\n"
                            + i[1]
                        )
                        lastLoggedUserError = time.time()

                    elif lastPrintedUserError < time.time() - 1:
                        print(
                            "Client side err(These are globally ratelimited):\r\n"
                            + i[1]
                        )
                        lastPrintedUserError = time.time()

            if "subsc" in o:
                for i in o["subsc"]:
                    if i in self.subscriptions:
                        continue
                    if i == "__WIDGETERROR__":
                        continue
                    elif i == "__SHOWMESSAGE__":
                        continue
                    elif i == "__SHOWSNACKBAR__":
                        if lastGlobalAlertMessage[0] and lastGlobalAlertMessage[1] > (
                            time.monotonic() - lastGlobalAlertMessage[2]
                        ):
                            self.send(
                                json.dumps(
                                    [
                                        [
                                            "__SHOWSNACKBAR__",
                                            [
                                                lastGlobalAlertMessage[0],
                                                lastGlobalAlertMessage[2]
                                                - (
                                                    time.monotonic()
                                                    - lastGlobalAlertMessage[1]
                                                ),
                                            ],
                                        ]
                                    ]
                                )
                            )

                    # TODO: DoS by filling memory with subscriptions?? This should at least stop accidental attacks
                    if self.subCount > 1024:
                        raise RuntimeError(
                            "Too many subscriptions for this connnection"
                        )

                    with subscriptionLock:
                        if i in widgets:
                            for p in widgets[i]._read_perms:
                                if not pages.canUserDoThis(p, user):
                                    # We have to be very careful about this, because
                                    self.send(
                                        json.dumps(
                                            [
                                                [
                                                    "__SHOWMESSAGE__",
                                                    "You are missing permission: "
                                                    + str(p)
                                                    + ", data may be incorrect",
                                                ]
                                            ]
                                        )
                                    )
                                    raise RuntimeError(
                                        user + " missing permission: " + str(p)
                                    )
                                self.usedPermissions[p] += 1

                            widgets[i].subscriptions[self.uuid] = subsc_closure(
                                self, i, widgets[i]
                            )
                            widgets[i].subscriptions_atomic = widgets[
                                i
                            ].subscriptions.copy()
                            # This comes after in case it  sends data
                            widgets[i].onNewSubscriber(user, {})
                            widgets[i].lastSubscribedTo = time.monotonic()

                            self.subscriptions.append(i)
                            if not widgets[i].noOnConnectData:
                                x = widgets[i]._onRequest(user, self.uuid)
                                if not x is None:
                                    widgets[i].send(x)
                            self.subCount += 1

            if "unsub" in o:
                for i in o["unsub"]:
                    if not i in self.subscriptions:
                        continue

                    # TODO: DoS by filling memory with subscriptions??
                    with subscriptionLock:
                        if i in widgets:
                            if widgets[i].subscriptions.pop(self.uuid, None):
                                self.subCount -= 1

                                for p in widgets[i].permissions:
                                    self.usedPermissions[p] -= 1
                                    if self.usedPermissions[p] == 0:
                                        del self.usedPermissions[p]
                            widgets[i].subscriptions_atomic = widgets[
                                i
                            ].subscriptions.copy()

        except Exception as e:
            logging.exception("Error in widget, responding to " + str(d))
            messagebus.postMessage(
                "system/errors/widgets/websocket", traceback.format_exc(6)
            )
            self.send(json.dumps({"__WIDGETERROR__": repr(e)}))


def makeTornadoSocket():
    import tornado.websocket

    class WS(tornado.websocket.WebSocketHandler):
        def open(self):
            x = self.request.remote_ip

            try:
                user_agent = self.request.headers["User-Agent"]
            except Exception:
                user_agent = ""

            if self.request.protocol == "https" or pages.isHTTPAllowed(x):
                user = pages.getAcessingUser(self.request)
                cookie = self.request.cookies
            else:
                cookie = None
                user = "__guest__"

            self.io_loop = tornado.ioloop.IOLoop.current()
            impl = websocket_impl(self, user)
            impl.cookie = cookie
            impl.user_agent = user_agent

            impl.clientinfo = ClientInfo(impl.user, impl.cookie)
            clients_info[impl.uuid] = impl.clientinfo
            self.impl = impl

            if (
                user == "__guest__"
                and (not x.startswith("127."))
                and (len(wsrunners) > 8)
            ):
                self.runner = guestWSRunner
            else:
                self.runner = WSActionRunner()

        def on_message(self, message):
            def doFunction():
                self.impl.received_message(message)

            self.runner.dowsAction(doFunction)

        def send_data(self, message, binary=False):
            def f():
                if self.close_code is None:
                    self.write_message(message, binary=binary)

            self.io_loop.add_callback(f)

        def on_close(self):
            self.impl.closed()

    return WS


import urllib


class rawwebsocket_impl:
    def __init__(self, *args, **kwargs):
        self.subscriptions = []
        self.lastPushedNewData = 0
        self.uuid = (
            "id"
            + base64.b64encode(os.urandom(16))
            .decode()
            .replace("/", "")
            .replace("-", "")
            .replace("+", "")[:-2]
        )
        self.widget_wslock = threading.Lock()
        self.subCount = 0
        ws_connections[self.uuid] = self
        messagebus.subscribe("/system/permissions/rmfromuser", self.onPermissionRemoved)
        self.user = "__guest__"
        x = cherrypy.request.remote.ip

        if cherrypy.request.scheme == "https" or pages.isHTTPAllowed(x):
            self.user = pages.getAcessingUser()
        else:
            self.user = "__guest__"
        self.usedPermissions = collections.defaultdict(lambda: 0)

        params = urllib.parse.parse_qs(args[3]["QUERY_STRING"])
        widgetName = params["widgetid"][0]
        WebSocket.__init__(self, *args, **kwargs)

        with subscriptionLock:
            if widgetName in widgets:
                for p in widgets[widgetName]._read_perms:
                    if not pages.canUserDoThis(p, self.user):
                        raise RuntimeError(self.user + " missing permission: " + str(p))
                    self.usedPermissions[p] += 1

                widgets[widgetName].subscriptions[self.uuid] = raw_subsc_closure(
                    self, widgetName, widgets[widgetName]
                )
                widgets[widgetName].subscriptions_atomic = widgets[
                    widgetName
                ].subscriptions.copy()
                # This comes after in case it  sends data
                widgets[widgetName].onNewSubscriber(self.user, {})
                widgets[widgetName].lastSubscribedTo = time.monotonic()

                self.subscriptions.append(widgetName)
                self.subCount += 1

    def onPermissionRemoved(self, t, v):
        "Close the socket if the user no longer has the permission"
        if v[0] == self.user and v[1] in self.usedPermissions:
            self.closeUnderLock()

    def closeUnderLock(self):
        def f():
            with self.widget_wslock:
                self.close()

        workers.do(f)

    def send(self, *a, **k):
        with self.widget_wslock:
            self.parent.send_data(self, *a, **k, binary=isinstance(a[0], bytes))

    def closed(self, code, reason):
        with subscriptionLock:
            for i in self.subscriptions:
                try:
                    widgets[i].subscriptions.pop(self.uuid)
                    widgets[i].subscriptions_atomic = widgets[i].subscriptions.copy()

                    if not widgets[i].subscriptions:
                        widgets[i].lastSubscribedTo = time.monotonic()
                except:
                    pass


def randID():
    "Generate a base64 id"
    return (
        base64.b64encode(os.urandom(8))[:-1]
        .decode()
        .replace("+", "")
        .replace("/", "")
        .replace("-", "")
    )


idlock = threading.RLock()


widgets_by_subsc_carryover = weakref.WeakValueDictionary()


class Widget:
    def __init__(self, *args, subsc_carryover=None, **kwargs):
        self.value = None
        self._read_perms = []
        self._write_perms = []
        self.errored_function = None
        self.errored_getter = None
        self.errored_send = None
        self.subscriptions = {}
        self.subscriptions_atomic = {}
        self.echo = True
        self.noOnConnectData = False

        # Used for GC, we have a fake subscriber right away so we can do a grace
        # Period before trashing it.
        # Also tracks unsubscribe, you need to combine this with if there are any subscribers
        self.lastSubscribedTo = time.monotonic()

        def f(u, v):
            pass

        def f2(u, v, id):
            pass

        self._callback = f
        self._callback2 = f2

        with idlock:
            # Give the widget an ID for the client to refer to it by
            # Note that it's no longer always a  uuid!!
            if not "id" in kwargs:
                for i in range(0, 250000):
                    self.uuid = randID()
                    if not self.uuid in widgets:
                        break
                    if i > 240000:
                        raise RuntimeError("No more IDs?")
            else:
                self.uuid = kwargs["id"]

            # oldWidget = widgets_by_subsc_carryover.get(self.uuid, None)

            # Insert self into the widgets list
            widgets[self.uuid] = self

        # Unused for now
        # # Lets you make
        # with subscriptionLock:
        #     if oldWidget:
        #         try:
        #             self.subscribers.update(oldWidget.subscriptions_atomic)
        #             self.subscriptions_atomic=copy.deepcopy(self.subscriptions)
        #         except:
        #             logging.exception

        # if subsc_carryover:
        #     widgets_by_subsc_carryover[subsc_carryover]= self

    def stillActive(self):
        if self.subscriptions or (self.lastSubscribedTo > (time.monotonic() - 30)):
            return True

    def onNewSubscriber(self, user, cid, **kw):
        pass

    def forEach(self, callback):
        "For each client currently subscribed, call callback with a clientinfo object"
        for i in self.subscriptions:
            callback(clients_info[i])

    # This function is called by the web interface code
    def _onRequest(self, user, uuid):
        """Widgets on the client side send AJAX requests for the new value. This function must
        return the value for the widget. For example a slider might request the newest value.

        This function is also responsible for verifying that the user has the right permissions

        This function is generally only called by the library.

        This function returns if the user does not have permission

        Args:
            user(string):
                the username of the user who is tring to access things.
        """
        for i in self._read_perms:
            if not pages.canUserDoThis(i, user):
                return "PERMISSIONDENIED"
        try:
            return self.onRequest(user, uuid)
        except Exception as e:
            logger.exception("Error in widget request to " + repr(self))
            if not (self.errored_getter == id(self._callback)):
                messagebus.postMessage(
                    "/system/notifications/errors",
                    "Error in widget getter function %s defined in module %s, see logs for traceback.\nErrors only show the first time a function has an error until it is modified or you restart Kaithem."
                    % (self._callback.__name__, self._callback.__module__),
                )
                self.errored_getter = id(self._callback)

    # This function is meant to be overridden or used as is
    def onRequest(self, user, uuid):
        """This function is called after permissions have been verified when a client requests the current value. Usually just returns self.value

        Args:
            user(string):
                The username of the acessung client
        """
        return self.value

    # This function is called by the web interface whenever this widget is written to
    def _onUpdate(self, user, value, uuid):
        """Called internally to write a value to the widget. Responisble for verifying permissions. Returns if user does not have permission"""
        for i in self._read_perms:
            if not pages.canUserDoThis(i, user):
                return

        for i in self._write_perms:
            if not pages.canUserDoThis(i, user):
                return

        self.onUpdate(user, value, uuid)

    def doCallback(self, user, value, uuid):
        "Run the callback, and if said callback fails, post a message about it."
        try:
            self._callback(user, value)
        except Exception as e:
            eventErrorHandler(self._callback)
            logger.exception("Error in widget callback for " + repr(self))
            if not (self.errored_function == id(self._callback)):
                messagebus.postMessage(
                    "/system/notifications/errors",
                    "Error in widget callback function %s defined in module %s, see logs for traceback.\nErrors only show the first time a function has an error until it is modified or you restart Kaithem."
                    % (self._callback.__name__, self._callback.__module__),
                )
                self.errored_function = id(self._callback)
            raise e

        try:
            self._callback2(user, value, uuid)
        except Exception as e:
            logger.exception("Error in widget callback for " + repr(self))
            eventErrorHandler(self._callback2)
            if not (self.errored_function == id(self._callback)):
                messagebus.postMessage(
                    "/system/notifications/errors",
                    "Error in widget callback function %s defined in module %s, see logs for traceback.\nErrors only show the first time a function has an error until it is modified or you restart Kaithem."
                    % (self._callback.__name__, self._callback.__module__),
                )
                self.errored_function = id(self._callback)
            raise e

    # Return True if this user can write to it
    def isWritable(self):
        for i in self._write_perms:
            if not pages.canUserDoThis(i):
                return "disabled"
        return ""

    # Set a callback if it ever changes
    @typechecked
    def attach(self, f: Callable):
        self._callback = f

    # Set a callback if it ever changes.
    # This version also gives you the connection ID
    @typechecked
    def attach2(self, f: Callable):
        self._callback2 = f

    # meant to be overridden or used as is
    def onUpdate(self, user, value, uuid):
        self.value = value
        self.doCallback(user, value, uuid)
        if self.echo:
            self.send(value)

    # Read and write are called by code on the server
    def read(self):
        return self.value

    def write(self, value, push=True):
        self.value = value
        self.doCallback("__SERVER__", value, "__SERVER__")
        if push:
            self.send(value)

    def send(self, value):
        "Send a value to all subscribers without invoking the local callback or setting the value"
        if usingmp:
            d = msgpack.packb([[self.uuid, value]], use_bin_type=True)
        else:
            d = json.dumps([[self.uuid, value]])

        # Very basic saniy check here
        if len(d) > 32 * 1024 * 1024:
            raise ValueError("Data is too large, refusing to send")

        # Yes, I really had a KeyError here. Somehow the dict was replaced with the new version in the middle of iteration
        # So we use an intermediate value so we know it won't change
        x = self.subscriptions_atomic
        for i in x:
            try:
                x[i](d, value)
            except Exception:
                print("WS Send Error ", traceback.format_exc())

    def __del__(self):
        try:
            d = json.dumps([[self.uuid]])

            # Yes, I really had a KeyError here. Somehow the dict was replaced with the new version in the middle of iteration
            # So we use an intermediate value so we know it won't change
            x = self.subscriptions_atomic
            for i in x:
                try:
                    x[i](d, None)
                except Exception:
                    print("WS Send Error ", traceback.format_exc())
        except Exception:
            print(traceback.format_exc())

    def sendTo(self, value, target):
        "Send a value to one subscriber by the connection ID"
        if usingmp:
            d = msgpack.packb([[self.uuid, value]])
        else:
            d = json.dumps([[self.uuid, value]])
        if len(d) > 32 * 1024 * 1024:
            raise ValueError("Data is too large, refusing to send")
        if target in self.subscriptions_atomic:
            self.subscriptions_atomic[target](d, value)

    # Lets you add permissions that are required to read or write the widget.
    def require(self, permission):
        self._read_perms.append(permission)

    def requireToWrite(self, permission):
        self._write_perms.append(permission)

    def setPermissions(self, read, write):
        self._read_perms = copy.copy(read)
        self._write_perms = copy.copy(write)


# This widget is just a time display, it doesn't really talk to the server, but it's useful to keep the same interface.


class TimeWidget(Widget):
    def onRequest(self, user, uuid):
        return str(unitsofmeasure.strftime())

    def render(self, type="widget"):
        """
        Args:
            type(string): if "widget",  returns it with normal widget styling. If "inline", it jsut looks like a span.
        Returns:
            string: An HTML and JS string that can be directly added as one would add any HTML inline block tag
        """
        if type == "widget":
            return """<div id="%s" class="widgetcontainer">
            <script type="text/javascript" src="/static/js/strftime-min.js">
            </script>
            <script type="text/javascript">
            var f = function(val)
            {
               var d = new Date();

                document.getElementById("%s").innerHTML=d.strftime("%s");
            }
            setInterval(f,70);
            </script>
            </div>""" % (
                self.uuid,
                self.uuid,
                auth.getUserSetting(pages.getAcessingUser(), "strftime").replace(
                    "%l", "%I"
                ),
            )

        elif type == "inline":
            return """<span id="%s">
            <script type="text/javascript" src="/static/js/strftime-min.js">
            </script>
            <script type="text/javascript">
            var f = function(val)
            {
               var d = new Date();

                document.getElementById("%s").innerHTML=d.strftime("%s");
            }
            setInterval(f,70);
            </script>
            </span>""" % (
                self.uuid,
                self.uuid,
                auth.getUserSetting(pages.getAcessingUser(), "strftime").replace(
                    "%l", "%I"
                ),
            )
        else:
            raise ValueError("Invalid type")


time_widget = TimeWidget(Widget)


class DynamicSpan(Widget):
    attrs = ""

    def __init__(self, *args, extraInfo=None, **kwargs):
        Widget.__init__(self, *args, **kwargs)
        self.extraInfo = extraInfo

    def write(self, value, push=True):
        self.value = str(value)[:255]
        Widget.write(self, self.value, push)

    def getExtraInfo(self):
        if self.extraInfo:
            return self.extraInfo()
        else:
            return ""

    def render(self):
        """
        Returns:
            string: An HTML and JS string that can be directly added as one would add any HTML inline block tag
        """

        return """<span id="%s" %s>
        <script type="text/javascript">
        var upd = function(val)
        {
            document.getElementById("%s").innerHTML=val;
        }
        kaithemapi.subscribe('%s',upd);
        </script>%s
        </span>""" % (
            self.uuid,
            self.attrs,
            self.uuid,
            self.uuid,
            self.value,
        )

    def render_as_span(self, label=""):
        return label + self.render()


class DataSource(Widget):
    attrs = ""

    def render(self):
        raise RuntimeError(
            "This is not a real widget, you must manually subscribe to this widget's ID and build your own handling for it."
        )


class TextDisplay(Widget):
    def render(self, height="4em", width="24em"):
        """
        Returns:
            string: An HTML and JS string that can be directly added as one would add any HTML inline block tag
        """
        # We only want to update the div when it has changed, otherwise some browsers might not let you click the links
        return """<div style="height:%s; width:%s; overflow-x:auto; overflow-y:scroll;" class="widgetcontainer" id="%s">
        <script type="text/javascript">
        KWidget_%s_prev = "PlaceHolder1234";
        var upd = function(val)
        {
            if(val == KWidget_%s_prev || val==null)
            {

            }
            else
            {
                document.getElementById("%s").innerHTML=val;
                KWidget_%s_prev = val;
            }
        }
        kaithemapi.subscribe('%s',upd);
        </script>%s
        </div>""" % (
            height,
            width,
            self.uuid,
            self.uuid,
            self.uuid,
            self.uuid,
            self.uuid,
            self.uuid,
            self.value,
        )


# Gram is the base unit even though Si has kg as the base
# Because it makes it *SO* much easier
siUnits = {"m", "Pa", "g", "V", "A"}


class Meter(Widget):
    def __init__(self, *args, extraInfo=None, **kwargs):
        self.k = kwargs
        if not "high" in self.k:
            self.k["high"] = 10000
        if not "high_warn" in self.k:
            self.k["high_warn"] = self.k["high"]
        if not "low" in self.k:
            self.k["low"] = -10000
        if not "low_warn" in self.k:
            self.k["low_warn"] = self.k["low"]
        if not "min" in self.k:
            self.k["min"] = 0
        if not "max" in self.k:
            self.k["max"] = 100

        self.extraInfo = extraInfo

        self.displayUnits = None
        self.defaultLabel = ""
        if not "unit" in kwargs:
            self.unit = None
        else:
            try:
                # Throw an error if you give it a bad unit
                self.unit = kwargs["unit"]
                # Do a KeyError if we don't support the unit
                unitTypes[self.unit] + "_format"
            except:
                self.unit = None
                logging.exception("Bad unit")

        Widget.__init__(self, *args, **kwargs)
        self.value = [0, "normal", self.formatForUser(0)]

    def getExtraInfo(self):
        if self.extraInfo:
            return self.extraInfo()
        else:
            return ""

    def write(self, value, push=True):
        # Decide a class so it can show red or yellow with high or low values.
        self.c = "normal"

        if "high_warn" in self.k:
            if value >= self.k["high_warn"]:
                self.c = "warning"

        if "low_warn" in self.k:
            if value <= self.k["low_warn"]:
                self.c = "warning"

        if "high" in self.k:
            if value >= self.k["high"]:
                self.c = "error"

        if "low" in self.k:
            if value <= self.k["low"]:
                self.c = "error"
        self.value = [round(value, 3), self.c, self.formatForUser(value)]
        Widget.write(self, self.value, push)

    def setup(self, min, max, high, low, unit=None, displayUnits=None):
        "On-the-fly change of parameters"
        d = {
            "high": high,
            "low": low,
            "high_warn": high,
            "low_warn": low,
            "min": min,
            "max": max,
        }
        self.k.update(d)

        if not unit:
            self.unit = None
        else:
            self.displayUnits = displayUnits
            try:
                # Throw an error if you give it a bad unit
                self.unit = unit

                # Do a KeyError if we don't support the unit
                unitTypes[self.unit] + "_format"
            except:
                logging.exception("Bad unit")
                self.unit = None
        Widget.write(self, self.value + [d])

    def onUpdate(self, *a, **k):
        raise RuntimeError("Only the server can edit this widget")

    def formatForUser(self, v, displayUnit=None):
        """Format the value into something for display, like 27degC, if we have a unit configured.
        Otherwise just return the value
        """
        try:
            unit = self.unit
            if unit:
                s = ""

                x = unitTypes[unit]

                if x in defaultDisplayUnits:
                    if not unit == "dBm":
                        units = defaultDisplayUnits[x]
                    else:
                        units = "dBm"
                else:
                    return str(round(v, 3)) + unit
                # Overrides are allowed, we ignorer the user specified units
                if self.displayUnits:
                    units = self.displayUnits
                else:
                    # Always show the base unit by default
                    if not unit in units:
                        units += "|" + unit
                # else:
                #    units = auth.getUserSetting(pages.getAcessingUser(),dimensionality_strings[unit.dimensionality]+"_format").split("|")

                for i in units.split("|"):
                    if s:
                        s += "/"
                    # Si abbreviations and symbols work with prefixes
                    if i in siUnits:
                        s += unitsofmeasure.siFormatNumber(convert(v, unit, i)) + i
                    else:
                        # If you need more than three digits,
                        # You should probably use an SI prefix.
                        # We're just hardcoding this for now
                        s += str(round(convert(v, unit, i), 2)) + i

                return s.replace("degC", "C").replace("degF", "F") + self.getExtraInfo()
            else:
                return str(round(v, 3)) + self.getExtraInfo()
        except Exception as e:
            print(traceback.format_exc())
            return str(round(v, 3)) + str(e)[:16]

    def render_as_span(self, label=""):
        """
        Returns:
            string: An HTML and JS string that can be directly added as one would add any HTML inline block tag
        """
        return """%s<span id="%s">
        <script type="text/javascript">
        var upd = function(val)
        {
            document.getElementById("%s").innerHTML=val[2];
        }
        kaithemapi.subscribe('%s',upd);
        </script>%s
        </span>""" % (
            label,
            self.uuid,
            self.uuid,
            self.uuid,
            self.value[2],
        )

    def render(self, unit="", label=None):
        label = label or self.defaultLabel
        return """
        <div class="widgetcontainer meterwidget">
        {label}<br>
        <span class="numericpv" id="{uuid}" style=" margin:0px;">
        <script type="text/javascript">
        var upd = function(val)
        {{
            document.getElementById("{uuid}_m").value=val[0];
            document.getElementById("{uuid}").className=val[1]+" numericpv";
            document.getElementById("{uuid}").innerHTML=val[2]+'<span style="color:grey">{unit}</span>';

            if(val[3])
            {{
                document.getElementById("{uuid}_m").high = val[3].high;
                document.getElementById("{uuid}_m").low = val[3].low;
                document.getElementById("{uuid}_m").min = val[3].min;
                document.getElementById("{uuid}_m").max = val[3].max;
            }}
        }}
        kaithemapi.subscribe('{uuid}',upd);
        </script>{valuestr}
        </span></br>
        <meter id="{uuid}_m" value="{value:f}" min="{min:f}" max="{max:f}" high="{high:f}" low="{low:f}"></meter>

        </div>""".format(
            uuid=self.uuid,
            value=self.value[0],
            min=self.k["min"],
            max=self.k["max"],
            high=self.k["high_warn"],
            low=self.k["low_warn"],
            label=label,
            unit=unit,
            valuestr=self.formatForUser(self.value[0], unit),
        )

    def render_oneline(self, unit="", label=None):
        label = label or self.defaultLabel
        return """
        {label}
        <span class="numericpv" id="{uuid}" style=" margin:0px;">
        <script type="text/javascript">
        var upd = function(val)
        {{
            document.getElementById("{uuid}_m").value=val[0];
            document.getElementById("{uuid}").className=val[1]+" numericpv";
            document.getElementById("{uuid}").innerHTML=val[2]+'<span style="color:grey">{unit}</span>';

            if(val[3])
            {{
                document.getElementById("{uuid}_m").high = val[3].high;
                document.getElementById("{uuid}_m").low = val[3].low;
                document.getElementById("{uuid}_m").min = val[3].min;
                document.getElementById("{uuid}_m").max = val[3].max;
            }}
        }}
        kaithemapi.subscribe('{uuid}',upd);
        </script>{valuestr}
        </span>
        <meter id="{uuid}_m" value="{value:f}" min="{min:f}" max="{max:f}" high="{high:f}" low="{low:f}"></meter>

        """.format(
            uuid=self.uuid,
            value=self.value[0],
            min=self.k["min"],
            max=self.k["max"],
            high=self.k["high_warn"],
            low=self.k["low_warn"],
            label=label,
            unit=unit,
            valuestr=self.formatForUser(self.value[0], unit),
        )

    def render_compact(self, unit="", label=None):
        label = label or self.defaultLabel
        return """
        <div style="display: inline">
        <script type="text/javascript">
        var upd = function(val)
        {{
            document.getElementById("{uuid}_m").value=val[0];
            document.getElementById("{uuid}").className=val[1]+" numericpv";
            document.getElementById("{uuid}").innerHTML=val[2]+'<span style="color:grey">{unit}</span>';

            if(val[3])
            {{
                document.getElementById("{uuid}_m").high = val[3].high;
                document.getElementById("{uuid}_m").low = val[3].low;
                document.getElementById("{uuid}_m").min = val[3].min;
                document.getElementById("{uuid}_m").max = val[3].max;
            }}
        }}
        kaithemapi.subscribe('{uuid}',upd);
        </script>
        <div style="display: inline">
        <span class="numericpv" id="{uuid}" style=" margin:0px;">
        {valuestr}
        </span><br>
        <meter id="{uuid}_m" value="{value:f}" min="{min:f}" max="{max:f}" high="{high:f}" low="{low:f}" style="width: 100%"></meter>
        </div>
        </div>""".format(
            uuid=self.uuid,
            value=self.value[0],
            min=self.k["min"],
            max=self.k["max"],
            high=self.k["high_warn"],
            low=self.k["low_warn"],
            label=label,
            unit=unit,
            valuestr=self.formatForUser(self.value[0], unit),
        )


class Button(Widget):
    def render(self, content, type="default"):
        if type == "default":
            return """
            <button %s type="button" id="%s" onmousedown="kaithemapi.sendValue('%s','pushed')" onmouseleave="kaithemapi.sendValue('%s','released')" onmouseup="kaithemapi.sendValue('%s','released')">%s</button>
             """ % (
                self.isWritable(),
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                content,
            )

        if type == "trigger":
            return """
            <div class="widgetcontainer">
            <script type="text/javascript">
            function %s_toggle()
            {
                if(!document.getElementById("%s_2").disabled)
                {
                    isarmed_%s = false;
                    document.getElementById("%s_1").innerHTML="ARM";
                    document.getElementById("%s_2").disabled=true;
                    document.getElementById("%s_3").style='';

                }
                else
                {
                    document.getElementById("%s_1").innerHTML="DISARM";
                    document.getElementById("%s_2").disabled=false;
                    document.getElementById("%s_3").style='background-color:red;';
                }
            }



            </script>
            <button type="button" id="%s_1" onmousedown="%s_toggle()">ARM</button><br/>
            <button type="button" class="triggerbuttonwidget" disabled=true id="%s_2" onmousedown="kaithemapi.setValue('%s','pushed')" onmouseleave="kaithemapi.setValue('%s','released')" onmouseup="kaithemapi.setValue('%s','released')" %s>
            <span id="%s_3">%s</span>
            </button>
            </div>
             """ % (
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.uuid,
                self.isWritable(),
                self.uuid,
                content,
            )

        raise RuntimeError("Invalid Button Type")


class Slider(Widget):
    def __init__(self, min=0, max=100, step=0.1, *args, **kwargs):
        self.min = min
        self.max = max
        self.step = step
        Widget.__init__(self, *args, **kwargs)
        self.value = 0

    def write(self, value):
        self.value = util.roundto(float(value), self.step)
        # Is this the right behavior?
        self._callback("__SERVER__", value)

    def render(self, type="realtime", orient="vertical", unit="", label=""):
        if orient == "vertical":
            orient = 'class="verticalslider" orient="vertical"'
        else:
            orient = 'class="horizontalslider"'
        if type == "debug":
            return {
                "htmlid": mkid(),
                "id": self.uuid,
                "min": self.min,
                "step": self.step,
                "max": self.max,
                "value": self.value,
                "unit": unit,
            }
        elif type == "realtime":
            return """<div class="widgetcontainer sliderwidget" ontouchmove = function(e) {e.preventDefault()};>
            <b><p>%(label)s</p></b>
            <input %(en)s type="range" value="%(value)f" id="%(htmlid)s" min="%(min)f" max="%(max)f" step="%(step)f"
            %(orient)s
            onchange="kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));"
            oninput="
            %(htmlid)s_clean=%(htmlid)s_cleannext=false;
            kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));
            document.getElementById('%(htmlid)s_l').innerHTML= document.getElementById('%(htmlid)s').value+'%(unit)s';
            setTimeout(function(){%(htmlid)s_cleannext=true},150);"
            ><br>
            <span
            class="numericpv"
            id="%(htmlid)s_l">%(value)g%(unit)s</span>
            <script type="text/javascript">
            %(htmlid)s_clean =%(htmlid)s_cleannext= true;
            var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)s').value= val;
            document.getElementById('%(htmlid)s_l').innerHTML= (Math.round(val*1000)/1000).toPrecision(5).replace(/\.?0*$$/, "")+"%(unit)s";
            }
            %(htmlid)s_clean =%(htmlid)s_cleannext;
            }

            kaithemapi.subscribe("%(id)s",upd);
            </script>

            </div>""" % {
                "label": label,
                "orient": orient,
                "en": self.isWritable(),
                "htmlid": mkid(),
                "id": self.uuid,
                "min": self.min,
                "step": self.step,
                "max": self.max,
                "value": self.value,
                "unit": unit,
            }

        elif type == "onrelease":
            return """<div class="widgetcontainer sliderwidget">
            <b><p">%(label)s</p></b>
            <input %(en)s type="range" value="%(value)f" id="%(htmlid)s" min="%(min)f" max="%(max)f" step="%(step)f"
            %(orient)s
            oninput="document.getElementById('%(htmlid)s_l').innerHTML= document.getElementById('%(htmlid)s').value+'%(unit)s'; document.getElementById('%(htmlid)s').lastmoved=(new Date).getTime();"
            onmouseup="kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            onmousedown="document.getElementById('%(htmlid)s').jsmodifiable = false;"
            onkeyup="kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            ontouchend="kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            ontouchstart="document.getElementById('%(htmlid)s').jsmodifiable = false;"
            ontouchleave="kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"


            ><br>
            <span class="numericpv" id="%(htmlid)s_l">%(value)f%(unit)s</span>
            <script type="text/javascript">
            var upd=function(val){

                if(document.getElementById('%(htmlid)s').jsmodifiable & ((new Date).getTime()-document.getElementById('%(htmlid)s').lastmoved > 300))
                {
                document.getElementById('%(htmlid)s').value= val;
                document.getElementById('%(htmlid)s_l').innerHTML= val+"%(unit)s";
                }


            }
            document.getElementById('%(htmlid)s').lastmoved=(new Date).getTime();
            document.getElementById('%(htmlid)s').jsmodifiable = true;
            kaithemapi.subscribe("%(id)s",upd);
            </script>
            </div>""" % {
                "label": label,
                "orient": orient,
                "en": self.isWritable(),
                "htmlid": mkid(),
                "id": self.uuid,
                "min": self.min,
                "step": self.step,
                "max": self.max,
                "value": self.value,
                "unit": unit,
            }
        raise ValueError("Invalid slider type:" % str(type))


class Switch(Widget):
    def __init__(self, *args, **kwargs):
        Widget.__init__(self, *args, **kwargs)
        self.value = False

    def write(self, value):
        self.value = bool(value)
        # Is this the right behavior?
        self._callback("__SERVER__", value)

    def render(self, label):
        if self.value:
            x = "checked=1"
        else:
            x = ""

        return """<div class="widgetcontainer">
        <label><input %(en)s id="%(htmlid)s" type="checkbox"
        onchange="
        %(htmlid)s_clean = %(htmlid)s_cleannext= false;
        setTimeout(function(){%(htmlid)s_cleannext = true},350);
        kaithemapi.setValue('%(id)s',document.getElementById('%(htmlid)s').checked)" %(x)s>%(label)s</label>
        <script type="text/javascript">
        %(htmlid)s_clean=%(htmlid)s_cleannext = true;
        var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)s').checked= val;
            }
            %(htmlid)s_clean=%(htmlid)s_cleannext;

        }
        kaithemapi.subscribe("%(id)s",upd);
        </script>
        </div>""" % {
            "en": self.isWritable(),
            "htmlid": mkid(),
            "id": self.uuid,
            "x": x,
            "value": self.value,
            "label": label,
        }


class TagPoint(Widget):
    def __init__(self, tag):
        Widget.__init__(self)
        self.tag = tag

    def write(self, value):
        self.value = bool(value)
        # Is this the right behavior?
        self._callback("__SERVER__", value)

    def render(self, label):
        if self.value:
            x = "checked=1"
        else:
            x = ""
        if type == "realtime":
            sl = """<div class="widgetcontainer sliderwidget" ontouchmove = function(e) {e.preventDefault()};>
            <b><p>%(label)s</p></b>
            <input %(en)s type="range" value="%(value)f" id="%(htmlid)s" min="%(min)f" max="%(max)f" step="%(step)f"
            oninput="
            %(htmlid)s_clean=%(htmlid)s_cleannext=false;
            kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));
            document.getElementById('%(htmlid)s_l').innerHTML= document.getElementById('%(htmlid)s').value+'%(unit)s';
            setTimeout(function(){%(htmlid)s_cleannext=true},150);"
            ><br>
            <span
            class="numericpv"
            id="%(htmlid)s_l">%(value)f%(unit)s</span>
            <script type="text/javascript">
            %(htmlid)s_clean =%(htmlid)s_cleannext= true;
            var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)s').value= val;
            document.getElementById('%(htmlid)s_l').innerHTML= (Math.round(val*1000)/1000)+"%(unit)s";
            }
            %(htmlid)s_clean =%(htmlid)s_cleannext;
           }

           kaithemapi.subscribe("%(id)s",upd);
           </script>

            </div>""" % {
                "label": label,
                "en": self.isWritable(),
                "htmlid": mkid(),
                "id": self.uuid,
                "min": self.tag.min,
                "step": self.step,
                "max": self.tag.max,
                "value": self.value,
                "unit": self.unit,
            }

        if type == "onrelease":
            sl = """<div class="widgetcontainer sliderwidget">
            <b><p">%(label)s</p></b>
            <input %(en)s type="range" value="%(value)f" id="%(htmlid)s" min="%(min)f" max="%(max)f" step="%(step)f"
            oninput="document.getElementById('%(htmlid)s_l').innerHTML= document.getElementById('%(htmlid)s').value+'%(unit)s'; document.getElementById('%(htmlid)s').lastmoved=(new Date).getTime();"
            onmouseup="kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            onmousedown="document.getElementById('%(htmlid)s').jsmodifiable = false;"
            onkeyup="kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            ontouchend="kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"
            ontouchstart="document.getElementById('%(htmlid)s').jsmodifiable = false;"
            ontouchleave="kaithemapi.setValue('%(id)s',parseFloat(document.getElementById('%(htmlid)s').value));document.getElementById('%(htmlid)s').jsmodifiable = true;"


            ><br>
            <span class="numericpv" id="%(htmlid)s_l">%(value)f%(unit)s</span>
            <script type="text/javascript">
            var upd=function(val){

                if(document.getElementById('%(htmlid)s').jsmodifiable & ((new Date).getTime()-document.getElementById('%(htmlid)s').lastmoved > 300))
                {
                document.getElementById('%(htmlid)s').value= val;
                document.getElementById('%(htmlid)s_l').innerHTML= val+"%(unit)s";
                }


            }
            document.getElementById('%(htmlid)s').lastmoved=(new Date).getTime();
            document.getElementById('%(htmlid)s').jsmodifiable = true;
            kaithemapi.subscribe("%(id)s",upd);
            </script>
            </div>""" % {
                "label": label,
                "en": self.isWritable(),
                "htmlid": mkid(),
                "id": self.uuid,
                "min": self.min,
                "step": self.step,
                "max": self.max,
                "value": self.value,
                "unit": unit,
            }

        return (
            """<div class="widgetcontainer">"""
            + sl
            + """


        <label><input %(en)s id="%(htmlid)sman" type="checkbox"
        onchange="
        %(htmlid)s_clean = %(htmlid)s_cleannext= false;
        setTimeout(function(){%(htmlid)s_cleannext = true},350);
        kaithemapi.setValue('%(id)s',(document.getElementById('%(htmlid)sman').checked))" %(x)s>Manual</label>
        <script type="text/javascript">
        %(htmlid)s_clean=%(htmlid)s_cleannext = true;
        var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)sman').checked= val;
            }
            %(htmlid)s_clean=%(htmlid)s_cleannext;

        }
        kaithemapi.subscribe("%(id)s",upd);
        </script>
        </div>"""
            % {
                "en": self.isWritable(),
                "htmlid": mkid(),
                "id": self.uuid,
                "x": x,
                "value": self.value,
                "label": label,
            }
        )


class TextBox(Widget):
    def __init__(self, *args, **kwargs):
        Widget.__init__(self, *args, **kwargs)
        self.value = ""

    def write(self, value):
        self.value = str(value)
        # Is this the right behavior?
        self._callback("__SERVER__", value)

    def render(self, label):
        if self.value:
            x = "checked=1"
        else:
            x = ""

        return """<div class="widgetcontainer">
        <label>%(label)s<input %(en)s id="%(htmlid)s" type="text"
        onblur="%(htmlid)s_clean= true;"
        onfocus=" %(htmlid)s_clean = false;"
        oninput="
        kaithemapi.setValue('%(id)s',document.getElementById('%(htmlid)s').value)
        "
                ></label>
        <script type="text/javascript">
 %(htmlid)s_clean = true;
        var upd=function(val){
            if(%(htmlid)s_clean)
            {
            document.getElementById('%(htmlid)s').value= val;
            }
        }
        kaithemapi.subscribe("%(id)s",upd);
        </script>
        </div>""" % {
            "en": self.isWritable(),
            "htmlid": mkid(),
            "id": self.uuid,
            "x": x,
            "value": self.value,
            "label": label,
        }


class ScrollingWindow(Widget):
    """A widget used for chatroom style scrolling text.
    Only the new changes are ever pushed over the net. To use, just write the HTML to it, it will
    go into a nev div in the log, old entries automatically go away, use the length param to decide
    how many to keep"""

    def __init__(self, length=250, *args, **kwargs):
        Widget.__init__(self, *args, **kwargs)
        self.value = []
        self.maxlen = length
        self.lock = threading.Lock()

    def write(self, value):
        with self.lock:
            self.value.append(str(value))
            self.value = self.value[-self.maxlen :]
            self.send(value)
            self._callback("__SERVER__", value)

    def render(self, cssclass="", style=""):
        content = "".join(["<div>" + i + "</div>" for i in self.value])

        return """<div class="widgetcontainer" style="display:block;width:90%%;">
        <div id=%(htmlid)s class ="scrollbox %(cssclass)s" style="%(style)s">
        %(content)s
        </div>
        <script type="text/javascript">
        var d=document.getElementById('%(htmlid)s');
        d.scrollTop = d.scrollHeight;
        var upd=function(val){
            var d=document.getElementById('%(htmlid)s');

            //Detect end of scroll, so we can keep it there if that's where we are at
            var isscrolled =d.scrollTop+d.clientHeight+35 >= d.scrollHeight;

            if (d.childNodes.length>%(maxlen)d)
            {
                d.removeChild(d.childNodes[0])
            }
            var n = document.createElement("div");
            n.innerHTML= val;
            d.appendChild(n);
            //Scroll to bottom if user was already there.
            if (isscrolled)
            {
                d.scrollTop = d.scrollHeight;
            }
        }
        kaithemapi.subscribe("%(id)s",upd);
        </script>
        </div>""" % {
            "htmlid": mkid(),
            "maxlen": self.maxlen,
            "content": content,
            "cssclass": cssclass,
            "style": style,
            "id": self.uuid,
        }


class APIWidget(Widget):
    def __init__(self, echo=True, *args, **kwargs):
        Widget.__init__(self, *args, **kwargs)
        self.value = None
        self.echo = echo

    def write(self, value, push=True):
        # Don't set the value, because we don't have a value just a pipe of messages
        # self.value = value
        self.doCallback("__SERVER__", value, "__SERVER__")
        if push:
            self.send(value)

    def render(self, htmlid):
        return """
            <script>
                %(htmlid)s = {};
                %(htmlid)s.value = "Waiting..."
                %(htmlid)s.clean = 0;
                %(htmlid)s._maxsyncdelay = 250
                %(htmlid)s.timeSyncInterval = 120*1000;

                %(htmlid)s._timeref = [performance.now()-1000000,%(loadtime)f-1000000]
                var onTimeResponse = function (val)
                {
                    if(Math.abs(val[0]-%(htmlid)s._txtime)<0.1)
                        {
                            var t = performance.now();
                            if(t-%(htmlid)s._txtime<%(htmlid)s._maxsyncdelay)
                                {
                            %(htmlid)s._timeref = [(t+%(htmlid)s._txtime)/2, val[1]]

                            %(htmlid)s._maxsyncdelay = (t-%(htmlid)s._txtime)*1.2;
                            }
                            else
                                {

                                    %(htmlid)s._maxsyncdelay= %(htmlid)s._maxsyncdelay*2;
                                }
                        }
                }

                var _upd = function(val)
                    {
                        if (%(htmlid)s.clean==0)
                            {
                                 %(htmlid)s.value = val;
                            }
                        else
                            {
                                %(htmlid)s.clean -=1;
                            }
                        %(htmlid)s.upd(val)
                    }

                %(htmlid)s.upd = function(val)
                        {
                        }
                %(htmlid)s.getTime = function()
                    {
                        var x = performance.now()
                        %(htmlid)s._txtime =x;
                        kaithemapi.sendValue("_ws_timesync_channel",x)
                    }


                %(htmlid)s.now = function(val)
                        {
                            var t=performance.now()
                            if(t-%(htmlid)s._txtime>%(htmlid)s.timeSyncInterval)
                                {
                                    %(htmlid)s.getTime();
                                }
                            return((t-%(htmlid)s._timeref[0])+%(htmlid)s._timeref[1])
                        }

                %(htmlid)s.set = function(val)
                    {
                         kaithemapi.setValue("%(id)s", val);
                         %(htmlid)s.clean = 2;
                    }

                %(htmlid)s.send = function(val)
                    {
                         kaithemapi.sendValue("%(id)s", val);
                         %(htmlid)s.clean = 2;
                    }

                    kaithemapi.subscribe("_ws_timesync_channel",onTimeResponse)
                    kaithemapi.subscribe("%(id)s",_upd);
                    setTimeout(%(htmlid)s.getTime,500)
            </script>
            """ % {
            "htmlid": htmlid,
            "id": self.uuid,
            "value": json.dumps(self.value),
            "loadtime": time.time() * 1000,
        }


t = APIWidget(echo=False, id="_ws_timesync_channel")


def f(s, v, id):
    t.sendTo([v, time.time() * 1000], id)


t.attach2(f)
