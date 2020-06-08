from mako.lookup import TemplateLookup
from . import sg1
from src import devices, alerts, scheduling, tagpoints
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
    def __init__(self, *args,  kaithemInterface=None,**kwargs):
        self.kaithemInterface=kaithemInterface
        sg1.SG1Gateway.__init__(self,*args,**kwargs)

    def onConnect(self):
        self.kaithemInterface().onConnect()
        return super().onConnect()

    def onDisconnect(self):
        self.kaithemInterface().onConnect()
        return super().onDisconnect()

class Device(sg1.SG1Device):
    def __init__(self, *args,  kaithemInterface=None,**kwargs):
        self.kaithemInterface=kaithemInterface
        sg1.SG1Device.__init__(self,*args,**kwargs)

    def onMessage(self,m):
        self.kaithemInterface().onMessage(m)

    def onRTMessage(self,m):
        self.kaithemInterface().onRTMessage(m)


class SG1Device(devices.Device):
    deviceTypeName = 'SG1Device'

    def __init__(self, name, data):
        self.lock = threading.Lock()
        self.gatewayStatusTag = tagpoints.StringTag("/devices/"+name+".status")
        self.gatewayStatusTagClaim = self.gatewayStatusTag.claim('disconnected', "HWStatus", 60)
        
        devices.Device.__init__(self, name, data)

        d = str(data.get("device.channelKey", 'A'*32))
        if len(d)==32:
            d= d.encode("ascii")
        else:
            d= base64.b64decode(d)

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
       
         

    def onMessage(m):
        self.print(str(m))

    def onRTMessage(m):
        self.print(m)
    
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

        self.gw.kaithemInterface= weakref.ref(self)

        self.tagpoints={"status":self.gatewayStatusTag}
       
        devices.Device.__init__(self, name, data)
        self.print("GW obj created")

    def close(self):
        self.gw.close()
        devices.Device.close(self)

    def onConnect(self):
        self.gatewayStatusTagClaim.set("connected")
        self.print("Connected to gateway")

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
