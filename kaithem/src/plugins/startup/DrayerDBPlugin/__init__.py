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

from scullery import messagebus

logger = logging.Logger("plugins.drayerb")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""


# class WebUI():
#     "Web UI for providing "
#     @cherrypy.expose
#     def index(self):
#         """Index page for web interface"""
#         return pages.get_template("settings/index.html").render()

#     @cherrypy.expose
#     def loginfailures(self, **kwargs):
#         pages.require("/admin/settings.edit")
#         with weblogin.recordslock:
#             fr = weblogin.failureRecords.items()
#         return pages.get_template("settings/security.html").render(history=fr)

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

    def dataCallback(self,db, record, signature):
        messagebus.postMessage("/devices/"+self.name+"/record",record)


    def setDocument(self,document):
        with self.service:
            self.service.setDocument(document)
        self.service.commit()

    
    def getDocumentsByType(self,*a,**k):
        return self.service.getDocumentsByType(*a,**k)

    def getDocumentByID(self,*a,**k):
        return self.service.getDocumentByID(*a,**k)

    def insertNotification(self,t,v):
        n = socket.gethostname()

        #All notifications go together under a topic with knowm ID derived from name
        parent = uuid.uuid5(uuid.UUID('3a0c86c2-d836-4236-8cf3-6514643585c7'),n)
        d=self.getDocumentByID(parent)
        if not d or not d['type']=='post':
            p={
                'title':"Kaithem notifications:"+n,
                'body':'',
                'id':parent,
                'type':'post'
            }
            self.setDocument(p)
        
        p={
            'color': 'red' if 'error' in t else ('yellow' if 'warning' in t else ''),
            'title': "",
            'body': v,
            'documentTime': time.time()*10**6,
            'notify': True,
            'parent':parent,
            'type':'post',
            'autoclean':'notifications',

        }
        self.setDocument(p)

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

            self.service = drayerdb.DocumentDatabase(os.path.join(self.serviceDir, name+'.db'),keypair=(vk,sk),autocleanDays=float(self.data.get('device.autocleanDays','0')))
            self.service.dataCallback = self.dataCallback

            if self.data.get('device.archiveNotifications','').lower() =='yes':
                from scullery import messagebus
                messagebus.subscribe("/system/notifications/#", self.insertNotification)

            if self.data.get('device.syncServer',''):
                self.service.useSyncServer(self.data.get('device.syncServer',''))
        except Exception:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["DrayerDatabase"] = DrayerDatabase
