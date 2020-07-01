# Copyright Daniel Dunn 2019
# This file is part of Scullery.

# Scullery is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Scullery is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Scullery.  If not, see <http://www.gnu.org/licenses/>.

import threading
import weakref
import logging
import time
import uuid
import traceback
import json

from scullery import messagebus, workers, util

try:
    import msgpack
except:
    pass

logger = logging.getLogger("system.mqtt")


connections = {}
lock = threading.RLock()


def getWeakrefHandlers(self):
    self = weakref.ref(self)

    def on_connect(client, userdata, flags, rc):
        logger.info("Connected to MQTT server: "+self().server)
        self().onStillConnected()
        # Don't block the network thread too long

        def subscriptionRefresh():
            with self().lock:
                for i in self().subscriptions:
                    # Refresh all subscriptions
                    self().connection.subscribe(i, self().subscriptions[i])
        workers.do(subscriptionRefresh)

    def on_disconnect(client, userdata, flags, rc):
        logger.info("Disconnected from MQTT server: "+self().server)
        self().onDisconnected()
        logger.info("Disconnected from MQTT server: "+self().server)

    def on_message(client, userdata, msg):
        try:
            s = self()
            # Everything must be fine, because we are getting messages
            messagebus.postMessage(
                "/mqtt/"+s.server+":"+str(s.port)+"/in/"+msg.topic,
                 msg.payload,
                 )
            s.onStillConnected()
        except Exception:
            print(traceback.format_exc())

    return on_connect, on_disconnect, on_message


def makeThread(f):
    def f2():
        f()
    return f2


class Connection():
    def __init__(self, server, port=1883, *, alertPriority="info", alertAck=True):
        self.server = server
        self.port = port
        self.lock = threading.Lock()

        virtual = server.startswith("__virtual__")

        self.subscriptions = {}
        logger.info("Creating connection object to: "+self.server)
        import paho.mqtt.client as mqtt

        # When we wrap a function store a weakref to the original here,
        # Pplus the wrapper, so the wrapper doesn't get GCed till
        # The wearkref callback deletes it.
        self.subscribeWrappers = {}

        with lock:
            n = server+":"+str(port)
            if n in connections and connections[n]():
                raise RuntimeError("There is already a connection")
            torm = []
            for i in connections:
                if not connections[i]():
                    torm.append(i)
            for i in torm:
                del connections[i]
            connections[n] = weakref.ref(self)

            try:

              
                if not virtual:
                    def out_handler(topic, message,timestamp,annotation):
                        self.connection.publish(topic[len(
                            "/mqtt/"+server+":"+str(port)+"/out/"):], payload=message, qos=annotation, retain=False)
                else:
                    #Virtual loopback server doesn't actually use a real server
                    def out_handler(topic, message,timestamp,annotation):
                        t = topic[len("/mqtt/"+server+":"+str(port)+"/out/"):]
                        messagebus.postMessage("/mqtt/"+server+":"+str(port)+"/in/"+t, message)

                messagebus.subscribe(
                    "/mqtt/"+server+":"+str(port)+"/out/#", out_handler)
                

                self.out_handler = out_handler

                if not virtual:
                    self.connection = mqtt.Client()
                    # We don't want the connection to stringly reference us, that would interfere with GC
                    on_connect, on_disconnect, on_message = getWeakrefHandlers(
                        self)
                    self.connection.on_connect = on_connect
                    self.connection.on_disconnect = on_disconnect
                    self.connection.on_message = on_message

                    self.connection.connect_async(
                        server, port=port, keepalive=60, bind_address="")

                    self._thread = threading.Thread(target=makeThread(
                        self.connection.loop_forever), name=server+":"+str(port), daemon=True)
                    self.configureAlert(alertPriority, alertAck)
                    self._thread.start()
                else:
                    self.connection=None
                    self.configureAlert(alertPriority, alertAck)
                    self.onStillConnected()


            except Exception:
                # Attempt cleanup
                try:
                    self.connection.disconnect()
                    time.sleep(2)
                except Exception:
                    pass
                try:
                    del connections[server+":"+str(port)]
                except Exception:
                    pass
                raise

    def onStillConnected(self):
        pass

    def onDisconnected(self):
        pass

    def __del__(self):
        if self.connection:
            self.connection.disconnect()

    def unsubscribe(self, topic, function):
        try:
            self.subscriptions[topic]
        except KeyError:
            pass
        with self.lock:
            torm = []
            for i in self.subscribeWrappers:
                x = self.subscribeWrappers[i]
                if x[2] == topic and (x[0]() == function or x[0]() is None):
                    messagebus.unsubscribe(x[3], x[1])
                    torm.append(i)
            for i in torm:
                try:
                    del self.subscribeWrappers[i]
                except KeyError:
                    pass

            for i in self.subscribeWrappers:
                x = self.subscribeWrappers[i]
                if x[2] == topic:
                    return

            # We could not find even a single subscriber function
            # So we unsubscribe at the MQTT level
            logging.debug("MQTT Unsubscribe from "+topic+" at "+self.server)
            if self.connection:
                self.connection.unubscribe(topic)

    def configureAlert(self, *a):
        pass

    def subscribe(self, topic, function, qos=2, encoding="json"):
        if self.connection:
            self.connection.subscribe(topic, qos)
        with self.lock:
            self.subscriptions[topic] = qos
        x = str(uuid.uuid4())

        def handleDel(*a):
            del self.subscribeWrappers[x]
            # We're really just using the "check if there's no subscribers"
            # Part of the function
            self.unsubscribe(topic, None)

        function = util.universal_weakref(function, handleDel)

        # Connection.subscribe was blocking forever.
        # Use a different thread, to hopefully avoid deadlocks
        def backgroundSubscribeTask():
            with self.lock:
                self.connection.subscribe(topic, qos)
        if self.connection:
            workers.do(backgroundSubscribeTask)

        if encoding == 'json':
            def wrapper(t, m):
                # Get rid of the extra kaithem framing part of the topic
                t = t[len("/mqtt/"+self.server+":"+str(self.port)+"/in/"):]
                function()(t, json.loads(m))

        elif encoding == 'msgpack':
            def wrapper(t, m):
                # Get rid of the extra kaithem framing part of the topic
                t = t[len("/mqtt/"+self.server+":"+str(self.port)+"/in/"):]
                function()(t, msgpack.unpackb(m,raw=False))

        elif encoding == 'utf8':
            def wrapper(t, m):
                # Get rid of the extra kaithem framing part of the topic
                t = t[len("/mqtt/"+self.server+":"+str(self.port)+"/in/"):]
                function()(t, m.decode("utf8"))

        elif encoding == 'raw':
            def wrapper(t, m):
                # Get rid of the extra kaithem framing part of the topic
                t = t[len("/mqtt/"+self.server+":"+str(self.port)+"/in/"):]
                function()(t, m)
        else:
            raise ValueError("Invalid encoding: "+encoding)

        # Correctly call message bus error handlers
        wrapper.messagebusWrapperFor = function

        internalTopic = "/mqtt/"+self.server+":"+str(self.port)+"/in/"+topic

        # Extra data is mostly used for unsubscription
        self.subscribeWrappers[x] = (function, wrapper, topic, internalTopic)

        logging.debug("MQTT subscribe to "+topic+" at "+self.server)
        # Ref to f exists as long as the original does because it's kept in subscribeWrappers
        messagebus.subscribe(internalTopic, wrapper)

    def publish(self, topic, message, qos=2, encoding="json"):
        if encoding == 'json':
            message = json.dumps(message)
        elif encoding == 'msgpack':
            message = msgpack.packb(message,use_bin_type=True)
        elif encoding == 'utf8':
            message = message.encode("utf8")
        elif encoding == 'raw':
            pass
        else:
            raise ValueError("Invalid encoding!")
        messagebus.postMessage(
            "/mqtt/"+self.server+":"+str(self.port)+"/out/"+topic, message, annotation=qos)


def getConnection(server, port, *, alertPriority="info", alertAck=True):
    # Kaithem is gonna monkeypatch kaithem with one that has better
    # logging
    global Connection
    with lock:
        if server+":"+str(port) in connections:
            x = connections[server+":"+str(port)]()
            if x:
                x.configureAlert(alertPriority, alertAck)
                return x

        return Connection(server, port, alertAck=True, alertPriority="info")
