from mako.lookup import TemplateLookup
from src import devices, alerts, scheduling, messagebus, workers, directories
import subprocess
import os
import mako
import time
import threading
import logging
import weakref
import base64
import traceback
import shutil
import socket
import uuid
import socket

from src import widgets

logger = logging.Logger("plugins.mqttbroker")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""

import logging
import asyncio
import os
from hbmqtt.broker import Broker


class MQTTBroker(devices.Device):
    deviceTypeName = 'MQTTBroker'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode

    @asyncio.coroutine
    def broker_coro(self):
        conf = {'listeners': {
                'default': {
                    'bind': +self.bind,
                    'type': 'tcp'
                },
                'auth': {
                    'plugins': ['auth.anonymous'],
                    'allow-anonymous': True
                }
                }
                }

        if self.wsAddr:
            ws ={
                'type':'ws',
                'bind':self.wsAddr
            }
            conf['listeners']['ws-1']=ws

        self.broker = Broker(conf)
        yield from self.broker.start()

    def close(self):
        try:
            self.broker.shutdown()
        except:
            self.handleException()

        try:
            self.loop.stop()
        except:
            self.handleException()

        try:
            self.loop.close()
        except:
            self.handleException()

        devices.Device.close(self)

    def __del__(self):
        self.close()

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        self.closed = False

        try:
            self.loop = asyncio.new_event_loop()

            if not data['device.bindTo'].strip():
                raise RuntimeError("No address selected")

            self.bind = data['device.bindTo'].strip()
            self.wsAddr = data['device.wsAddr'].strip()

            self.loop.run_until_complete(self.broker_coro())

            self.thread = threading.thread(t=self.get_event_loop().run_forever)
            self.thread.start()

        except Exception:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["HardlineP2PService"] = HardlineP2PService
