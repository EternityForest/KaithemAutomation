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



import weakref,pavillion, threading,time,logging,traceback
import cherrypy

from . import virtualresource,pages,registry,modules_state


remote_devices = {}
remote_devices_atomic = {}

lock = threading.RLock()

#shoould contain all data needed to create the device objects and connect to them
device_data = registry.get("system_remotedevices.devices",{})
k4dlogger = logging.getLogger("system_k4d_errors")
syslogger = logging.getLogger("system.devices")




#Indexed by module,resource tuples
loadedSquirrelPrograms = {}

class RemoteSquirrelProgram():
    def __init__(self, module,resource, data):
        self.target = data['device']
        self.code = data['code']
        self.prgid=data['prgid']
        self.errors = []
        self.print = ""

    def upload(self):
        if self.target in remote_devices:
            d = remote_devices[self.target]
            d.loadProgram(self.prgid, self.code,self)

    def unload(self):
        if self.target in remote_devices:
            d = remote_devices[self.target]
            d.forceClose(self.prgid)


def removeProgram(module,resource):
    with lock:
        if (module, resource) in loadedSquirrelPrograms:
            loadedSquirrelPrograms[module,resource].unload()
            del loadedSquirrelPrograms[module,resource]




def updateProgram(module,resource, data, upload=True):
    with lock:
        data = data or modules_state.ActiveModules[module][resource]
        if (module, resource) in loadedSquirrelPrograms:
            loadedSquirrelPrograms[module,resource].unload()
        loadedSquirrelPrograms[module,resource] = RemoteSquirrelProgram(module,resource, data)
        if upload:
            try:
              loadedSquirrelPrograms[module,resource].upload()
            except:
                try:
                    loadedSquirrelPrograms[module,resource].errors.append([time.time(),traceback.format_exc()])
                except:
                    pass
                syslogger.exception("Could not upload program: "+ module+"."+resource)
#This is the base class for a remote device of any variety.

class RemoteDevice(virtualresource.VirtualResource):
    @staticmethod
    def validateData(data):
        pass

    def __init__(self,name, data):
        virtualresource.VirtualResource.__init__(self)
        global remote_devices_atomic

        self.data = data
        self.name = data.get('name', None) or name
        self.errors = []
        with lock:
            remote_devices[name]=self
            remote_devices_atomic =remote_devices.copy()

    #Takes an error as a string and handles it
    def handleError(self, s):
        self.errors.append([time.time(), str(s)])

    #delete a device, it should not be used after this
    def close(self):
        global remote_devices_atomic
        with lock:
            del remote_devices[self.name]
            remote_devices_atomic =remote_devices.copy()





##Device data always has 2 constants. 1 is the required type, the other
#is name, and that's optional but can be used to rename a device
def updateDevice(name, kwargs,saveChanges=True):
    name = name or kwargs['name']
    devicetypes.get(kwargs['type'],RemoteDevice).validateData(kwargs)
    with lock:
        if name in remote_devices:
            remote_devices[name].close()
            del device_data[name]

        #Allow name changing via data
        name=kwargs.get("name") or name
        device_data[name] = kwargs        

        remote_devices[name] = makeDevice(name, kwargs)
        global remote_devices_atomic
        remote_devices_atomic =remote_devices.copy()
        if saveChanges:
            registry.set("system_remotedevices.devices", device_data)


class WebDevices():
    @cherrypy.expose
    def index(self):
        """Index page for web interface"""
        return pages.get_template("devices/index.html").render(devices=remote_devices_atomic)
    
    @cherrypy.expose
    def device(self,name):
        return pages.get_template("devices/device.html").render(data=device_data[name], obj=remote_devices[name],name=name)

    def readFile(self, name, file):
        return remote_devices[name].readFile(file)


    @cherrypy.expose
    def updateDevice(self,name,**kwargs):
        updateDevice(name,kwargs)
        raise cherrypy.HTTPRedirect("/devices")


    @cherrypy.expose
    def createDevice(self,name,**kwargs):
        name = name or kwargs['name']
        with lock:
            device_data[name]=kwargs
            if name in remote_devices:
                remote_devices[name].close()
            remote_devices[name] = makeDevice(name, kwargs)
            global remote_devices_atomic
            remote_devices_atomic =remote_devices.copy()

        raise cherrypy.HTTPRedirect("/devices")







#We're going to put some K4D features in this class, 
#But keep it compatible with straight non-k4d pavillion stuff.
class PavillionDevice(RemoteDevice):

    @staticmethod
    def validateData(data):
        data['port'] = int(data['port'])


    def close(self):
        RemoteDevice.close(self)
        self.pclient.close()


    def __init__(self, name, data):
        if not data['type']=='pavillion':
            raise ValueError("That is not a pavillion device info dict")
        RemoteDevice.__init__(self,name,data)

        self.recievelock=threading.Lock()

        self.k4dprint = []
        self.k4derr = []
        self.loaded = weakref.WeakValueDictionary()
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



        self.psk = data['psk']

        if len(data['cid'])==32:
            self.cid = bytes.fromhex(data['cid'])
        else:
            self.cid = data['cid'].encode("utf-8")

        self.pubkey = data.get('pubkey',None)
        self.privkey = data.get('privkey',None)
        self.server_pubkey = data.get('server_pubkey', None)



        self.pclient = pavillion.Client(clientID=self.cid,psk=self.psk, address=self.address)

        def handle_print(name, data, source):
            data= data.decode("utf8")
            with lock:
                try:
                    self.loaded[name].print+= data
                    self.loaded[name].print = self.loaded[name].print[4096:]
                except Exception as e:
                    print(e)

        def handle_error(name, data, source):
            data= data.decode("utf8")
            with self.recievelock:
                self.k4derr.append((name, data,time.time()))
                self.k4derr = self.k4derr[-256:]
            with lock:
                try:
                    self.loaded[name].errors+= [data, time.time()]
                    self.loaded[name].errors = self.loaded[name].errors[4096:]
                except:
                    pass
            k4dlogger.error("Error in remote progam "+name+":\r\n"+data)
        
        self._handlerror = handle_error
        self._handleprint=handle_print

        self.t = self.pclient.messageTarget("k4dprint",handle_print)
        self.t2 = self.pclient.messageTarget("k4derr",handle_error)

    def __del__(self):
        try:
            self.pclient.close()
        except:
            pass

    def forceClose(self, name):
        c = self.pclient
        c.call(4105, name.encode("utf-8"))

    def loadProgram(self, name, p, obj=None):
        if obj:
            self.loaded[name]=obj
        c = self.pclient
        c.call(4097, name.encode("utf-8"))
        while p:
            x = p[:1024]
            p=p[1024:]
            c.call(4098, name.encode("utf8")+b"\x00"+x.encode("utf8"))
        c.call(4099, name.encode("utf-8"))

        syslogger.info("Loaded porgram:" +p+" to k4d device")

    
    def readFile(self,*a,**k):
        return self.pclient.readFile(*a,*k)

    def listDir(self, *a,**k):
        return self.pclient.listDir(*a,*k)

class DeviceNamespace():
    def __getattr__(self, name):
        return remote_devices[name].interface

devicetypes = {'pavillion':PavillionDevice}

def makeDevice(name, data):
    return {'pavillion':PavillionDevice}.get(data['type'], RemoteDevice)(name, data)

def init_devices():
        
    for i in device_data:
        try:
            remote_devices[i] = makeDevice(i, device_data[i])
        except:
            syslogger.exception("Error initializing device")

    remote_devices_atomic =remote_devices.copy()

init_devices()