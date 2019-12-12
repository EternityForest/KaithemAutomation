#Copyright Daniel Dunn 2019
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

import threading,weakref,logging,time

logger = logging.getLogger("system.mqtt")

from . import tagpoints,messagebus,alerts

connections = {}
lock = threading.RLock()

def getWeakrefHandlers(self):
    self=weakref.ref(self)
    def on_connect(client, userdata, flags, rc):
        logger.info("Connected to MQTT server: "+self().server)
        self().statusTagClaim.set("connected")
        self().release()

    def on_disconnect(client, userdata, flags, rc):
        logger.info("Disconnected from MQTT server: "+self().server)
        self().statusTagClaim.set("disconnected")
        self().trip()


    def on_message(client, userdata,msg):
        s = self()
        messagebus.post("/mqtt/"+s.server+":"+str(s.port)+"/in/"+msg.topic)
        logger.info("Disconnected from MQTT server: "+s.server)
        s.statusTagClaim.set("disconnected")

    return on_connect, on_disconnect, on_message

class Connection():
    def __init__(self, server,port=1883, alert_priority="info", alert_ack=True):
        self.server = server
        self.port = port
        self.lock = threading.Lock()
        logger.info("Creating connection object to: "+self.server)
        import paho.mqtt.client as mqtt

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
            connections[n]=self

            try:
                self.connection =  mqtt.Client()
                self.connection.connect_async(server, port=port, keepalive=60, bind_address="")

                self.alert = alerts.Alert(name="/system/mqtt/"+n+"/status", priority=alert_priority,autoAck= alert_ack,tripDelay=5)

                self.statusTag = tagpoints.StringTag("/system/mqtt/"+n+"/status")
                self.statusTagClaim = self.statusTag.claim("disconnected", "status",90)

                #We don't want the connection to stringly reference us, that would interfere with GC
                on_connect,on_disconnect,on_message = getWeakrefHandlers(self)
            

                def out_handler(topic, message):
                    self.connection.publish(topic[len("/mqtt/"+server+":"+str(port)+"/out/"):], payload=message, qos=2, retain=False)
                self.out_handler=out_handler
                self.connection.on_connect = on_connect
                self.connection.on_disconnect= on_disconnect
                self.connection.on_message=on_message    
                messagebus.subscribe("/mqtt/"+server+":"+str(port)+"/out/#", out_handler)
                self._thread = threading.Thread(target=self.thread, name=server+":"+str(port), daemon=True)
                #We have 5s to connect before the alert actually does anything
                self.alert.trip()
                self._thread.start()
            
            except:
                #Attempt cleanup
                try:
                    self.connection.disconnect()
                    time.sleep(2)
                except:
                    pass
                try:
                    del connections[server+":"+str(port)]
                except:
                    pass
                raise

    def __del__(self):
        self.connection.disconnect()

    def thread(self):
        self.connection.loop_forever()

    def subscribe(self,topic, function):
        self.connection.subscribe(topic,2)
        def f(t,m):
            #Get rid of the extra kaithem framing part of the topic
            t = t[:len("/mqtt/"+s.server+":"+str(s.port)+"/in/")]
            function(t,m)
        function._mqtt_subscribe_wrapper= f
        messagebus.subscribe("/mqtt/"+s.server+":"+str(s.port)+"/in/"+topic,function)

    def publish(self,topic, message):
        messagebus.postMessage("/mqtt/"+self.server+":"+str(self.port)+"/out/"+topic, message)



def getConnection(sever, port,alert_ack=True, alert_priority="info"):
    if server+":"+str(port) in connections:
        return connections[server+":"+str(port)]

    else:
        return Connection(server,port,alert_ack=True, alert_priority="info")