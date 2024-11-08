from __future__ import annotations

import logging
import threading
import time
import traceback
import typing
import weakref

from scullery import workers

if typing.TYPE_CHECKING:
    import paho.mqtt.client

import structlog

logger = structlog.get_logger(__name__)

testCrashOnce = False


def checkIfConnected(c, delay):
    time.sleep(delay)
    if not c.is_connected:
        logging.warning(
            "An MQTT connection to : "
            + str(c.name)
            + " was not connected after "
            + str(delay)
            + " seconds of waiting"
        )


def waitConnected(c):
    for i in range(100):
        if c.is_connected:
            return
        time.sleep(0.01)


def makeThread(c, ref):
    def f2():
        global testCrashOnce
        try:
            if testCrashOnce:
                testCrashOnce = False
                raise RuntimeError("Test crash once")
            c.loop_forever(retry_first_connection=True)
        except Exception:
            if ref():
                ref().on_connection_crash(traceback.format_exc())
                logger.exception("MQTT Crash")

    return f2


def getWeakrefHandlers(self):
    self = weakref.ref(self)

    def on_connect(client, userdata=None, flags=None, rc=0, *a):
        obj = self()
        if not obj:
            return

        try:
            if not rc == 0:
                obj.on_disconnect()
                return
            obj.on_connect()

            logger.info(
                "Connected to MQTT server: "
                + obj.name
                + "result code "
                + str(rc)
            )
            # Don't block the network thread too long

            def subscriptionRefresh():
                try:
                    for i in obj.subscriptions:
                        obj.connection.subscribe(i[1], 0)
                except Exception:
                    logger.exception("Error subscription refresh")

            workers.do(subscriptionRefresh)
        except Exception:
            logging.exception("MQTT")

    def on_disconnect(client, *a):
        obj = self()
        if not obj:
            return

        try:
            if not obj:
                return
            logger.info("Disconnected from MQTT server: " + obj.name)
            obj.on_disconnect()
            logger.info("Disconnected from MQTT server: " + obj.name)
        except Exception:
            logging.exception("MQTT")

    def on_message(client, userdata, msg):
        try:
            s = self()
            if s:
                # Everything must be fine, because we are getting messages
                s.on_message(msg.topic, msg.payload)
        except Exception:
            logging.exception("MQTT")

    return on_connect, on_disconnect, on_message


class MQTTConnection:
    def __init__(self, host, port, username=None, password=None) -> None:
        import paho.mqtt.client as mqtt

        # Ok so the connection is supposed to do this by itself. Some condition can
        # Cause the loop to crash and I do not know what!
        self.subscriptions = []

        # We want to track this so we do not double subscribe.
        self.successful_subscriptions = []

        self.lock = threading.RLock()

        self.is_connected = False

        self.connection: None | paho.mqtt.client.Client = None

        self._thread: None | threading.Thread = None

        x = host.split("@")
        if len(x) == 2:
            host = x[1]
            assert not username
            username = x[0]

        name = host + ":" + str(port)
        self.name = name

        def reconnect():
            try:
                if self.connection:
                    self.connection.disconnect()
            except Exception:
                pass

            try:
                self.connection = mqtt.Client()
            except TypeError:
                self.connection = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)

            # We don't want the connection to strongly reference us, that would interfere with GC
            on_connect, on_disconnect, on_message = getWeakrefHandlers(self)

            # if self.username:
            #     self.username_pw_set(self.username, self.password)

            self.connection.connect_async(
                host, port=port, keepalive=10, bind_address=""
            )

            self.connection.on_connect = on_connect
            self.connection.on_disconnect = on_disconnect
            self.connection.on_message = on_message

            self._thread = threading.Thread(
                target=makeThread(self.connection, weakref.ref(self)),
                name=name,
                daemon=True,
            )
            self._thread.start()

        self.reconnect = reconnect

        # Actually do the connection.
        self.reconnect()

        # Give it 5 mins before we print a warning.
        def f():
            checkIfConnected(self, 5)

        workers.do(f)

        # Block so the rest of the code doesn't do nuisance warnings
        # and stuff working on a not yet connected thing.
        waitConnected(self)

    def subscribe(self, t):
        with self.lock:
            if t in self.successful_subscriptions:
                return
            # Atomic.  Also add to list happens before subscribe because of race if not connected
            self.subscriptions = list(self.subscriptions) + [t]
            try:
                assert self.connection
                self.connection.subscribe(t, 0)
                self.successful_subscriptions.append(t)
            except Exception:
                logger.exception(
                    "Could not subscribe to MQTT message but can retry later"
                )

    def on_message(self, t, m):
        pass

    def on_connect(self):
        self.is_connected = True

    def on_disconnect(self):
        self.is_connected = False

    def publish(self, topic, message):
        try:
            assert self.connection
            self.connection.publish(
                topic,
                payload=message,
                qos=0,
                retain=False,
            )
        except Exception:
            logging.exception("Err in MQTT")

    def disconnect(self):
        try:
            if self.connection:
                self.connection.disconnect()
        except Exception:
            logging.exception("Err in MQTT")

    def close(self):
        self.disconnect()

    def __del__(self):
        print("Deleting MQTT Connection", self.name)
        logging.warning("MQTT Connection closed automatically: " + self.name)
        self.close()

    def unsubscribe(self, topic):
        with self.lock:
            try:
                self.subscriptions.remove(topic)
                if self.connection:
                    self.connection.unsubscribe(topic)
                self.successful_subscriptions.remove(topic)
            except Exception:
                logging.exception("Err in MQTT")
