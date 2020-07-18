from mako.lookup import TemplateLookup
from src import devices, alerts, scheduling, messagebus, workers
from scullery import iceflow, workers, sip
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
    def __init__(self, username, port=5060, jackSource='system', jackSink='system'):
        sip.SipUserAgent.__init__(
            self, username, audioDriver="jack", port=5060, jackSource=jackSource, jackSink=jackSink)

    def onIncomingCall(self, number):
        self.controller().print("Incoming call from: "+str(number))
        self.controller().onIncomingCall(number)


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    #Function is called whenever a key is pressed.
    # Numbers are automatically converted to int type, everything else is a string
    def onKeyPress(self,key):
        self.print(key, title="Press")
"""


def numberIfPossible(n):
    try:
        return(int(n))
    except:
        return n


def onKeyWrapper(o):
    def f(k):
        o().onKeyPress(k)
    return f


def buttonPusher(dev, name):
    w = widgets.ButtonWidget()
    w.require("/admin/settings.edit")

    def f(u, v):
        if 'pushed' in v:
            dev._onKeyPress(name, True)
    return w


class PiMatrixKeypad(devices.Device):
    deviceTypeName = 'PiMatrixKeypad'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode

    def close(self):
        devices.Device.close(self)
        try:
            self.pad.close()
        except:
            print(traceback.format_exc())

    def __del__(self):
        self.close()

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        self.testMode =  data.get("device.testMode", "") in ("true","yes","on","enable","test")

        try:
            keys = [[numberIfPossible(k.strip()) for k in i.split(
                ",")] for i in data.get("device.keys", "").split("\n")]
            import pad4pi_patched

            self.padFactory = rpi_gpio.KeypadFactory()

            rows = [int(i.strip())
                    for i in data.get("device.rowPinsBCM", "").split(",")]
            cols = [int(i.strip())
                    for i in data.get("device.colPinsBCM", "").split(',')]

            self.padFactory.create_keypad(
                keypad=keys, row_pins=rows, col_pins=cols)
            # Weakrefs to stop any garbage cycles
            self.padFactory.registerKeyPressHandler(
                onKeyWrapper(weakref.ref(self)))
        except:
            self.handleException()

        self.keyWidgets = []

        for i in self.keys:
            x = []
            for k in i:
                x.append((buttonPusher(self, k), k))
            self.keyWidgets.append(x)

    def _onKeyPress(self, key, fromUI=None):
        if fromUI or not self.testMode:
            messagebus.postMessage("/devices/"+self.name+"/keypress", key)
            self.onKeyPress()

        else self.testMode:
            self.print(key, "keypress[IGNORED]")

    def onKeyPress(self):
        pass

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["RPiGPIOKeypad"] = JackBareSipAgent
