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

logger = logging.Logger("plugins.drayerb")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""


class DrayerDatabase(devices.Device):
    deviceTypeName = 'DrayerDatabase'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode

    def close(self):
        if self.service:
            try:
                self.service.close()
            except:
                logging.exception("No close")
        devices.Device.close(self)

    def __del__(self):
        self.close()

    def onDelete(self):
        import shutil
        try:
            shutil.rmtree(self.serviceDir)
        except:
            pass

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        self.closed = False
        self.service=None
        self.plock = threading.RLock()
        if '/' in name or '\\' in name:
            raise ValueError("Path sep in name")

        self.serviceDir = os.path.join(directories.vardir, "drayerdb", name)
        os.makedirs(self.serviceDir, exist_ok=True)

        try:
            from hardline import drayerdb

            if not self.data.get('device.syncKey','').strip():
                vk, sk = drayerdb.libnacl.crypto_sign_keypair()
                self.setDataKey('device.syncKey', base64.b64encode(vk).decode())
                self.setDataKey('device.writePassword', base64.b64encode(sk).decode())
            
            else:
                vk,sk =base64.b64decode(self.data.get('device.syncKey','')),base64.b64decode(self.data.get('device.writePassword',''))

            self.service = drayerdb.DocumentDatabase(os.path.join(self.serviceDir, name+'.db'),keypair=(vk,sk))

            if self.data.get('device.syncServer',''):
                self.service.useSyncServer(self.data.get('device.syncServer',''))
        except Exception:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["DrayerDatabase"] = DrayerDatabase
