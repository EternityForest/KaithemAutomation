from mako.lookup import TemplateLookup
from src import devices, alerts, scheduling, messagebus, workers
from scullery import iceflow, workers,sip
import os
import mako
import time
import threading
import logging 
import weakref
import base64
import traceback
import shutil

from src import widgets

logger = logging.Logger("plugins.baresip")

templateGetter = TemplateLookup(os.path.dirname(__file__))


class JackBareSipAgentRunner(sip.SipUserAgent):
    def __init__(self, username,port=5060, jackSource='system', jackSink='system'):
        sip.SipUserAgent.__init__(
            self, username, audioDriver="jack", port=5060, jackSource=jackSource, jackSink=jackSink)

    def onIncomingCall(self, number):
        self.controller().print("Incoming call from: "+str(number))
        self.controller().onIncomingCall(number)


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    def onIncomingCall(self,number):
        # Uncomment to accept all incoming calls
        # self.accept()
        pass
"""


class JackBareSipAgent(devices.Device):
    deviceTypeName = 'JackBareSipAgent'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode

    def close(self):
        devices.Device.close(self)
        try:
            self.agent.close()
        except:
            print(traceback.format_exc())
    
    def __del__(self):
        self.close()

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        try:
            self.agent = JackBareSipAgentRunner(
                                          data.get("device.username", "kaithem"),
                                          int(data.get("device.port", 5060)),
                                          data.get("device.jacksrc", "system"),
                                          data.get("device.jacksink", "system"))
            self.agent.controller = weakref.ref(self)
        except:
            self.handleException()

    def onIncomingCall(self, number):
        pass

    def call(self, number):
        self.print("Outgoing call to: "+str(number))
        self.agent.call(number)
    
    def hang(self):
        self.print("Hanging up.")
        self.agent.hang()



    def accept(self):
        self.print("Call Accepted")
        self.agent.accept()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["JackBareSipAgent"] = JackBareSipAgent
