import scullery.mqtt
from mako.lookup import TemplateLookup
from src import devices, alerts, scheduling, messagebus, workers
from scullery import workers
import scullery
import os
import mako
import time
import threading
import logging
import weakref
import base64
import traceback
import shutil
from src.kaithemobj import kaithem

from src import widgets, jackmanager

logger = logging.Logger("plugins.mqtt")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    # All this device does is configure the kaithem.mqtt.connection object, available at
    # device.connection
    pass
"""


class SculleryMQTTConnection(devices.Device):
    deviceTypeName = 'SculleryMQTTConnection'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode

    def close(self):
        devices.Device.close(self)

        try:
            self.client.deactivate()
        except:
            print(traceback.format_exc())

        try:
            self.client.close()
        except:
            print(traceback.format_exc())

    def __del__(self):
        try:
            self.connection.close()
        except:
            pass

        self.close()

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        try:
            self.connection = kaithem.mqtt.Connection(
                data.get("device.server", "localhost"),
                int(data.get("device.port", "1883").strip() or 1883),
                messageBusName=data.get("device.localBusName", "").strip(),
                password=data.get("device.password", "").strip(),

            )
            self.tagPoints['status'] = self.connection.statusTag

            for i in data.get("device.watchTopics", "").split("\n"):
                i = i.strip()
                if i:
                    self.connection.subscribe(
                        i, self.onDebugIncoming, encoding="raw")
        except:
            self.handleException()

    def onDebugIncoming(self,t, v):
        try:
            self.print(str(v)[:512], title="In: "+str(t))
        except:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["SculleryMQTTConnection"] = SculleryMQTTConnection
