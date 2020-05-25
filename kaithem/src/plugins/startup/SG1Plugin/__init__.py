from mako.lookup import TemplateLookup
from . import sg1
from src import devices, alerts, scheduling, tagpoints
import os
import mako
import time
import threading
import logging

from src import widgets

logger = logging.Logger("plugins.sg1")

templateGetter = TemplateLookup(os.path.dirname(__file__))


class SG1Gateway(devices.Device):
    deviceTypeName = 'SG1Gateway'

    def __init__(self, name, data):
        self.lock = threading.Lock()
        self.gatewayStatusTag = tagpoints.StringTag("/devices/"+name+".status")
        self.gatewayStatusTagClaim = self.gatewayStatusTag.claim('disconnected', "HWStatus", 60)
        
        self.gw = sg1.SG1Gateway(port=data.get("device.serialport", "/dev/ttyUSB0"),
                                 id=data.get("device.gatewayID", "default"),
                                 mqttServer=data.get(
                                     "device.mqttServer", "__virtual__SG1"),
                                 mqttPort=int(
                                     data.get("device.mqttPort", 1883))
                                 )
       
        devices.Device.__init__(self, name, data)

    @staticmethod
    def getCreateForm():
        return templateGetter.get_template("createform_gateway.html").render()

    def getManagementForm(self):
        return templateGetter.get_template("manageform_gateway.html").render(data=self.data, obj=self)


devices.deviceTypes["SG1Gateway"] = SG1Gateway
