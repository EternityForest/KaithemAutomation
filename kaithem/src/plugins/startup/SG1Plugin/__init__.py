from mako.lookup import TemplateLookup
from . import sg1
from src import devices, alerts, scheduling, tagpoints,workers
import os
import mako
import time
import threading
import logging
import weakref
import base64

from src import widgets

logger = logging.Logger("plugins.sg1")

templateGetter = TemplateLookup(os.path.dirname(__file__))


class Gateway(sg1.SG1Gateway):
    def __init__(self, *args,  kaithemInterface=None, **kwargs):
        self.kaithemInterface = kaithemInterface
        sg1.SG1Gateway.__init__(self, *args, **kwargs)

    def onConnect(self):
        self.kaithemInterface().onConnect()
        self.kaithemInterface().print("Connected to gateway")
        def f():
            time.sleep(3)
            self.kaithemInterface().print("serial round-trip latency(avg,min,max): "+str(self.testLatency()))
        workers.do(f)
        return super().onConnect()

    def onDisconnect(self):
        self.kaithemInterface().onConnect()
        return super().onDisconnect()


class Device(sg1.SG1Device):
    def __init__(self, *args,  kaithemInterface=None, **kwargs):
        self.kaithemInterface = kaithemInterface
        sg1.SG1Device.__init__(self, *args, **kwargs)

    def onMessage(self, m):
        self.kaithemInterface()._onMessage(m)

    def onRTMessage(self, m):
        self.kaithemInterface()._onRTMessage(m)


class SG1Device(devices.Device):
    deviceTypeName = 'SG1Device'

    def __init__(self, name, data):
        self.lock = threading.Lock()

        self.lastSeen = 0
        self.lastRSSI = -127
        self.expectedMessageInterval = float(
            data.get("device.expectedMessageInterval", 60))

        self.rssiTag = tagpoints.Tag("/devices/"+name+".rssi")
        self.rssiTagClaim = self.rssiTag.claim(self.rssi, "HWStatus", 60)
        self.rssiTag.setAlarm("LowSignal: "+name, "value < -94")

        self.wakeButton = widgets.Button()
        self.wakeButton.attach(self.wakeButtonHandler)



        # update just a bit faster than the expected message interval
        self.rssiTag.interval = self.expectedMessageInterval*0.83

        devices.Device.__init__(self, name, data)

        self.tagPoints['rssi']= self.rssiTag

        d = str(data.get("device.channelKey", 'A'*32))
        if len(d) <= 32:
            d += 'A'*(32-len(d))
            d = d.encode("ascii")
        else:
            d = base64.b64decode(d)

        self.dev = Device(
                kaithemInterface=weakref.ref(self),
                channelKey=d,
                nodeID=int(data.get("device.nodeID", '0')),
                gateways=data.get("device.gateways", "__all__").split(","),
                mqttServer=data.get(
                    "device.mqttServer", "__virtual__SG1"),
                mqttPort=int(
                    data.get("device.mqttPort", 1883))
                )

    def status(self):
        return str(self.rssiTag.value)+"dB"

    def wakeButtonHandler(self,u, v):
        #Note that this sends one wake request that lasts 30s only
        self.dev.sendWakeRequest()

    @property
    def keepAwake(self):
        return self.dev.keepAwake

    @keepAwake.setter
    def keepAwake(self, val):
        self.dev.keepAwake = val

    def rssi(self):
        # Get the most recent RSSI from the device, or -127 if we have not recieved any correct
        # Messages at all recently
        if self.lastSeen > (time.monotonic()-self.expectedMessageInterval):
            return self.lastRSSI
        else:
            return -127

    def _onMessage(self, m):
        self.rssi = m['rssi']
        self.lastSeen = time.monotonic()
        # Trigger the tag to refresh
        x = self.rssiTag.value

        self.onMessage(m)

    def _onRTMessage(self, m):
        self.rssi = m['rssi']
        self.lastSeen = time.monotonic()
        # Trigger the tag to refresh
        x = self.rssiTag.value

        self.onRTMessage(m)

    def _onBeacon(self,m):
        self.rssi = m['rssi']
        self.lastSeen = time.monotonic()
        # Trigger the tag to refresh
        x = self.rssiTag.value

        self.onBeacon(m)


    def onMessage(self, m):
        self.print(str(m))

    def onRTMessage(self, m):
        self.print(m)

    def onBeacon(self, m):
        self.print(m)

    def sendMessage(self, msg, rt=False, power=0):
        if rt:
            limit = 64 - (3+4+4)
        else:
            limit = 64 - (6 + 3 + 8 + 8)
        if len(msg) > limit:
            raise ValueError("Message cannot be longer than "+str(limit)+" when rt="+str(rt))
        self.dev.sendMessage(msg,rt, power)

    @staticmethod
    def getCreateForm():
        return templateGetter.get_template("createform_device.html").render()

    def getManagementForm(self):
        return templateGetter.get_template("manageform_device.html").render(data=self.data, obj=self)


class SG1Gateway(devices.Device):
    deviceTypeName = 'SG1Gateway'

    def __init__(self, name, data):
        self.lock = threading.Lock()
        self.gatewayStatusTag = tagpoints.StringTag("/devices/"+name+".status")
        self.gatewayStatusTagClaim = self.gatewayStatusTag.claim('disconnected', "HWStatus", 60)
        self.gatewayStatusTag.setAlarm("GatewayDisconnected: "+name,"value != 'connected'", tripDelay=15)

        devices.Device.__init__(self, name, data)
        self.tagPoints['status']= self.gatewayStatusTag


        self.gw = Gateway(
                            kaithemInterface=weakref.ref(self),
                            port=data.get("device.serialport", "/dev/ttyUSB0"),
                            id=data.get("device.gatewayID", "default"),
                            mqttServer=data.get(
                                "device.mqttServer", "__virtual__SG1"),
                            mqttPort=int(
                                data.get("device.mqttPort", 1883)),
                            rfProfile=int(
                                data.get("device.rfProfile", 7)),
                            channelNumber=int(
                                data.get("device.channelNumber", 3))
                            )

        self.gw.kaithemInterface = weakref.ref(self)

        self.tagpoints={"status": self.gatewayStatusTag}
       
        self.print("GW obj created")

    def status(self):
        return self.gatewayStatusTag.value

    def close(self):
        self.gw.close()
        devices.Device.close(self)

    def onConnect(self):
        self.gatewayStatusTagClaim.set("connected")

    def onDisconnect(self):
        self.gatewayStatusTagClaim.set("disconnected")
        self.print("Disconnected from gateway")

    @staticmethod
    def getCreateForm():
        return templateGetter.get_template("createform_gateway.html").render()

    def getManagementForm(self):
        return templateGetter.get_template("manageform_gateway.html").render(data=self.data, obj=self)


devices.deviceTypes["SG1Gateway"] = SG1Gateway
devices.deviceTypes["SG1Device"] = SG1Device
