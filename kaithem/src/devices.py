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
import logging
import traceback
import struct
import hashlib
import base64
import gc
import os
import re
import cherrypy
import mako

from . import virtualresource, pages, registry, modules_state, kaithemobj, workers, tagpoints, alerts, persist, directories, messagebus

remote_devices = {}
remote_devices_atomic = {}

lock = threading.RLock()
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
            saved[i+".yaml"] = True
            persist.save(sd[i], os.path.join(saveLocation, i+".yaml"))

        # Delete everything not in folder
        for i in os.listdir(saveLocation):
            fn = os.path.join(saveLocation, i)
            if os.path.isfile(fn) and i.endswith(".yaml"):
                if not i in saved:
                    os.remove(fn)
        unsaved_changes = {}


messagebus.subscribe("/system/save", saveAsFiles)

def wrcopy(x):
    return {i:weakref.ref(x[i]) for i in x}

def getByDescriptor(d):
    x = {}

    for i in remote_devices_atomic:
        if d in remote_devices_atomic[i].descriptors:
            z= remote_devices_atomic[i]()
            if z:
                x[i]=z

    return x

# This is the base class for a remote device of any variety.


globalDefaultSubclassCode="""
class CustomDeviceType(DeviceType):
    pass
"""
class Device(virtualresource.VirtualResource):
    """A Descriptor is something that describes a capability or attribute
    of a device. They are string names and object values,
    and names should be globally unique"""
    descriptors = {}

    description = "Abstract base class for a device"
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

    def renderTemplate(self, file):
        return pages.get_template(file).render(data=self.data, obj=self, name=self.name)

    def setAlertPriorities(self):
        """Sets alert priorites for all alerts in the alerts dict
            based on the data key alerts.<alert_key>.priority
        """
        for i in self.alerts:
            if "alerts."+i+".priority" in self.data:
                self.alerts[i].priority = self.data["alerts."+i+".priority"]

    def setDataKey(self, key, val):
        "Lets a device set it's own persistent stored data"
        with lock:
            self.data[key] = val
            device_data[self.name][key] = str(val)
            unsaved_changes[self.name] = True

    def __init__(self, name, data):
        if not data['type'] == self.deviceTypeName:
            raise ValueError("Incorrect type in info dict")
        virtualresource.VirtualResource.__init__(self)
        global remote_devices_atomic
        global remote_devices

        dbgd[name+str(time.time())] = self

        # Time, title, text tuples for any "messages" a device might "print"
        self.messages = []


        # This data dict represents all persistent configuration
        # for the alert object.
        self.data = data.copy()
        

        # This dict cannot be changed, only replaced atomically.
        # It is a list of alert objects. Dict keys
        # may not include special chars besides underscores.

        # It is a list of all alerts "owned" by the device.
        self.alerts = {}

        # A list of all the tag points owned by the device
        self.tagPoints = {}
        # Where we stash our claims on the tags
        self.tagClaims = {}

        self.name = data.get('name', None) or name
        self.errors = []


        with lock:
            remote_devices[name] = self
            remote_devices_atomic=wrcopy(remote_devices)

    def handleException(self):
        self.handleError(traceback.format_exc(chain=True))
    # Takes an error as a string and handles it

    def handleError(self, s):
        self.errors.append([time.time(), str(s)])

        if len(self.errors)> 50:
            self.errors.pop(0)
        if len(self.errors)==1:
            messagebus.postMessage("/system/notifications/errors","First error in device: "+self.name)

    # delete a device, it should not be used after this
    def close(self):
        global remote_devices_atomic
        with lock:
            del remote_devices[self.name]
            remote_devices_atomic=wrcopy(remote_devices)

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
        self.messages.append((time.time(), title, msg, "printfunction"))
        if len(self.messages)> 100:
            try:
                self.messages.pop(0)
            except Exception:
                pass


# Device data always has 2 constants. 1 is the required type, the other
# is name, and that's optional but can be used to rename a device
def updateDevice(devname, kwargs, saveChanges=True):
    name = kwargs.get('name', None) or devname

    getDeviceType(kwargs['type']).validateData(kwargs)

    if not kwargs.get("subclass","").replace("\n",'').replace("\r","").strip():
            kwargs['subclass'] = getDeviceType(kwargs['type']).defaultSubclassCode
    unsaved_changes[devname] = True

    with lock:
        if devname in remote_devices:
            remote_devices[devname].close()
            del device_data[devname]
        gc.collect()
        time.sleep(0.01)
        time.sleep(0.01)
        gc.collect()

        # Allow name changing via data, we save under new, not the old name
        device_data[name] = {i: kwargs[i]
                             for i in kwargs if not i.startswith('temp.')}
        unsaved_changes[kwargs['name']] = True

        remote_devices[name] = makeDevice(name, kwargs)
        global remote_devices_atomic
        remote_devices_atomic=wrcopy(remote_devices)


class WebDevices():
    @cherrypy.expose
    def index(self):
        """Index page for web interface"""
        pages.require("/admin/settings.edit")
        return pages.get_template("devices/index.html").render(deviceData=remote_devices_atomic)

    @cherrypy.expose
    def device(self, name):
        pages.require("/admin/settings.edit")
        return pages.get_template("devices/device.html").render(data=device_data[name], obj=remote_devices[name], name=name)

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
    def createDevice(self, name, **kwargs):
        "Actually create the new device"

        pages.require("/admin/settings.edit")
        name = name or kwargs['name']

        with lock:
            device_data[name] = kwargs
            unsaved_changes[name] = True

            if name in remote_devices:
                remote_devices[name].close()
            remote_devices[name] = makeDevice(name, kwargs)
            global remote_devices_atomic
            remote_devices_atomic=wrcopy(remote_devices)

        raise cherrypy.HTTPRedirect("/devices")

    @cherrypy.expose
    def customCreateDevicePage(self, name, **kwargs):
        "Ether create a 'blank' device, or, if supported, show the custom page"
        pages.require("/admin/settings.edit")

        tp = getDeviceType(kwargs['type'])

        if hasattr(tp, "getCreateForm"):
            createForm = tp.getCreateForm()
        else:
            createForm = ""

        return pages.get_template("devices/createpage.html").render(customForm=createForm, name=name, type=kwargs['type'])

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
            try:
                del remote_devices[name]
            except KeyError:
                pass
            try:
                del device_data[name]
            except KeyError:
                pass
            global remote_devices_atomic
            remote_devices_atomic=wrcopy(remote_devices)
            gc.collect()
            unsaved_changes[name] = True

        raise cherrypy.HTTPRedirect("/devices")



class DeviceNamespace():
    def __getattr__(self, name):
        return remote_devices[name].interface()

    def __getitem__(self, name):
        return remote_devices[name].interface()

    def __iter__(self):
        return (i() for i in remote_devices_atomic)


builtinDeviceTypes = {'device': Device}
deviceTypes = weakref.WeakValueDictionary()




class DeviceTypeLookup():
    def __getitem__(self, k):
        if k in builtinDeviceTypes:
            dt = builtinDeviceTypes[k]
        elif k in ("", 'device', 'Device'):
            dt = Device
        else:
            dt = deviceTypes[data['type']]
        return dt


def makeDevice(name, data):

    if data['type'] in builtinDeviceTypes:
        dt = builtinDeviceTypes[data['type']]
    elif data['type'] in ("", 'device', 'Device'):
        dt = Device
    else:
        dt = deviceTypes[data['type']]

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
                from src import kaithemobj
                codeEvalScope = {"DeviceType": dt, 'kaithem': kaithemobj.kaithem}
                exec(data['subclass'], codeEvalScope, codeEvalScope)
                dt = codeEvalScope["CustomDeviceType"]
            d = dt(name, data)
            

        except:
            d = originaldt(name, data)
            d.handleError(traceback.format_exc(chain=True))
            messagebus.postMessage('/system/notifications/error',"Error with customized behavior for: "+ name+" using default")
    else:
        d = dt(name, data)

    return d


def getDeviceType(t):
    if t in builtinDeviceTypes:
        return builtinDeviceTypes[t]
    elif t in deviceTypes:
        return deviceTypes[t]
    else:
        return Device


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
    codeEvalScope = {"Device": Device, 'kaithem': kaithemobj.kaithem,
                     'deviceTypes': DeviceTypeLookup()}
    exec(compile(d, "Driver_"+name, 'exec'), codeEvalScope, codeEvalScope)

    # Remove anything in parens
    realname = re.sub(r'\(.*\)', '', name).strip()
    dt = codeEvalScope[realname]
    # Fix missing devicetypename
    dt.deviceTypeName = realname
    deviceTypes[realname] = dt
    deviceTypesFromData[realname] = dt

    createfn = os.path.join(root, name+".create.html")
    if os.path.exists(createfn):
        dt.getCreateForm = TemplateGetter(createfn)

    editfn = os.path.join(root, name+".edit.html")
    if os.path.exists(editfn):
        dt.getManagementForm = TemplateGetter(editfn)

    mdfn = os.path.join(root, "README.md")
    if os.path.exists(mdfn):
        dt.readme = mdfn


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
                        "/system/notifications/errors", "Error with device driver :"+i[1]+"\n"+traceback.format_exc(chain=True))

        else:
            os.mkdir(driversLocation)
    except:
        messagebus.postMessage("/system/notifications/errors",
                               "Error with device drivers:\n"+traceback.format_exc(chain=True))

    for i in device_data:
        try:
            remote_devices[i] = makeDevice(i, device_data[i])
            syslogger.info("Created device from config: "+i)
        except:
            messagebus.postMessage(
                "/system/notifications/errors", "Error creating device: "+i+"\n"+traceback.format_exc())
            syslogger.exception("Error initializing device "+str(i))

    remote_devices_atomic=wrcopy(remote_devices)
