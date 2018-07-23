#Copyright Daniel Dunn 2018
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.



import weakref,pavillion, threading,time

import cherrypy

from . import virtualresource,pages


remote_devices = {}
remote_devices_atomic = {}

lock = threading.RLock()

device_data = {}


class RemoteDevice():
    @staticmethod
    def validateData(data):
        pass

    def __init__(self,name, data):
        global remote_devices_atomic

        self.data = data
        self.name = name
        self.errors = []
        with lock:
            remote_devices[name]=self
            remote_devices_atomic =remote_devices.copy()

    def handleError(self, s):
        self.errors.append([time.time(), str(s)])

    def rm(self):
        global remote_devices_atomic
        with lock:
            del remote_devices[self.name]
            remote_devices_atomic =remote_devices.copy()



class WebDevices():
    @cherrypy.expose
    def index(self):
        """Index page for web interface"""
        return pages.get_template("devices/index.html").render(devices=remote_devices_atomic)
    
    @cherrypy.expose
    def device(self,name):
        return pages.get_template("devices/device.html").render(data=device_data[name], obj=remote_devices[name],name=name)


    @cherrypy.expose
    def updateDevice(self,name,**kwargs):
        name = name or kwargs['name']
        devicetypes.get(kwargs['type'],RemoteDevice).validateData(kwargs)
        with lock:
            device_data[name]=kwargs
            if name in remote_devices:
                remote_devices[name].rm()
            remote_devices[name] = makeDevice(name, kwargs)
            global remote_devices_atomic
            remote_devices_atomic =remote_devices.copy()

        raise cherrypy.HTTPRedirect("/devices")


    @cherrypy.expose
    def createDevice(self,name,**kwargs):
        name = name or kwargs['name']
        with lock:
            device_data[name]=kwargs
            if name in remote_devices:
                remote_devices[name].rm()
            remote_devices[name] = makeDevice(name, kwargs)
            global remote_devices_atomic
            remote_devices_atomic =remote_devices.copy()

        raise cherrypy.HTTPRedirect("/devices")

class PavillionDevice(RemoteDevice,virtualresource.VirtualResource):

    @staticmethod
    def validateData(data):
        data['port'] = int(data['port'])

    def __init__(self, name, data):
        if not data['type']=='pavillion':
            raise ValueError("That is not a pavillion device info dict")
        RemoteDevice.__init__(self,name,data)

        if not 'address' in data:
            self.handleError("No address specified")
            return
        
        if not 'port' in data:
            self.handleError("No port specified")
            return

        if not 'psk' in data:
            self.handleError("No psk specified")
            return

        if not 'cid' in data:
            self.handleError("No client ID specified")
            return


        self.address = (data['address'],data['port'])
        self.psk = bytes.fromhex(data.get('psk',None))

        if len(data['cid'])==32:
            self.cid = bytes.fromhex(data['cid'])
        else:
            self.cid = data['cid'].encode("utf-8")

        self.pubkey = data.get('pubkey',None)
        self.privkey = data.get('privkey',None)
        self.server_pubkey = data.get('server_pubkey', None)


        self.pclient = pavillion.Client(clientID=self.cid,psk=self.psk, address=self.address)

    
    def readFile(*a,**k):
        self.pclient.readFile(*a,*k)

class DeviceNamespace():
    def __getattr__(self, name):
        return remote_devices[name].interface

devicetypes = {'pavillion':PavillionDevice}

def makeDevice(name, data):
    return {'pavillion':PavillionDevice}.get(data['type'], RemoteDevice)(name, data)

def init_devices():
    pass