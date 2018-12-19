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



import weakref,pavillion, threading,time,logging,traceback,struct,hashlib,base64
import cherrypy,mako

from . import virtualresource,pages,registry,modules_state,kaithemobj, workers

remote_devices = {}
remote_devices_atomic = {}

lock = threading.RLock()

#shoould contain all data needed to create the device objects and connect to them
device_data = registry.get("system_remotedevices.devices",{})
k4dlogger = logging.getLogger("system_k4d_errors")
syslogger = logging.getLogger("system.devices")




#Indexed by module,resource tuples
loadedSquirrelPrograms = {}

def sqminify(code):
    line = ''
    lines = []
    quote = False
    for i in code:
        if not quote and i=='\n':
            lines.append(line)
            line = ''
        else:
            line+= i
        if i=='"':
            quote = not quote
    lines+= [line]
    olines =[]
    for i in lines:
        x = i.strip()
        if x.startswith("\\") or x.startswith("#"):
            continue
        if not x:
            continue
        
        #Pretty sure two statements like this can just be put together
        if olines and olines[-1][-1] in ";}{" and x[-1] in ";}{":
            olines[-1]+=x
            continue
        #Put closing bracket on the line
        if olines and x[0] =="{":
            olines[-1]+=x
            continue
        olines.append(x)
    return("\n".join(olines))

class RemoteSquirrelProgram():
    def __init__(self, module,resource, data):
        self.target = data['device']
        self.code = data['code']
        self.prgid=data['prgid']
        self.errors = []
        self.print = ""
        self.module = module
        self.resource = resource


    def getPreprocessedCode(self,code=None,minify=True):
        code = code or self.code
        x = {"kaithem":kaithemobj.kaithem, "module":modules_state.scopes[self.module]}
        code =  mako.template.Template(code, uri="SquirrelTemplate"+self.module+'_'+self.resource, global_vars=x)
        code = code.render(**x)
        if minify:
            code = sqminify(code)
        code = "//"+(base64.b64encode(hashlib.sha256(code.encode("utf8")).digest()).decode("utf8"))[:14]+"\n"+ code
        return code

    def upload(self):
        if self.target in remote_devices:
            d = remote_devices[self.target]
         
            d.loadProgram(self.prgid, self.getPreprocessedCode(),self)

    def unload(self):
        if self.target in remote_devices:
            d = remote_devices[self.target]
            d.forceClose(self.prgid)


def removeProgram(module,resource):
    with lock:
        if (module, resource) in loadedSquirrelPrograms:
            loadedSquirrelPrograms[module,resource].unload()
            del loadedSquirrelPrograms[module,resource]


def loadProgramsFromModules():
    from .modules import ActiveModules
    for module in ActiveModules:
        for i in ActiveModules[module]:
            if ActiveModules[module][i]['resource-type'] == 'k4dprog_sq':
                updateProgram(module, i, ActiveModules[module][i])

def updateProgram(module,resource, data, upload=True):
    with lock:
        data = data or modules_state.ActiveModules[module][resource]
        if (module, resource) in loadedSquirrelPrograms:
            loadedSquirrelPrograms[module,resource].unload()
        loadedSquirrelPrograms[module,resource] = RemoteSquirrelProgram(module,resource, data)
        if upload:
            #Networks aren't reliable, do everything in a background thread because it might take time 
            #And we'll just try again later if it fails
            def f():
                try:
                    loadedSquirrelPrograms[module,resource].upload()
                except:
                    try:
                        loadedSquirrelPrograms[module,resource].errors.append([time.time(),traceback.format_exc()])
                    except:
                        pass
                    syslogger.exception("Could not upload program: "+ module+"."+resource)
            workers.do(f)
#This is the base class for a remote device of any variety.

class RemoteDevice(virtualresource.VirtualResource):
    @staticmethod
    def validateData(data):
        pass

    def __init__(self,name, data):
        if not data['type']==self.deviceTypeName:
            raise ValueError("Incorrect type in info dict")
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
    def status(self):
        return "norm"




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
        pages.require("/admin/settings.edit")
        return pages.get_template("devices/index.html").render(devices=remote_devices_atomic)
    
    @cherrypy.expose
    def device(self,name):
        pages.require("/admin/settings.edit")
        return pages.get_template("devices/device.html").render(data=device_data[name], obj=remote_devices[name],name=name)

    def readFile(self, name, file):
        pages.require("/admin/settings.edit")
        return remote_devices[name].readFile(file)


    @cherrypy.expose
    def updateDevice(self,name,**kwargs):
        pages.require("/admin/settings.edit")
        updateDevice(name,kwargs)
        raise cherrypy.HTTPRedirect("/devices")


    @cherrypy.expose
    def createDevice(self,name,**kwargs):
        pages.require("/admin/settings.edit")
        name = name or kwargs['name']
        with lock:
            device_data[name]=kwargs
            if name in remote_devices:
                remote_devices[name].close()
            remote_devices[name] = makeDevice(name, kwargs)
            global remote_devices_atomic
            remote_devices_atomic =remote_devices.copy()

        raise cherrypy.HTTPRedirect("/devices")





class Client2(pavillion.Client):
    def __init__(self, cb, *a,**k):
        self.connectCB = cb
        pavillion.Client.__init__(self, *a,**k)
    def onServerConnect(self, addr, pubkey):
        #That lint error is fine
        if self.connectCB:
            workers.do(self.connectCB)

class PavillionDevice(RemoteDevice):
    deviceTypeName="pavillion"
    @staticmethod
    def validateData(data):
        data['port'] = int(data['port'])


    def close(self):
        RemoteDevice.close(self)
        try:
            self.pclient.close()
        except:
            pass
    onPavillionConnect =None

    def __init__(self, name, data):

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


        self.lock = threading.RLock()
        #This client is passed a callback to autoload all new code onto the device upon connection
        self.pclient = Client2(self.onPavillionConnect, clientID=self.cid,psk=self.psk, address=self.address)


        def handle_print(name, data, source):
            data= data.decode("utf8")
            print(source, data)
            with lock:
                try:
                    self.loaded[name].print+= data
                    self.loaded[name].print = self.loaded[name].print[-4096:]
                except Exception as e:
                    print(e)

        def handle_error(name, data, source):
            data= data.decode("utf8")
            print(source, data)
            with self.recievelock:
                self.k4derr.append((name, data,time.time()))
                self.k4derr = self.k4derr[-256:]
            with lock:
                try:
                    self.loaded[name].errors+= [data, time.time()]
                    self.loaded[name].errors = self.loaded[name].errors[4096:]
                except:
                    k4dlogger.exception("Error logging the error")
            k4dlogger.error("Error in remote progam "+name+":\r\n"+data)
        
        self._handlerror = handle_error
        self._handleprint=handle_print

        #Todo: change names
        self.t = self.pclient.messageTarget("k4dprint",handle_print)
        self.t2 = self.pclient.messageTarget("k4derr",handle_error)

    def __del__(self):
        try:
            self.pclient.close()
        except:
            pass



    
    def readFile(self,*a,**k):
        return self.pclient.readFile(*a,*k)

    def listDir(self, *a,**k):
        return self.pclient.listDir(*a,*k)

class K4DDevice(PavillionDevice):
    "Represents a device that supports the full K4D standard, allowing remote code execution"

    deviceTypeName = "k4d"
    def forceClose(self, name):
        c = self.pclient
        c.call(4105, name.encode("utf-8"))

    def isRunning(self, name,hash):
        c = self.pclient
        return c.call(4100, name.encode("utf-8")+b"\x00"+hash.encode("utf-8")+b"\x00")[0]>0


    
    def _loadAll(self):
        time.sleep(3)
        with self.lock:
            for i in self.loaded:
                self.loadProgram(i, self.loaded[i].code, self.loaded[i])
    onPavillionConnect = _loadAll
    def loadProgram(self, name, p, obj=None,errors=False):
        with self.lock:
            if obj:
                self.loaded[name]=obj
            try:
                if self.isRunning(name, p[:33]):
                    return

                c = self.pclient
                c.call(4097, name.encode("utf-8"))
                pos =0
                while p:
                    x = p[:1024].encode("utf8")
                    p=p[1024:]
                    c.call(4098, struct.pack("<L",pos) +name.encode("utf8")+b"\x00"+x)
                    pos+= len(x)
                c.call(4099, name.encode("utf-8"))

                syslogger.info("Loaded porgram:" +name+" to k4d device")
            except:
                print(traceback.format_exc())
                if errors:
                    raise

class DeviceNamespace():
    def __getattr__(self, name):
        return remote_devices[name].interface

devicetypes = {'pavillion':PavillionDevice,"k4d":K4DDevice}

def makeDevice(name, data):
    return devicetypes.get(data['type'], RemoteDevice)(name, data)

def init_devices():
        
    for i in device_data:
        try:
            remote_devices[i] = makeDevice(i, device_data[i])
        except:
            syslogger.exception("Error initializing device")

    remote_devices_atomic =remote_devices.copy()

init_devices()