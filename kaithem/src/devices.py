# Copyright Daniel Dunn 2018
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.


import weakref
import threading
import time
import textwrap
import logging
import traceback
import gc
import os
import re
import cherrypy
from typing import Dict


from . import virtualresource, pages, workers, tagpoints, alerts, persist, directories, messagebus, widgets, unitsofmeasure


#Has to be the same lock otherwise there would be too may easy ways to make a deadlock, we have to be able to
#edit the state because self modifying devices exist and can be saved in a module
from .modules_state import modulesLock as lock
from .modules_state import additionalTypes

remote_devices = {}
remote_devices_atomic = {}


device_data = {}

saveLocation = os.path.join(directories.vardir, "devices")

driversLocation = os.path.join(directories.vardir, "devicedrivers")


if os.path.isdir(saveLocation):
    for i in os.listdir(saveLocation):
        fn = os.path.join(saveLocation, i)
        if os.path.isfile(fn) and fn.endswith(".yaml"):
            d = persist.load(fn)
            d = {i: d[i] for i in d if not i.startswith('temp.')}
            device_data[i[:-len('.yaml')]] = d

syslogger = logging.getLogger("system.devices")

dbgd = weakref.WeakValueDictionary()

unsaved_changes = {}


class DeviceResourceType():
    def onload(self,module,name,value):
        with lock:
            n = module+"/"+name
            if n in remote_devices:
                remote_devices[n].close()

            remote_devices[n] = makeDevice(n,value['device'],module, name)
            global remote_devices_atomic
            remote_devices_atomic = wrcopy(remote_devices)


    def ondelete(self,module,name,value):
        with lock:
            n = module+"/"+name
            if n in remote_devices:
                remote_devices[n].close()

    def create(self,module,path,name,kwargs):
        raise RuntimeError("Not implemented, devices uses it's own create page")

    def createpage(self,module,path):
        return pages.get_template("devices/deviceintomodule.html").render(module=module,path=path)


    def editpage(self,module,name,value):
        with lock:
            n = module+"/"+name
        return pages.get_template("devices/device.html").render(data=remote_devices[n].data, obj=remote_devices[n], name=n)

drt = DeviceResourceType()
additionalTypes['device']=drt

def getZombies():
    x = []
    for i in dbgd:
        if not dbgd[i] in remote_devices.values():
            x.append(i)
    return x


def saveAsFiles():
    global unsaved_changes
    sd = device_data
    saveLocation = os.path.join(directories.vardir, "devices")
    if not os.path.exists(saveLocation):
        os.mkdir(saveLocation)

    saved = {}
    # Lock used to prevent conflict, saving over each other with nonsense data.
    with lock:
        for i in sd:
            saved[i + ".yaml"] = True
            persist.save(sd[i], os.path.join(saveLocation, i + ".yaml"))

        # Delete everything not in folder
        for i in os.listdir(saveLocation):
            fn = os.path.join(saveLocation, i)
            if os.path.isfile(fn) and i.endswith(".yaml"):
                if i not in saved:
                    os.remove(fn)
        unsaved_changes = {}


messagebus.subscribe("/system/save", saveAsFiles)


def wrcopy(x):
    return {i: weakref.ref(x[i]) for i in x}


def getByDescriptor(d):
    x = {}

    for i in remote_devices_atomic:
        if d in remote_devices_atomic[i].descriptors:
            z = remote_devices_atomic[i]()
            if z:
                x[i] = z

    return x

# This is the base class for a remote device of any variety.


globalDefaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""

try:
    try:
        import html
        esc = html.escape
    except:
        import cgi
        esc = cgi.escape
except:
    def esc(t): return t


def makeBackgroundPrintFunction(p, t, title, self):
    def f():
        self.logWindow.write('<b>' + title + " at " + t + "</b><br>"
                             + p
                             )
    return f


def makeBackgroundErrorFunction(t, time, self):
    # Don't block everything up
    def f():
        self.logWindow.write('<div class="error"><b>Error at ' + time + "</b><br>"
                             + '<pre>' + t + '</pre></div>'
                             )
    return f


class Device(virtualresource.VirtualResource):
    """A Descriptor is something that describes a capability or attribute
    of a device. They are string names and object values,
    and names should be globally unique"""
    descriptors = {}

    description = "No description set"
    deviceTypeName = "device"

    readme = None

    defaultSubclassCode = globalDefaultSubclassCode

    @staticmethod
    def validateData(data):
        pass

    @staticmethod
    def getCreateForm():
        """Method that should return HTML that may contain input tags.
         Anything prefixed with data_ will be considered somthing that goes directly into
         the device data, minus the prefix.

         The contents will be added to the form used for creating new devices of this type.
         """
        return ""


    def webHandler(self,*path,**kwargs):
        "Handle /kaithem/devices/DEVICE/web/"
        raise cherrypy.NotFound()

    def renderTemplate(self, file):
        return pages.get_template(file).render(data=self.data, obj=self, name=self.name)

    def setAlertPriorities(self):
        """Sets alert priorites for all alerts in the alerts dict
            based on the data key alerts.<alert_key>.priority
        """
        for i in self.alerts:
            if "alerts." + i + ".priority" in self.data:
                self.alerts[i].priority = self.data["alerts." +
                                                    i + ".priority"]

    def setDataKey(self, key, val):
        "Lets a device set it's own persistent stored data"
        with lock:
            self.data[key] = val
            if self.parentModule:
                from src import modules
                modules.modules_state.ActiveModules[self.parentModule][self.parentResource]['device'][key] = str(val)
                modules.unsaved_changed_obj[self.parentModule, self.parentResource] = "Device changed"
                modules.modules_state.createRecoveryEntry(self.parentModule, self.parentResource, modules.modules_state.ActiveModules[self.parentModule][self.parentResource])
                modules.modulesHaveChanged()
            else:
                #This might not be stored in the master lists, and yet it might not be connected to
                #the parentModule, because of legacy API reasons.
                #Just store it it self.data which will get saved at the end of makeDevice, that pretty much handles all module devices
                if self.name in device_data:
                    device_data[self.name][key] = str(val)
                    unsaved_changes[self.name] = True

    def __init__(self, name, data):
        if not data['type'] == self.deviceTypeName and not self.deviceTypeName=='unsupported':
            raise ValueError("Incorrect device type in info dict, does not match deviceTypeName")
        virtualresource.VirtualResource.__init__(self)
        global remote_devices_atomic
        global remote_devices

        self.logWindow = widgets.ScrollingWindow(2500)

        dbgd[name + str(time.time())] = self

        self.parentModule=None
        self.parentResource=None

        # Time, title, text tuples for any "messages" a device might "print"
        self.messages = []

        # This data dict represents all persistent configuration
        # for the alert object.
        self.data = data.copy()

        # This dict cannot be changed, only replaced atomically.
        # It is a list of alert objects. Dict keys
        # may not include special chars besides underscores.

        # It is a list of all alerts "owned" by the device.
        self.alerts: Dict[str, alerts.Alert] = {}

        # A list of all the tag points owned by the device
        self.tagPoints: Dict[str, tagpoints._TagPoint] = {}
        # Where we stash our claims on the tags
        self.tagClaims: Dict[str, tagpoints.Claim] = {}

        self.name = data.get('name', None) or name
        self.errors = []

        # self.scriptContext = scriptbindings.ChandlerScriptContext(variables={
        #     'tags': self.tagPoints,
        #     "device": self
        # })

        # self.scriptContext.commands['print'] = self.print

        with lock:
            remote_devices[name] = self
            remote_devices_atomic = wrcopy(remote_devices)


    # def loadScriptBindings(self):
    #     try:
    #         if 'rules' in self.data:
    #             self.scriptContext.addBindings(json.loads(self.data['rules']))
    #     except:
    #         self.handleException()

    def handleException(self):
        try:
            self.handleError(traceback.format_exc(chain=True))
        except:
            print(traceback.format_exc())
    # Takes an error as a string and handles it

    @property
    def tagpoints(self):
        "This property is because it's not really obvious which spelling should be used"
        return self.tagPoints

    @tagpoints.setter
    def tagpoints(self, v):
        self.tagPoints = v

    def handleError(self, s):
        self.errors.append([time.time(), str(s)])

        if self.errors:
            if time.time() > self.errors[-1][0] + 15:
                syslogger.error("in device: " + self.name + "\n" + s)
            else:
                logging.error("in device: " + self.name + "\n" + s)

        if len(self.errors) > 50:
            self.errors.pop(0)

        workers.do(makeBackgroundErrorFunction(textwrap.fill(
            s, 120), unitsofmeasure.strftime(time.time()), self))
        if len(self.errors) == 1:
            messagebus.postMessage(
                "/system/notifications/errors", "First error in device: " + self.name)
            syslogger.error("in device: " + self.name + "\n" + s)

    # delete a device, it should not be used after this
    def close(self):
        global remote_devices_atomic
        with lock:
            if self.name in remote_devices:
                del remote_devices[self.name]
                remote_devices_atomic = wrcopy(remote_devices)

            if self.parentModule:
                try:
                    del devicesByModuleAndResource[self.parentModule,self.parentResource]
                except KeyError:
                    pass



    def onDelete(self):
        "Called just before the device is deleted right after closing it."
        pass

    def status(self):
        return "norm"

    @staticmethod
    def discoverDevices():
        """Returns a list of data objectd that could be used to
            create a device object of this type, indexed by
            a string that can be up to a line of description.

            The data should leave out defaults.
        """
        return {}

    def print(self, msg, title="Message"):
        "Print a message to the Device's management page"
        t = textwrap.fill(str(msg), 120)
        tm = unitsofmeasure.strftime(time.time())

        # Can't use a def here, wouldn't want it to possibly capture more than just a string,
        # And keep stuff from GCIng for too long
        workers.do(makeBackgroundPrintFunction(t, tm, title, self))


class UnsupportedDevice(Device):
    description = "This device does not have support, or else the support is not loaded."
    deviceTypeName = "unsupported"

    def warn(self):
        self.handleError("This device type has no support.")

    def __init__(self, name, data):
        super().__init__(name, data)
        unsupportedDevices[name]=self


# Device data always has 2 constants. 1 is the required type, the other
# is name, and that's optional but can be used to rename a device
def updateDevice(devname, kwargs, saveChanges=True):
    name = kwargs.get('name', None) or devname



    getDeviceType(kwargs['type']).validateData(kwargs)

    if not kwargs.get("subclass", "").replace("\n", '').replace("\r", "").strip():
        kwargs['subclass'] = getDeviceType(kwargs['type']).defaultSubclassCode
    unsaved_changes[devname] = True

    with lock:
        if devname in remote_devices:
            parentModule= remote_devices[devname].parentModule
            parentResource= remote_devices[devname].parentResource

            remote_devices[devname].close()

            #Delete and then recreate because we may be renaming to a different name

            if not parentModule:
                del device_data[devname]
            else:
                from src import modules
                del modules.modules_state.ActiveModules[parentModule][parentResource]
                modules.unsaved_changed_obj[parentModule, parentResource] = "Device Changed or renamed"
                modules.modules_state.createRecoveryEntry(parentModule, parentResource, None)

                #Forbid moving to new module for now, specifically we don't want to move to nonexistent
                name = parentModule+"/"+name.split("/",1)[-1]
                parentResource=name.split("/",1)[-1]

        else:
            raise RuntimeError("No such device to update")

        gc.collect()
        time.sleep(0.01)
        time.sleep(0.01)
        gc.collect()
        d={i: str(kwargs[i]) for i in kwargs if not i.startswith('temp.')}


        if parentModule:
            from src import modules
            modules.modules_state.ActiveModules[parentModule][parentResource]={'resource-type':'device',"device":d}
            modules.unsaved_changed_obj[parentModule, parentResource] = "Device changed"
            modules.modules_state.createRecoveryEntry(parentModule, parentResource, {'resource-type':'device',"device":d})
            modules.modulesHaveChanged()

        else:
             # Allow name changing via data, we save under new, not the old name
            device_data[name] = d
            unsaved_changes[kwargs['name']] = True

        remote_devices[name] = makeDevice(name, kwargs,parentModule,parentResource)
        global remote_devices_atomic
        remote_devices_atomic = wrcopy(remote_devices)


class WebDevices():
    @cherrypy.expose
    def index(self):
        """Index page for web interface"""
        pages.require("/admin/settings.edit")
        return pages.get_template("devices/index.html").render(deviceData=remote_devices_atomic)

    @cherrypy.expose
    def device(self, name,*args,**kwargs):
        #This is a customizable per-device page
        if args and args[0]=='web':
            try:
                return remote_devices[name].webHandler(*args[1:], **kwargs)
            except pages.ServeFileInsteadOfRenderingPageException as e:
                return cherrypy.lib.static.serve_file(e.f_filepath, e.f_MIME, e.f_name)

        if args and args[0]=='manage':
            pages.require("/admin/settings.edit")
            return pages.get_template("devices/device.html").render(data=remote_devices[name].data, obj=remote_devices[name], name=name,args=args,kwargs=kwargs)
        if not args:
            raise cherrypy.HTTPRedirect(cherrypy.url()+"/manage")

    @cherrypy.expose
    def devicedocs(self, name):
        pages.require("/admin/settings.edit")
        x = remote_devices[name].readme

        if x is None:
            x = "No readme found"
        if x.startswith("/"):
            with open(x) as f:
                x = f.read()

        return pages.get_template("devices/devicedocs.html").render(docs=x)

    def readFile(self, name, file):
        pages.require("/admin/settings.edit")
        return remote_devices[name].readFile(file)

    @cherrypy.expose
    def updateDevice(self, devname, **kwargs):
        pages.require("/admin/settings.edit")
        updateDevice(devname, kwargs)
        raise cherrypy.HTTPRedirect("/devices")

    @cherrypy.expose
    def createDevice(self, name=None, **kwargs):
        "Actually create the new device"

        pages.require("/admin/settings.edit")
        name = name or kwargs.get('name',None)
        m=r=None
        with lock:
            if 'module' in kwargs:                
                from src import modules
                m=kwargs['module']
                r=kwargs['resource']
                name=m+"/"+r
                del kwargs['module']                
                del kwargs['resource']
                d = {i: kwargs[i] for i in kwargs if not i.startswith('temp.')}
                modules.ActiveModules[m][r]= {'resource-type':'device', 'device':d}
                modules.unsaved_changed_obj[m, r] = "Device changed"
                modules.modulesHaveChanged()
            else:                
                if not name:
                    raise RuntimeError("No name?")
                d = {i: str(kwargs[i]) for i in kwargs if not i.startswith('temp.')}
                device_data[name] = d
                unsaved_changes[name] = True

            if name in remote_devices:
                remote_devices[name].close()
            remote_devices[name] = makeDevice(name, kwargs,m,r)
            global remote_devices_atomic
            remote_devices_atomic = wrcopy(remote_devices)

        raise cherrypy.HTTPRedirect("/devices")

    @cherrypy.expose
    def customCreateDevicePage(self, name, module='',resource='',**kwargs):
        "Ether create a 'blank' device, or, if supported, show the custom page"
        pages.require("/admin/settings.edit")

        tp = getDeviceType(kwargs['type'])

        if hasattr(tp, "getCreateForm"):
            createForm = tp.getCreateForm()
        else:
            createForm = ""

        return pages.get_template("devices/createpage.html").render(customForm=createForm, name=name, type=kwargs['type'], module=module, resource=resource)

    @cherrypy.expose
    def deleteDevice(self, name, **kwargs):
        pages.require("/admin/settings.edit")
        name = name or kwargs['name']
        return pages.get_template("devices/confirmdelete.html").render(name=name)

    @cherrypy.expose
    def deletetarget(self, **kwargs):
        pages.require("/admin/settings.edit")
        name = kwargs['name']
        with lock:
            remote_devices[name].close()
            remote_devices[name].onDelete()
            try:
                del remote_devices[name]
            except KeyError:
                pass
            try:
                del device_data[name]
            except KeyError:
                pass

            if self.parentModule:
                from src import modules
                del modules.modules_state.ActiveModules[self.parentModule][self.parentResource]
                modules.unsaved_changed_obj[self.parentModule, self.parentResource] = "Device deleted"
                modules.modules_state.createRecoveryEntry(self.parentModule, self.parentResource,None)
                modules.modulesHaveChanged()
            global remote_devices_atomic
            remote_devices_atomic = wrcopy(remote_devices)
            gc.collect()
            unsaved_changes[name] = True

        raise cherrypy.HTTPRedirect("/devices")




builtinDeviceTypes = {'device': Device}
deviceTypes = weakref.WeakValueDictionary()

class DeviceNamespace():
    deviceTypes = deviceTypes
    Device = Device

    def __getattr__(self, name):
        if remote_devices[name].deviceTypeName =="unsupported":
            raise RuntimeError("There is no driver for this device")
        return remote_devices[name].interface()

    def __getitem__(self, name):
        if remote_devices[name].deviceTypeName =="unsupported":
            raise RuntimeError("There is no driver for this device")
        return remote_devices[name].interface()

    def __iter__(self):
        x=remote_devices_atomic
        return (i for i in x if not x[i]().deviceTypeName=='unsupported')

class DeviceTypeLookup():
    def __getitem__(self, k):
        if k in builtinDeviceTypes:
            dt = builtinDeviceTypes[k]
        elif k in ("", 'device', 'Device'):
            dt = Device
        return dt

devicesByModuleAndResource = weakref.WeakValueDictionary()

def makeDevice(name, data, module=None,resource=None):
    if data['type'] in builtinDeviceTypes:
        dt = builtinDeviceTypes[data['type']]
    elif data['type'] in ("", 'device', 'Device'):
        dt = Device
    elif data['type'] in deviceTypes:
        dt = deviceTypes[data['type']]
    else:
        dt = UnsupportedDevice

    if 'subclass' not in data:
        data['subclass'] = dt.defaultSubclassCode

    # Allow auto-subclassing to make customized v
    if 'subclass' in data and data['subclass'].strip():
        # Allow default code, without having to have an unneccesary layer of subclassing
        # If it is unused.   These are just purely for comparision, we don't actually use them.

        stripped = data['subclass'].replace("\n", '').replace(
            "\r", '').replace("\t", '').replace(" ", '')

        strippedGenericTemplate = globalDefaultSubclassCode.replace("\n", '').replace(
            "\r", '').replace("\t", '').replace(" ", '')

        originaldt = dt
        try:
            if not stripped == strippedGenericTemplate:
                from . import kaithemobj
                codeEvalScope = {"DeviceType": dt,
                                 'kaithem': kaithemobj.kaithem}
                exec(data['subclass'], codeEvalScope, codeEvalScope)
                dt = codeEvalScope["CustomDeviceType"]
            d = dt(name, data)

        except Exception:
            d = originaldt(name, data)
            d.handleError(traceback.format_exc(chain=True))
            messagebus.postMessage('/system/notifications/error',
                                   "Error with customized behavior for: " + name + " using default")
    else:
        d = dt(name, data)


    if module:
        from src import modules
        d.parentModule = module
        d.parentResource=resource
        devicesByModuleAndResource[module,resource]=d


        #In case something changed during initializatiion before we set it 
        #flush the changes back to the modules object if applicable
        with lock:
            modules.modules_state.ActiveModules[d.parentModule][d.parentResource]={'resource-type':'device', 'device':d.data}
            modules.unsaved_changed_obj[d.parentModule, d.parentResource] = "Device changed"
            modules.modules_state.createRecoveryEntry(d.parentModule, d.parentResource, {'resource-type':'device',"device":d.data})
            modules.modulesHaveChanged()
    return d


def getDeviceType(t):
    if t in builtinDeviceTypes:
        return builtinDeviceTypes[t]
    elif t in deviceTypes:
        return deviceTypes[t]
    else:
        return UnsupportedDevice


class TemplateGetter():
    def __init__(self, fn):
        self.fn = fn

    def __get__(self, instance, owner):
        return lambda: pages.get_vardir_template(self.fn).render(data=instance.data, obj=instance, name=instance.name)


deviceTypesFromData = {}


def loadDeviceType(root, i):
    name = i[:-3]
    fn = os.path.join(root, i)
    with open(fn) as f:
        d = f.read()

    # Avoid circular imports, kaithemobj basically depends on everything
    from . import kaithemobj
    codeEvalScope = {"Device": Device, 'kaithem': kaithemobj.kaithem,
                     'deviceTypes': DeviceTypeLookup()}
    exec(compile(d, "Driver_" + name, 'exec'), codeEvalScope, codeEvalScope)

    # Remove anything in parens
    realname = re.sub(r'\(.*\)', '', name).strip()
    dt = codeEvalScope[realname]
    # Fix missing devicetypename
    dt.deviceTypeName = realname
    deviceTypes[realname] = dt
    deviceTypesFromData[realname] = dt

    createfn = os.path.join(root, name + ".create.html")
    if os.path.exists(createfn):
        dt.getCreateForm = TemplateGetter(createfn)

    editfn = os.path.join(root, name + ".edit.html")
    if os.path.exists(editfn):
        dt.getManagementForm = TemplateGetter(editfn)

    mdfn = os.path.join(root, "README.md")
    if os.path.exists(mdfn):
        dt.readme = mdfn


def createDevicesFromData():
    for i in device_data:

        # We can call this again to reload unsupported devices.
        if i in remote_devices and not remote_devices[i].deviceTypeName == "unsupported":
            continue

        try:
            #No module or resource here
            remote_devices[i] = makeDevice(i, device_data[i])
            syslogger.info("Created device from config: " + i)
        except:
            messagebus.postMessage(
                "/system/notifications/errors", "Error creating device: " + i + "\n" + traceback.format_exc())
            syslogger.exception("Error initializing device " + str(i))

    remote_devices_atomic = wrcopy(remote_devices)

unsupportedDevices = weakref.WeakValueDictionary()

def fixUnsupported():
    "For all placeholder unsupported devices, let's see if we can fix them with a newly set up driver"
    global remote_devices_atomic
    with lock:
        #Small optimization here
        if not unsupportedDevices:
            return
        s=0
        for i in list(remote_devices.keys()):
            if remote_devices[i].deviceTypeName == 'unsupported':
                d = remote_devices[i]
                remote_devices[i]=makeDevice(i,d.data,d.parentModule,d.parentResource)
                if not remote_devices[i].deviceTypeName == 'unsupported':
                    s+=1
        if s:
            remote_devices_atomic = wrcopy(remote_devices)

def warnAboutMissingDevices():
    x = remote_devices_atomic
    for i in x:
        if x[i]().deviceTypeName() == "unsupported":
            try:
                x[i].warn()
            except Exception:
                syslogger.exception(
                    "Error warning about missing device support device " + str(i))


def init_devices():
    global remote_devices_atomic
    toLoad = []
    try:
        if os.path.isdir(driversLocation):

            # Iterate over subfolders, one subfolder per collection
            # Of device drivers.
            for root in os.listdir(driversLocation):
                root = os.path.join(driversLocation, root)
                for i in os.listdir(root):
                    if i.endswith('.py'):
                        toLoad.append((root, i))

            # sort by len, such that foo(bar) comes after bar
            toLoad = sorted(toLoad, key=lambda x: len(x[1]))
            for i in toLoad:
                try:
                    loadDeviceType(*i)
                except:
                    messagebus.postMessage(
                        "/system/notifications/errors", "Error with device driver :" + i[1] + "\n" + traceback.format_exc(chain=True))

        else:
            os.mkdir(driversLocation)
    except:
        messagebus.postMessage("/system/notifications/errors",
                               "Error with device drivers:\n" + traceback.format_exc(chain=True))

    createDevicesFromData()
