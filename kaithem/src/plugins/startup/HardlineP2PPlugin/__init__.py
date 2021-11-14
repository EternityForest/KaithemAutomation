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

from src import widgets,workers

logger = logging.Logger("plugins.hardlinep2p")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""


class HardlineP2PService(devices.Device):
    deviceTypeName = 'HardlineP2PService'
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

        self.serviceDir = os.path.join(directories.vardir, "hardlinep2p", name)
        os.makedirs(self.serviceDir,exist_ok=True)

        if data.get('device.service', '').strip() and data.get('device.title', '').strip():
            def f():
                try:
                    import hardline
                    self.service = hardline.Service(os.path.join(self.serviceDir, 'service.cert'), data["device.service"], int(data.get('device.port', '80')),
                                                    {'title': data.get("device.title",'').replace('{{host}}', socket.gethostname())})
                except Exception:
                    self.handleException()
            workers.do(f)

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["HardlineP2PService"] = HardlineP2PService
