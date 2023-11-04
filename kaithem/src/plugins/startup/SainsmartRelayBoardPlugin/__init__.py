from mako.lookup import TemplateLookup
from kaithem.src import devices, alerts, scheduling, messagebus, workers, tagpoints
from kaithem.src.scullery import workers
from kaithem.src import scullery
import os
import mako
import time
import threading
import logging
import weakref
import base64
import traceback
import shutil

from kaithem.src import widgets

logger = logging.Logger("plugins.sainsmart")

templateGetter = TemplateLookup(os.path.dirname(__file__))

defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""

devsLock = threading.Lock()


class Relayft245r(devices.Device):
    device_type_name = 'Relayft245r'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode
    description = "Control relay boards such as one chep one by SainSmart. Beware random clattering relays at boot, that is caused by the board itself."

    def close(self):
        devices.Device.close(self)

    def __del__(self):
        self.close()

    def makeWidgetHandler(self, c, state):
        def f(u, v):
            try:
                for i in v:
                    if v == 'pushed':
                        with devsLock:
                            if state:
                                self.rb.switchon(c)
                            else:
                                self.rb.switchoff(c)
            except:
                self.handleException()
                self.retryConnect()

        return f

    def makeTagHandler(self, c):
        def f(v, t, a):
            try:
                if v > 0.5:
                    with devsLock:
                        self.rb.switchon(c)
                else:
                    with devsLock:
                        self.rb.switchoff(c)
            except:
                self.retryConnect()

        return f

    def retryConnect(self):
        try:
            import relay_ft245r
            rb = relay_ft245r.FT245R()
            dev_list = rb.list_dev()

            x = []
            dev = None
            # Show their serial numbers
            for i in dev_list:
                x.append(i.serial_number)
                if str(i.serial_number) == self.data.get(
                        "device.serialnumber", ''):
                    dev = i
            self.allDevices = x

            if (self.data.get("device.serialnumber", '') == '*'):
                # Pick the first one for simplicity
                dev = dev_list[0]

            if dev is None:
                self.connectedTag.value = 0.1
                raise RuntimeError("No dev")

            print('Using device with serial number ' + dev.serial_number)
            self.connectedTag.value = 1
            rb.connect(dev)
            self.rb = rb
        except:
            self.handleException()

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        self.connectedTag = tagpoints.Tag("/devices/" + name + "/connected")

        try:
            self.retryConnect()
        except:
            self.handleException()

        self.widgets = []

        self.connectedTag.setAlarm("Disconnected", "not value")

        for n in range(8):
            i = n + 1
            x = widgets.Button()
            x.attach(self.makeWidgetHandler(i, True))

            y = widgets.Button()
            y.attach(self.makeWidgetHandler(i, False))

            t = tagpoints.Tag("/devices/" + name + "/relays[" + str(i) + "]")
            h = self.makeTagHandler(i)
            t.handlerFunction = h
            t.subscribe(h)
            self.tagPoints["ch" + str(i)] = t

            self.widgets.append((x, y))

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(
            data=self.data, obj=self)


devices.deviceTypes["Relayft245r"] = Relayft245r