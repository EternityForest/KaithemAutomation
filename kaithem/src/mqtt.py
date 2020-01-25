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

import threading,weakref,logging,time,uuid,traceback,json

logger = logging.getLogger("system.mqtt")

from . import tagpoints,messagebus,alerts,util,workers

connections = {}
lock = threading.RLock()

def getWeakrefHandlers(self):
    self=weakref.ref(self)
    def on_connect(client, userdata, flags, rc):
        logger.info("Connected to MQTT server: "+self().server)
        self().statusTagClaim.set("connected")
        self().alert.clear()

        #Don't block the network thread too long
        def subscriptionRefresh():
            with self().lock:
                for i in self().subscriptions:
                    #Refresh all subscriptions
                    self().connection.subscribe(i,self().subscriptions[i])
        workers.do(subscriptionRefresh)


    def on_disconnect(client, userdata, flags, rc):
        logger.info("Disconnected from MQTT server: "+self().server)
        self().statusTagClaim.set("disconnected")
        self().alert.trip()
        logger.info("Disconnected from MQTT server: "+s.server)

    def on_message(client, userdata,msg):
        try:
            s = self()
            #Everything must be fine, because we are getting messages
            s.alert.clear()
            messagebus.postMessage("/mqtt/"+s.server+":"+str(s.port)+"/in/"+msg.topic,msg.payload)
            s.statusTagClaim.set("connected")
        except:
            print (traceback.format_exc())

    return on_connect, on_disconnect, on_message


def makeThread(f):
    def f2():
        f()
    return f2

class Connection():
    def __init__(self, server,port=1883, *, alertPriority="info", alertAck=True):
        self.server = server
        self.port = port
        self.lock = threading.Lock()
        self.subscriptions = {}
        logger.info("Creating connection object to: "+self.server)
        import paho.mqtt.client as mqtt

        #When we wrap a function store a weakref to the original here,
        #Pplus the wrapper, so the wrapper doesn't get GCed till
        #The wearkref callback deletes it.
        self.subscribeWrappers ={}

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
            connections[n]=weakref.ref(self)

            try:
                self.connection =  mqtt.Client()


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

                self.connection.connect_async(server, port=port, keepalive=60, bind_address="")
  
                messagebus.subscribe("/mqtt/"+server+":"+str(port)+"/out/#", out_handler)
                self._thread = threading.Thread(target=makeThread(self.connection.loop_forever), name=server+":"+str(port), daemon=True)
                #We have 5s to connect before the alert actually does anything
                self.configureAlert(alertPriority,alertAck)
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
    
    def configureAlert(self, alertPriority,alertAck):
        self.alert = alerts.Alert(name="/system/mqtt/"+self.server+":"+str(self.port)+"/disconnected/",description="MQTT client is disconnected", priority=alertPriority,autoAck= alertAck,tripDelay=5)
        #Possible race condition here with a false trip just after connect. That is why we release on every recieved msg.
        if not self.statusTag.value == 'connected':
            self.alert.trip()

        time.sleep(0.05)
        if not self.statusTag.value == 'connected':
            self.alert.trip()
        else:
            self.alert.clear()


    def __del__(self):
        self.connection.disconnect()

    def unsubscribe(self,topic,function):
        try:
            self.subscriptions[topic]
        except KeyError:
            pass
        with self.lock:
            em = []
            torm =[]
            for i in self.subscribeWrappers:
               x =self.subscribeWrappers[i]
               if x[2]==topic and (x[0]()==function or x[0]()==None) :
                   messagebus.unsubscribe(x[3],x[1])
                   torm.append(i)
            for i in torm:
                try:
                    del self.subscribeWrappers[i]
                except:
                    pass
            
            for i in self.subscribeWrappers:
                x =self.subscribeWrappers[i]
                if x[2]==topic:
                   return

            #We could not find even a single subscriber function
            #So we unsubscribe at the MQTT level
            logging.debug("MQTT Unsubscribe from "+topic+" at "+self.server)
            self.connection.unsubscribe(topic)

    def subscribe(self,topic, function, qos=2, encoding="json"):
        self.connection.subscribe(topic,qos)
        with self.lock:
            self.subscriptions[topic]=qos
        x = str(uuid.uuid4())
        
        def handleDel(*a):
            del self.subscribeWrappers[x]
            #We're really just using the "check if there's no subscribers"
            #Part of the function
            self.unsubscribe(topic, None)

        function = util.universal_weakref(function, handleDel)

        #Connection.subscribe was blocking forever.
        #Use a different thread, to hopefully avoid deadlocks
        def backgroundSubscribeTask():
            with self.lock:
                self.connection.subscribe(topic,qos)
        workers.do(backgroundSubscribeTask)
        
        if encoding=='json':
            def wrapper(t,m):
                #Get rid of the extra kaithem framing part of the topic
                t = t[len("/mqtt/"+self.server+":"+str(self.port)+"/in/"):]
                function()(t,json.loads(m))

        elif encoding=='utf8':
            def wrapper(t,m):
                #Get rid of the extra kaithem framing part of the topic
                t = t[len("/mqtt/"+self.server+":"+str(self.port)+"/in/"):]
                function()(t,m.decode("utf8"))

        elif encoding=='raw':
            def wrapper(t,m):
                #Get rid of the extra kaithem framing part of the topic
                t = t[len("/mqtt/"+self.server+":"+str(self.port)+"/in/"):]
                function()(t,m)
        else:
            raise ValueError("Invalid encoding!")

        internalTopic = "/mqtt/"+self.server+":"+str(self.port)+"/in/"+topic

        #Extra data is mostly used for unsubscription
        self.subscribeWrappers[x]=(function,wrapper,topic,internalTopic)

        logging.debug("MQTT subscribe to "+topic+" at "+self.server)
        #Ref to f exists as long as the original does because it's kept in subscribeWrappers
        messagebus.subscribe(internalTopic,wrapper)

    def publish(self,topic, message,qos=2,encoding="json"):
        if encoding=='json':
            message=json.dumps(message)
        elif encoding=='utf8':
            message=message.encode("utf8")
        elif encoding=='raw':
            pass
        else:
            raise ValueError("Invalid encoding!")
        messagebus.postMessage("/mqtt/"+self.server+":"+str(self.port)+"/out/"+topic, message,annotation=2)



def getConnection(server, port,*, alertPriority="info",alertAck=True):
    with lock:
        if server+":"+str(port) in connections:
            x = connections[server+":"+str(port)]()
            if x:
                x.configureAlert(alertPriority, alertAck)
                return x

        return Connection(server,port,alertAck=True, alertPriority="info")
