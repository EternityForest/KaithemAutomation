# SPDX-FileCopyrightText: Copyright 2014 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


# Long lines, legacy stuff rarely touched...
# ruff: noqa

from __future__ import annotations

import base64
import collections
import copy
import json
import logging, structlog, asyncio
import os
import threading
import time
import traceback
import weakref
import asyncio
from collections.abc import Callable
from typing import Optional, Any
from starlette.requests import Request
from quart.ctx import copy_current_request_context
import msgpack
from beartype import beartype

from . import auth, messagebus, pages, workers
from http.cookies import SimpleCookie

logger = structlog.get_logger(__name__)

# Modify lock for any websocket's subscriptions
subscriptionLock = threading.Lock()
widgets: weakref.WeakValueDictionary[str | int, Widget] = (
    weakref.WeakValueDictionary()
)
n = 0

# We can keep track of how many. If more than 10, we stop making new ones for every
# connection.
wsrunners: weakref.WeakValueDictionary[int, WSActionRunner] = (
    weakref.WeakValueDictionary()
)


class WSActionRunner:
    """Class for running actions in a separate thread under a lock"""

    def __init__(self) -> None:
        self.wsActionSerializer = threading.Lock()
        self.wsActionQueue: list[Callable[[], Any]] = []
        wsrunners[id(self)] = self

    # We must serialize  actions to avoid out of order,
    # but for performance we really need to do them in the background
    def dowsAction(self, g: Callable[[], Any]) -> None:
        if len(self.wsActionQueue) > 10:
            time.sleep(0.1)

            if len(self.wsActionQueue) > 25:
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
                else:
                    pass

        workers.do(f)


# All guests share a runner, logged in users get their own per-connection
guestWSRunner = WSActionRunner()


def eventErrorHandler(f: Callable[[], Any]):
    # If we can, try to send the exception back whence it came
    try:
        from .plugins import CorePluginEventResources

        if f.__module__ in CorePluginEventResources.eventsByModuleName:
            CorePluginEventResources.eventsByModuleName[
                f.__module__
            ].handle_exception()
    except Exception:
        print(traceback.format_exc())


default_display_units = {
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
    def __init__(
        self, user: str, cookie: Optional[SimpleCookie] = None
    ) -> None:
        self.user = user
        self.cookie = cookie


lastLoggedUserError = 0

lastPrintedUserError = 0


def subsc_closure(self: WebSocketHandler, widgetid: str, widget: Widget):
    def f(msg: bytes | str, raw: Any = None):
        try:
            self.send(msg)
        except OSError:
            # These happen sometimes when things are disconnecting it seems,
            # And there's no need to waste log space or send a notification.
            pass
        except Exception:
            if not widget.errored_send:
                widget.errored_send = True
                messagebus.post_message(
                    "/system/notifications/errors",
                    "Problem in widget " + repr(widget) + ", see logs",
                )
                logger.exception(
                    "Error sending data from widget "
                    + repr(widget)
                    + " via websocket"
                )
            else:
                logger.exception("Error sending data from websocket")

    return f


def raw_subsc_closure(
    self: RawWidgetDataHandler, widgetid: str, widget: Widget
):
    def f(msg: Any, raw: Any):
        try:
            if isinstance(raw, bytes):
                self.send(raw)
            else:
                self.send(json.dumps(raw))

        except OSError as e:
            if e.errno == 32:
                self.closeUnderLock()
            # These happen sometimes when things are disconnecting it seems,
            # And there's no need to waste log space or send a notification.
            print("wtimeout", traceback.format_exc())
        except Exception:
            if not widget.errored_send:
                widget.errored_send = True
                messagebus.post_message(
                    "/system/notifications/errors",
                    "Problem in widget " + repr(widget) + ", see logs",
                )
                logger.exception(
                    "Error sending data from widget "
                    + repr(widget)
                    + " via websocket"
                )
            else:
                logger.exception("Error sending data from websocket")

    return f


clients_info = weakref.WeakValueDictionary()

ws_connections: weakref.WeakValueDictionary[
    str, WebSocketHandler | RawWidgetDataHandler
] = weakref.WeakValueDictionary()


def get_connectionRefForID(
    id: str,
    deleteCallback: Callable[
        [weakref.ref[WebSocketHandler | RawWidgetDataHandler]], None
    ]
    | None = None,
):
    try:
        return weakref.ref(ws_connections[id], deleteCallback)
    except KeyError:
        return None


# Message, start time, duration
lastGlobalAlertMessage = ["", 0, 0]


def send_toAll(d):
    d = json.dumps(d)
    x = {}

    # Retry against the dict changed size during iteration thing
    for i in range(50):
        try:
            for j in ws_connections:
                if j not in x:
                    ws_connections[j].send(d)
                    x[j] = True
            break
        except Exception:
            logger.exception("Error in global broadcast")


def sendGlobalAlert(msg: str, duration=60.0):
    lastGlobalAlertMessage[0] = msg
    lastGlobalAlertMessage[1] = time.monotonic()
    lastGlobalAlertMessage[2] = duration

    send_toAll([["__SHOWSNACKBAR__", [msg, float(duration)]]])


def send_to(topic: str, value: Any, target: str):
    "Send a value to one subscriber by the connection ID"
    d = msgpack.packb([[topic, value]])

    if len(d) > 32 * 1024 * 1024:
        raise ValueError("Data is too large, refusing to send")
    ws_connections[target].send(d)


userBatteryAlerts = {}


class WebSocketHandler:
    def __init__(
        self, parent: WebSocket, user: str, loop: asyncio.AbstractEventLoop
    ) -> None:
        self.subscriptions: list[str] = []
        self.lastPushedNewData = 0
        self.connection_id = (
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
        self.peer_address = ""
        self.batteryStatus = None
        self.cookie = dict[str, Any] | None

        self.loop = loop

        ws_connections[self.connection_id] = self
        messagebus.subscribe(
            "/system/permissions/rmfromuser", self.onPermissionRemoved
        )

        self.pageURL = "UNKNOWN"

        self.usedPermissions = collections.defaultdict(int)

        if auth.getUserSetting(self.user, "telemetry-alerts"):
            from . import alerts

            if self.user not in userBatteryAlerts:
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

    def onPermissionRemoved(self, t: str, v):
        "Close the socket if the user no longer has the permission"
        if v[0] == self.user and v[1] in self.usedPermissions:
            self.closeUnderLock()

    def send(self, b: bytes | str):
        with self.widget_wslock:

            async def f():
                if isinstance(b, str):
                    await self.parent.send_text(b)
                else:
                    await self.parent.send_bytes(b)

            asyncio.run_coroutine_threadsafe(f(), self.loop)

    def close(self, *a: Any) -> None:
        with subscriptionLock:
            while self.subscriptions:
                i = self.subscriptions.pop(0)
                try:
                    widgets[i].subscriptions.pop(self.connection_id)
                    widgets[i].subscriptions_atomic = widgets[
                        i
                    ].subscriptions.copy()
                    widgets[i].on_subscriber_disconnected(
                        self.user, self.connection_id
                    )
                except Exception:
                    pass

    def closeUnderLock(self):
        def f():
            with self.widget_wslock:
                self.close()

    def received_message(self, message: bytes | str, asgi):
        global lastLoggedUserError
        global lastPrintedUserError
        try:
            d = message

            if isinstance(d, bytes):
                o = msgpack.unpackb(d, raw=False)
            else:
                o = json.loads(d)

            user = self.user

            upd = o["upd"]
            for i in upd:
                if i[0] in widgets:
                    widgets[i[0]]._on_update(
                        user, i[1], self.connection_id, asgi
                    )
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
                        except Exception:
                            logger.exception(
                                "Error in battery status telemetry"
                            )

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
                        if lastGlobalAlertMessage[0] and lastGlobalAlertMessage[
                            1
                        ] > (time.monotonic() - lastGlobalAlertMessage[2]):
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
                                if not pages.canUserDoThis(
                                    p, user, self.asgiscope
                                ):
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
                                    raise PermissionError(
                                        user + " missing permission: " + str(p)
                                    )
                                self.usedPermissions[p] += 1

                            widgets[i].subscriptions[self.connection_id] = (
                                subsc_closure(self, i, widgets[i])
                            )
                            widgets[i].subscriptions_atomic = widgets[
                                i
                            ].subscriptions.copy()

                            self.subscriptions.append(i)
                            if not widgets[i].noOnConnectData:
                                x = widgets[i]._on_request(
                                    user, self.connection_id, asgi
                                )
                                if x is not None:
                                    widgets[i].send(x)
                            self.subCount += 1

                            # This comes after in case it  sends data
                            widgets[i].on_new_subscriber(
                                user, self.connection_id
                            )
                        else:
                            pass
            if "unsub" in o:
                for i in o["unsub"]:
                    if i not in self.subscriptions:
                        continue

                    # TODO: DoS by filling memory with subscriptions??
                    with subscriptionLock:
                        if i in widgets:
                            if widgets[i].subscriptions.pop(
                                self.connection_id, None
                            ):
                                self.subCount -= 1

                                for p in widgets[i].permissions:
                                    self.usedPermissions[p] -= 1
                                    if self.usedPermissions[p] == 0:
                                        del self.usedPermissions[p]
                            widgets[i].subscriptions_atomic = widgets[
                                i
                            ].subscriptions.copy()

        # Permissionerrors are too common to do the full logging thing
        except PermissionError as e:
            self.send(json.dumps({"__WIDGETERROR__": repr(e)}))

        except Exception as e:
            logger.exception("Error in widget, responding to " + str(d))
            messagebus.post_message(
                "system/errors/widgets/websocket", traceback.format_exc(6)
            )
            self.send(json.dumps({"__WIDGETERROR__": repr(e)}))


from starlette.websockets import WebSocket


class RawWidgetDataHandler:
    def __init__(self, parent, user, loop, widgetName: str, asgiscope) -> None:
        self.subscriptions: list[str] = []
        self.lastPushedNewData = 0
        self.connection_id = (
            "id"
            + base64.b64encode(os.urandom(16))
            .decode()
            .replace("/", "")
            .replace("-", "")
            .replace("+", "")[:-2]
        )
        self.widget_wslock = threading.Lock()
        self.subCount = 0
        ws_connections[self.connection_id] = self
        messagebus.subscribe(
            "/system/permissions/rmfromuser", self.onPermissionRemoved
        )
        self.user = user
        self.parent = parent
        self.peer_address = ""

        self.usedPermissions = collections.defaultdict(int)
        self.loop = loop
        self.asgi = asgiscope
        self.batteryStatus = None

        assert isinstance(widgetName, str)
        with subscriptionLock:
            if widgetName in widgets:
                for p in widgets[widgetName]._read_perms:
                    if not pages.canUserDoThis(p, self.user, asgi=self.asgi):
                        raise RuntimeError(
                            self.user + " missing permission: " + str(p)
                        )
                    self.usedPermissions[p] += 1

                widgets[widgetName].subscriptions[self.connection_id] = (
                    raw_subsc_closure(self, widgetName, widgets[widgetName])
                )
                widgets[widgetName].subscriptions_atomic = widgets[
                    widgetName
                ].subscriptions.copy()

                self.subscriptions.append(widgetName)
                self.subCount += 1

                # This comes after in case it  sends data
                widgets[widgetName].on_new_subscriber(self.user, {})

    def onPermissionRemoved(self, t, v):
        "Close the socket if the user no longer has the permission"
        if v[0] == self.user and v[1] in self.usedPermissions:
            self.closeUnderLock()

    def closeUnderLock(self):
        def f():
            with self.widget_wslock:
                self.close()

        workers.do(f)

    def send(self, b: bytes | str):
        with self.widget_wslock:

            async def f():
                if isinstance(b, str):
                    await self.parent.send_text(b)
                else:
                    await self.parent.send_bytes(b)

            asyncio.run_coroutine_threadsafe(f(), self.loop)

    def close(self, *a):
        with subscriptionLock:
            while self.subscriptions:
                i = self.subscriptions.pop(0)
                try:
                    widgets[i].subscriptions.pop(self.uuid)
                    widgets[i].subscriptions_atomic = widgets[
                        i
                    ].subscriptions.copy()
                except Exception:
                    pass


def makeclosure(f, i, scope):
    def g():
        return f(i, scope)

    return g


async def app(scope, receive, send):
    websocket = WebSocket(scope=scope, receive=receive, send=send)
    await websocket.accept()
    io_loop = asyncio.get_running_loop()

    def f():
        try:
            user_agent = scope.headers["User-Agent"]
        except Exception:
            user_agent = ""
        x = scope["client"][0]

        if scope["scheme"] == "wss" or pages.isHTTPAllowed(x):
            user = pages.getAcessingUser(asgi=scope)
            cookie = scope.get("cookie", None)
        else:
            cookie = None
            user = "__guest__"

        impl: WebSocketHandler = WebSocketHandler(websocket, user, io_loop)
        impl.cookie = cookie
        impl.user_agent = user_agent
        impl.asgiscope = scope

        impl.clientinfo = ClientInfo(impl.user, impl.cookie)
        clients_info[impl.connection_id] = impl.clientinfo

        assert isinstance(x, str)
        impl.peer_address = x

        if (
            user == "__guest__"
            and (not x.startswith("127."))
            and (len(wsrunners) > 8)
        ):
            runner = guestWSRunner
        else:
            runner = WSActionRunner()

        return impl, runner

    impl, runner = await asyncio.to_thread(f)

    while 1:
        try:
            x = await websocket.receive()
        except Exception:
            break

        if "text" in x:
            i = x["text"]
        elif "bytes" in x:
            i = x["bytes"]
        else:
            continue

        f = makeclosure(impl.received_message, i, scope)
        runner.dowsAction(f)


async def rawapp(scope, receive, send):
    websocket = WebSocket(scope=scope, receive=receive, send=send)
    await websocket.accept()

    try:
        user_agent = scope.headers["User-Agent"]
    except Exception:
        user_agent = ""
    x = scope["client"][0]

    if scope["scheme"] == "wss" or pages.isHTTPAllowed(x):
        user = pages.getAcessingUser(asgi=scope)
        cookie = scope.get("cookie", None)
    else:
        cookie = None
        user = "__guest__"

    io_loop = asyncio.get_running_loop()
    impl = RawWidgetDataHandler(
        websocket, user, io_loop, websocket.query_params["widgetid"], scope
    )
    impl.cookie = cookie
    impl.user_agent = user_agent

    impl.clientinfo = ClientInfo(impl.user, impl.cookie)
    clients_info[impl.connection_id] = impl.clientinfo

    assert isinstance(x, str)
    impl.peer_address = x

    if (
        user == "__guest__"
        and (not x.startswith("127."))
        and (len(wsrunners) > 8)
    ):
        runner = guestWSRunner
    else:
        runner = WSActionRunner()

    while 1:
        try:
            x = await websocket.receive()
        except Exception:
            break

        if "text" in x:
            i = x["text"]
        elif "bytes" in x:
            i = x["bytes"]
        else:
            continue
        # runner.dowsAction(lambda: impl.received_message(i))


def randID() -> str:
    "Generate a base64 id"
    return (
        base64.b64encode(os.urandom(8))[:-1]
        .decode()
        .replace("+", "")
        .replace("/", "")
        .replace("-", "")
    )


idlock = threading.RLock()


class Widget:
    def __init__(self, *args, **kwargs) -> None:
        self.value = None
        self._read_perms: list[str] = []
        self._write_perms: list[str] = []
        self.errored_function = None
        self.errored_getter = None
        self.errored_send = False
        self.subscriptions: dict[str, Callable[[Any, Any], None]] = {}
        self.subscriptions_atomic: dict[str, Callable[[Any, Any], None]] = {}
        self.echo: bool = True
        self.noOnConnectData: bool = False

        self.uuid: int | str

        self.metadata: dict[str, str | int | float | bool] = {}

        def f(u: str, v: Any):
            pass

        def f2(u: str, v: Any, id: str):
            pass

        self._callback = f
        self._callback2 = f2

        with idlock:
            # Give the widget an ID for the client to refer to it by
            # Note that it's no longer always a  uuid!!
            if "id" not in kwargs:
                for i in range(250000):
                    self.uuid = randID()
                    if self.uuid not in widgets:
                        break
                    if i > 240000:
                        raise RuntimeError("No more IDs?")
            else:
                self.uuid = kwargs["id"]

            # Insert self into the widgets list
            widgets[self.uuid] = self

    def on_new_subscriber(self, user, connection_id, **kw):
        pass

    def on_subscriber_disconnected(
        self, user: str, connection_id: str, **kw: Any
    ) -> None:
        pass

    def forEach(self, callback):
        "For each client currently subscribed, call callback with a clientinfo object"
        for i in self.subscriptions:
            callback(clients_info[i])

    # This function is called by the web interface code
    def _on_request(self, user, uuid, asgi):
        """Widgets on the client side send AJAX requests for the new value.
          This function must
        return the value for the widget. For example a slider might request the
        newest value.

        This function is also responsible for verifying that the user has the right
          permissions

        This function is generally only called by the library.

        This function returns if the user does not have permission

        Args:
            user(string):
                the username of the user who is tring to access things.
        """
        for i in self._read_perms:
            if not pages.canUserDoThis(i, user, asgi=asgi):
                return "PERMISSIONDENIED"
        try:
            return self.on_request(user, uuid)
        except Exception:
            logger.exception("Error in widget request to " + repr(self))
            if not (self.errored_getter == id(self._callback)):
                messagebus.post_message(
                    "/system/notifications/errors",
                    f"Error in widget getter function {self._callback.__name__} defined in module { self._callback.__module__}, see logs for traceback.",
                )
                self.errored_getter = id(self._callback)

    # This function is meant to be overridden or used as is
    def on_request(self, user: str, uuid: int | str):
        """This function is called after permissions have been verified when a client
          requests the current value. Usually just returns self.value

        Args:
            user(string):
                The username of the acessung client
        """
        return self.value

    # This function is called by the web interface whenever this widget is written to
    def _on_update(self, user, value, uuid, asgi):
        """Called internally to write a value to the widget. Responisble for
        verifying permissions. Returns if user does not have permission"""
        for i in self._read_perms:
            if not pages.canUserDoThis(i, user, asgi):
                return

        for i in self._write_perms:
            if not pages.canUserDoThis(i, user, asgi):
                return

        self.on_update(user, value, uuid)

    def doCallback(self, user: str, value: Any, uuid: str):
        "Run the callback, and if said callback fails, post a message about it."
        try:
            self._callback(user, value)
        except Exception as e:
            eventErrorHandler(self._callback)
            logger.exception("Error in widget callback for " + repr(self))
            if not (self.errored_function == id(self._callback)):
                messagebus.post_message(
                    "/system/notifications/errors",
                    f"Error in widget callback function {self._callback.__name__} defined in module { self._callback.__module__}, see logs for traceback.",
                )
                self.errored_function = id(self._callback)
            raise e

        try:
            self._callback2(user, value, uuid)
        except Exception as e:
            logger.exception("Error in widget callback for " + repr(self))
            eventErrorHandler(self._callback2)
            if not (self.errored_function == id(self._callback)):
                messagebus.post_message(
                    "/system/notifications/errors",
                    f"Error in widget callback function {self._callback.__name__} defined in module { self._callback.__module__}, see logs for traceback.",
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
    @beartype
    def attach(self, f: Callable[[str, Any], None]) -> None:
        self._callback = f

    # Set a callback if it ever changes.
    # This version also gives you the connection ID
    @beartype
    def attach2(self, f: Callable[[str, Any, str], None]) -> None:
        self._callback2 = f

    # meant to be overridden or used as is
    def on_update(self, user: str, value: Any, uuid: str):
        self.value = value
        self.doCallback(user, value, uuid)
        if self.echo:
            self.send(value)

    # Read and write are called by code on the server
    def read(self):
        return self.value

    def write(self, value: Any, push=True):
        self.value = value
        self.doCallback("__SERVER__", value, "__SERVER__")
        if push:
            self.send(value)

    def send(self, value: Any) -> None:
        "Send a value to all subscribers without invoking the local callback or setting the value"
        x = self.subscriptions_atomic

        if not x:
            return

        d = msgpack.packb([[self.uuid, value]], use_bin_type=True)

        # Very basic saniy check here
        if len(d) > 32 * 1024 * 1024:
            raise ValueError("Data is too large, refusing to send")

        # Yes, I really had a KeyError here.
        # Somehow the dict was replaced with the new version in the middle of iteration
        # So we use an intermediate value so we know it won't change
        for i in x:
            try:
                x[i](d, value)
            except Exception:
                print("WS Send Error ", traceback.format_exc())

    def __del__(self) -> None:
        try:
            d = json.dumps([[self.uuid]])

            # Yes, I really had a KeyError here.
            # Somehow the dict was replaced with the new version in
            # the middle of iteration
            # So we use an intermediate value so we know it won't change
            x = self.subscriptions_atomic
            for i in x:
                try:
                    x[i](d, None)
                except Exception:
                    print("WS Send Error ", traceback.format_exc())
        except Exception:
            if traceback:
                print(traceback.format_exc())

    def send_to(self, value: Any, target: str):
        "Send a value to one subscriber by the connection ID"
        d = msgpack.packb([[self.uuid, value]])

        if len(d) > 32 * 1024 * 1024:
            raise ValueError("Data is too large, refusing to send")
        if target in self.subscriptions_atomic:
            self.subscriptions_atomic[target](d, value)

    # Lets you add permissions that are required to read or write the widget.
    def require(self, permission: str) -> None:
        self._read_perms.append(permission)

    def require_to_write(self, permission: str) -> None:
        self._write_perms.append(permission)

    def set_permissions(self, read: list[str], write: list[str]) -> None:
        self._read_perms = copy.copy(read)
        self._write_perms = copy.copy(write)


class DataSource(Widget):
    attrs = ""

    def render(self):
        raise RuntimeError(
            "This is not a real widget, you must manually subscribe to this widget's ID and build your own handling for it."
        )


class ScrollingWindow(Widget):
    """A widget used for chatroom style scrolling text.
    Only the new changes are ever pushed over the net.
    To use, just write the HTML to it, it will
    go into a nev div in the log, old entries automatically go away,
    use the length param to decide
    how many to keep"""

    def __init__(self, length: int = 250, *args, **kwargs) -> None:
        Widget.__init__(self, *args, **kwargs)
        self.value = []
        self.maxlen = length
        self.lock = threading.Lock()

    def write(self, value: str) -> None:
        with self.lock:
            self.value.append(str(value))
            self.value = self.value[-self.maxlen :]
            self.send(value)
            self._callback("__SERVER__", value)

    def render(self, cssclass="", style=""):
        content = "".join(["<div>" + i + "</div>" for i in self.value])

        return """<div class="w-full card">
        <div id=%(htmlid)s class ="max-h-12rem scroll border %(cssclass)s" style="%(style)s">
        %(content)s
        </div>
        <script type="module">
        import { kaithemapi } from "/static/js/widget.mjs"
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
            n.className="w-full";
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
    def __init__(self, echo: bool = True, *args, **kwargs) -> None:
        Widget.__init__(self, *args, **kwargs)
        self.value = None
        self.echo = echo

    def write(self, value: Any, push: bool = True):
        # Don't set the value, because we don't have a value just a pipe of messages
        # self.value = value
        self.doCallback("__SERVER__", value, "__SERVER__")
        if push:
            self.send(value)


t = APIWidget(echo=False, id="_ws_timesync_channel")


def f(s: str, v: Any, id: str):
    t.send_to([v, time.time() * 1000], id)


t.attach2(f)
