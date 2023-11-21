

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

import html
from . import modules_state
from .modules_state import additionalTypes
import json
import colorzero
import weakref
import time
import textwrap
import logging
import traceback
import gc
import os
import re
import cherrypy
import copy
import asyncio
from typing import Dict, Optional, Union, Any, Callable
import urllib.parse

from . import pages, workers, tagpoints, alerts
from . import persist, directories, messagebus, widgets, unitsofmeasure

import iot_devices.host
import iot_devices.device

# Our lock to be the same lock as the modules lock otherwise there would be too may easy ways to make a deadlock, we have to be able to
# edit the state because self modifying devices exist and can be saved in a module
log = logging.getLogger("system.devices")


remote_devices: Dict[str, object] = {}
remote_devices_atomic = {}

device_data = {}

saveLocation = os.path.join(directories.vardir, "devices")

driversLocation = os.path.join(directories.vardir, "devicedrivers")


recent_scanned_tags = {}

# Used by device tag j2 template
callable = callable


def log_scanned_tag(v: str, *args):
    recent_scanned_tags[v] = time.time()
    if len(recent_scanned_tags) > 15:
        recent_scanned_tags.pop(next(iter(recent_scanned_tags)))


if os.path.isdir(saveLocation):
    for i in os.listdir(saveLocation):
        fn = os.path.join(saveLocation, i)
        if os.path.isfile(fn) and fn.endswith(".yaml"):
            d = persist.load(fn)
            d = {i: d[i] for i in d if not i.startswith('temp.')}
            device_data[i[:-len('.yaml')]] = d

syslogger = logging.getLogger("system.devices")

dbgd = weakref.WeakValueDictionary()


def closeAll(*a):
    for i in list(remote_devices_atomic.keys()):
        try:
            c = remote_devices_atomic[i]
        except KeyError:
            continue
        c = c()
        if c:
            c.close()


class DeviceResourceType():
    def onload(self, module, name, value):
        with modules_state.modulesLock:
            n = module + "/" + name
            if n in remote_devices:
                remote_devices[n].close()

            remote_devices[n] = makeDevice(n, value['device'], module, name)
            global remote_devices_atomic
            remote_devices_atomic = wrcopy(remote_devices)

    def ondelete(self, module, name, value):
        with modules_state.modulesLock:
            n = module + "/" + name
            if n in remote_devices:
                x = remote_devices[n]
                x.close()
                gc.collect
                x.onDelete()
                gc.collect()
                remote_devices.pop(n, None)

            global remote_devices_atomic
            remote_devices_atomic = wrcopy(remote_devices)
            # Gotta be aggressive about ref cycle breaking!
            gc.collect()
            time.sleep(0.1)
            gc.collect()
            time.sleep(0.2)
            gc.collect()

    def create(self, module, path, name, kwargs):
        raise RuntimeError(
            "Not implemented, devices uses it's own create page")

    def createpage(self, module, path):
        return pages.get_template("devices/deviceintomodule.html").render(
            module=module, path=path)

    def editpage(self, module, name, value):
        with modules_state.modulesLock:
            n = module + "/" + name
        return pages.get_template("devices/device.html").render(
            data=remote_devices[n].config, obj=remote_devices[n], name=n)


drt = DeviceResourceType()
additionalTypes['device'] = drt


def getZombies():
    x = []
    v = remote_devices.values()
    for i in dbgd:
        if not dbgd[i] in v:
            x.append((i, dbgd[i]))
    return x


def saveDevice(d):
    sd = device_data
    saveLocation = os.path.join(directories.vardir, "devices")
    if not os.path.exists(saveLocation):
        os.mkdir(saveLocation)

    # Lock used to prevent conflict, saving over each other with nonsense data.
    with modules_state.modulesLock:
        if d in sd:
            persist.save(sd[d], os.path.join(saveLocation, d + ".yaml"))
            os.chmod(os.path.join(saveLocation, d + ".yaml"), 0o600)

        if d not in sd:
            fn = os.path.join(saveLocation, d + ".yaml")
            if os.path.isfile(fn):
                os.remove(fn)


def getDeviceConfigFolder(d, create=True):
    saveLocation = os.path.join(directories.vardir, "devices", d)
    if not os.path.exists(saveLocation):
        if not create:
            return None
        os.mkdir(saveLocation)

    return saveLocation


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


esc = html.escape


def makeBackgroundPrintFunction(p, t, title, self):
    def f():
        self.logWindow.write('<b>' + title + " at " + t + "</b><br>" + p)

    return f


def makeBackgroundErrorFunction(t, time, self):
    # Don't block everything up
    def f():
        self.logWindow.write('<div class="danger"><b>Error at ' + time +
                             "</b><br>" + '<pre>' + t + '</pre></div>')

    return f


class Device():
    """A Descriptor is something that describes a capability or attribute
    of a device. They are string names and object values,
    and names should be globally unique"""
    descriptors: Dict[str, object] = {}

    description = ""
    readme = ''
    device_type_name = "device"

    readme = None

    # Placeholder not meant to be used as the kaithem specific device api is deprecated
    subdevices = {}

    # We are renaming data to config for clarity.
    # This is the legacy alias.
    @property
    def data(self):
        return self.config

    @data.setter
    def data(self, v):
        return self.config.update(v)

    def getManagementForm(self):
        return ''

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

    def webHandler(self, *path, **kwargs):
        "Handle /kaithem/devices/DEVICE/web/"
        raise cherrypy.NotFound()

    def renderTemplate(self, file):
        return pages.get_template(file).render(data=self.config,
                                               obj=self,
                                               name=self.name)

    def setAlertPriorities(self):
        """Sets alert priorites for all alerts in the alerts dict
            based on the data key alerts.<alert_key>.priority
        """
        for i in self.alerts:
            if "alerts." + i + ".priority" in self.config:
                self.alerts[i].priority = self.config["alerts." + i +
                                                      ".priority"]

    def setDataKey(self, key, val):
        "Lets a device set it's own persistent stored data"

        # We allow special config keys
        if not key.startswith('kaithem.'):
            v = str(val)

        with modules_state.modulesLock:
            self.config[key] = v

            if not self.config.get("is_ephemeral", False) and not key.startswith('temp.'):
                if self.parentModule:
                    modules_state.ActiveModules[self.parentModule][
                        self.parentResource]['device'][key] = v

                    modules_state.saveResource(
                        self.parentModule, self.parentResource,
                        modules_state.ActiveModules[self.parentModule][
                            self.parentResource])
                    modules_state.modulesHaveChanged()
                else:
                    # This might not be stored in the master lists, and yet it might not be connected to
                    # the parentModule, because of legacy API reasons.
                    # Just store it it self.config which will get saved at the end of makeDevice, that pretty much handles all module devices
                    if self.name in device_data:
                        device_data[self.name][key] = v
                        saveDevice(self.name)

    def setObject(self, key, val):
        # Store data
        json.dumps(val)

        "Lets a device set it's own persistent stored data"
        with modules_state.modulesLock:
            self.config[key] = val
            if self.parentModule:
                from . import modules_state
                modules_state.ActiveModules[self.parentModule][
                    self.parentResource]['device'][key] = val
                modules_state.saveResource(
                    self.parentModule, self.parentResource,
                    modules_state.ActiveModules[self.parentModule][
                        self.parentResource])
                modules_state.modulesHaveChanged()
            else:
                # This might not be stored in the master lists, and yet it might not be connected to
                # the parentModule, because of legacy API reasons.
                # Just store it it self.config which will get saved at the end of makeDevice, that pretty much handles all module devices
                if self.name in device_data:
                    device_data[self.name][key] = val

    def getObject(self, key, default=None):
        "Lets a device set it's own persistent stored data"
        with modules_state.modulesLock:
            if self.parentModule:
                return modules_state.ActiveModules[self.parentModule][
                    self.parentResource]['device'][key]
            else:
                # This might not be stored in the master lists, and yet it might not be connected to
                # the parentModule, because of legacy API reasons.
                # Just store it it self.config which will get saved at the end of makeDevice, that pretty much handles all module devices
                if self.name in device_data:
                    return device_data[self.name][key]
        return default

    @staticmethod
    def makeUIMsgHandler(wr):
        def f(u, v):
            wr().on_ui_message(u)

        return f

    @staticmethod
    def makeGenericUIMsgHandler(wr):
        def f(u, v):
            wr().onGenericUIMessage(u, v)

        return f

    def __init__(self, name, data):
        if not data[
                'type'] == self.device_type_name and not self.device_type_name == 'unsupported':
            raise ValueError(
                "Incorrect device type in info dict," +
                data['type'] + " does not match device_type_name " +
                self.device_type_name
            )
        global remote_devices_atomic
        global remote_devices

        try:
            self.title: str = data.get('title', '').strip() or name
        except Exception:
            self.title = name

        self.config_properties = {}

        self.logWindow = widgets.ScrollingWindow(2500)

        self._tagBookKeepers = {}

        # The single shared broadcast data channel the spec suggests we have
        self._admin_ws_channel = widgets.APIWidget()
        self._admin_ws_channel.require("/admin/settings.edit")

        # This is for extra non device specific stuff we add to all devices
        self._generic_ws_channel = widgets.APIWidget()
        self._generic_ws_channel.require("/admin/settings.edit")

        # Widgets could potentially stay around after this was deleted,
        # because a connection was open. We wouldn't want that to keep this device around when it should not
        # be.
        onMessage = self.makeUIMsgHandler(weakref.ref(self))

        onMessage2 = self.makeGenericUIMsgHandler(weakref.ref(self))

        # Maps the local short tag namre to the tag the user bound it to in the UI
        self._kBindings = {}

        # I don't think this is actually needed
        self._uiMsgRef = onMessage

        self._admin_ws_channel.attach(onMessage)
        self._generic_ws_channel.attach(onMessage2)

        dbgd[name + str(time.time())] = self

        self.parentModule = None
        self.parentResource = None

        # Time, title, text tuples for any "messages" a device might "print"
        self.messages = []

        # This data dict represents all persistent configuration
        # for the alert object.
        self.config = copy.deepcopy(data)

        # This dict cannot be changed, only replaced atomically.
        # It is a list of alert objects. Dict keys
        # may not include special chars besides underscores.

        # It is a list of all alerts "owned" by the device.
        self.alerts: Dict[str, alerts.Alert] = {}

        # A list of all the tag points owned by the device
        self.tagPoints: Dict[str, tagpoints.TagPointClass] = {}
        # Where we stash our claims on the tags
        self.tagClaims: Dict[str, tagpoints.Claim] = {}

        self._deviceSpecIntegrationHandlers = {}

        # The new devices spec has a way more limited idea of what a data point is.
        self.datapoints = {}

        self.name = data.get('name', None) or name
        self.errors = []

        # self.scriptContext = scriptbindings.ChandlerScriptContext(variables={
        #     'tags': self.tagPoints,
        #     "device": self
        # })

        # self.scriptContext.commands['print'] = self.print

        with modules_state.modulesLock:
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
            self.handle_error(traceback.format_exc(chain=True))
        except Exception:
            print(traceback.format_exc())

    # Takes an error as a string and handles it

    @property
    def tagpoints(self):
        "This property is because it's not really obvious which spelling should be used"
        try:
            return self.tagPoints
        except AttributeError:
            # Defence against erroneous devices
            return {}

    @tagpoints.setter
    def tagpoints(self, v):
        self.tagPoints = v

    # def handler(v,t or None, a="Set by device"):
    #     self.setClaimVal("default", v, t or time.monotonic(), a)

    def handle_error(self, s):
        self.errors.append([time.time(), str(s)])

        if self.errors:
            if time.time() > self.errors[-1][0] + 15:
                syslogger.error("in device: " + self.name + "\n" + s)
            else:
                log.error("in device: " + self.name + "\n" + s)

        if len(self.errors) > 50:
            self.errors.pop(0)

        workers.do(
            makeBackgroundErrorFunction(textwrap.fill(s, 120),
                                        unitsofmeasure.strftime(time.time()),
                                        self))
        if len(self.errors) == 1:
            messagebus.post_message("/system/notifications/errors",
                                   "First error in device: " + self.name)
            syslogger.error("in device: " + self.name + "\n" + s)

    def onGenericUIMessage(self, u, v):
        if v[0] == 'set':
            if v[2] is not None:
                self.tagPoints[v[1]].value = v[2]

        if v[0] == 'fake':
            if v[2] is not None:
                self.tagPoints[v[1]]._k_ui_fake = self.tagPoints[v[1]].claim(
                    v[2], "faked", priority=50.5)

            else:
                if hasattr(self.tagPoints[v[1]], "_k_ui_fake"):
                    self.tagPoints[v[1]]._k_ui_fake.release()

        elif v[0] == 'refresh':
            self.tagPoints[v[1]].pull()

    # delete a device, it should not be used after this
    def close(self):
        global remote_devices_atomic
        with modules_state.modulesLock:
            if self.name in remote_devices:
                del remote_devices[self.name]
                remote_devices_atomic = wrcopy(remote_devices)

            if self.parentModule:
                try:
                    del devicesByModuleAndResource[self.parentModule,
                                                   self.parentResource]
                except KeyError:
                    pass

            if hasattr(self, "_kBindings"):
                for i in self._kBindings:
                    try:
                        self._kBindings[i].unsubscribe(self.tagPoints[i])
                    except Exception:
                        log.exception(
                            "Could not unsub. Maybe was never created.")

            if hasattr(self, "tagPoints"):
                for i in self.tagPoints:
                    t = self.tagPoints[i]

                    if hasattr(t, "_kOutputBindings"):
                        for i in t._kOutputBindings:
                            try:
                                t.unsubscribe[i]
                            except Exception:
                                log.exception(
                                    "Could not unsub. Maybe was never created.")

                    t._kOutputBindings = []

            # Be defensive about ref cycles.
            try:
                del self._kBindings
            except Exception:
                pass

            # Be defensive about ref cycles.
            try:
                del self._kRevBindings
            except Exception:
                pass

            try:
                del self.tagPoints
            except Exception:
                pass
        try:
            for i in self.alerts:
                try:
                    self.alerts[i].release()
                except Exception:
                    log.exception("Error releasing alerts")
        except Exception:
            log.exception("Error releasing alerts")

    def onDelete(self):
        "Called just before the device is deleted right after closing it."
        pass

    def status(self):
        return "norm"

    @staticmethod
    def discoverDevices(config: Dict[str, str] = {},
                        current_device: Optional[object] = None,
                        intent="",
                        **kwargs) -> Dict[str, Dict]:
        """create a device object of this type, indexed by
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
    device_type_name = "unsupported"
    device_type = 'unsupported'

    def warn(self):
        self.handle_error("This device type has no support.")

    def __init__(self, name, data):
        super().__init__(name, data)
        unsupportedDevices[name] = self


class UnusedSubdevice(Device):
    description = "Someone created configuration for a subdevice that is no longer in use or has not yet loaded"
    device_type_name = "UnusedSubdevice"
    device_type = 'UnusedSubdevice'

    def warn(self):
        self.handle_error("This device type has no support.")

    def __init__(self, name, data):
        super().__init__(name, data)


class CrossFrameworkDevice(Device, iot_devices.device.Device):
    ######################################################################################
    # Compatibility block for this spec https://github.com/EternityForest/iot_devices
    # Musy ONLY have things we want to override from the imported driver class,
    # as this will have the highest priority
    # Keep this pretty self contained.  That makes it clear what's a Kaithem feature and
    # what is in the generic spec
    ######################################################################################

    # Alarms are only done via the new tags way with these
    _noSetAlarmPriority = True

    _isCrossFramework = True

    def get_config_folder(self, create=True):
        return getDeviceConfigFolder(self.name, create=create)

    def create_subdevice(self, cls, name: str, config: Dict, *a, **k):
        """
            Allows a device to create it's own subdevices.             
        """
        global remote_devices_atomic

        originalName = name

        name = self.name + '.' + name

        config = copy.deepcopy(config)
        config['name'] = name
        config['is_subdevice'] = "true"

        # Mix in the config for the data
        try:
            if name in device_data:
                config.update(device_data[name])
        except KeyError:
            log.exception(
                'Probably a race condition. Can probably ignore this one.')

        with modules_state.modulesLock:
            if name in remote_devices_atomic:
                n = remote_devices_atomic.get(name, None)
                if n:
                    n = n()
                if n:
                    if not n.device_type in ['UnusedSubdevice', 'unsupported']:
                        raise RuntimeError("Subdevice name is already in use")
                    remote_devices.pop(name)
                    remote_devices_atomic = wrcopy(remote_devices)

        m = makeDevice(name=name, data=config, cls=cls)

        m._kaithem_is_subdevice = True

        with modules_state.modulesLock:
            c2 = copy.deepcopy(config)
            c2.pop('type', cls.device_type)
            device_data[name] = config
            self.subdevices[originalName] = m
            remote_devices[name] = m
            remote_devices_atomic = wrcopy(remote_devices)

        return m

    def webHandler(self, *path, **kwargs):
        """
            A device's web page is also permissioned based on the global rules.
        """
        if cherrypy.request.method in ('post', 'put'):
            perms = self.config.get(
                "kaithem.write_perms", '').strip() or "/admin/settings.edit"

        if cherrypy.request.method == "get":
            perms = self.config.get(
                "kaithem.write_perms", '').strip() or "/admin/settings.edit"

        for i in perms.split(","):
            pages.require(i)

        return asyncio.run(self.web_handler(path, kwargs, cherrypy.request.method))

    def serve_file(self, fn, mime='', name=None):
        from . import kaithemobj
        return kaithemobj.kaithem.web.serve_file(fn, mime, name)

    def __setupTagPerms(self, t, writable=True):
        # Devices can have a default exposure
        readPerms = self.config.get("kaithem.read_perms", '').strip()
        writePerms = self.config.get("kaithem.write_perms", '').strip()
        t.expose(readPerms, writePerms if writable else [])

    def handle_web_request(self, relpath, params, method, **kwargs):
        "To be called by the framework"
        return "No web content here"

    def web_serve_file(self, path, filename=None, mime=None):
        """
        From within your web handler, you can return the result of this to serve that file
        """
        return pages.serveFile(path, mime or '', filename)

    def numeric_data_point(self,
                           name: str,
                           min: Optional[float] = None,
                           max: Optional[float] = None,
                           hi: Optional[float] = None,
                           lo: Optional[float] = None,
                           description: str = "",
                           unit: str = '',
                           handler: Optional[Callable[[str, float, Any],
                                                      Any]] = None,
                           default: float = 0,
                           interval: float = 0,
                           writable: bool = True,
                           subtype: str = '',
                           **kwargs):

        with modules_state.modulesLock:
            if "/" in name:
                t = tagpoints.Tag("/devices/" + self.name + "/" + name)
            else:
                t = tagpoints.Tag("/devices/" + self.name + "." + name)

            self.__setupTagPerms(t, writable)

            t._dev_ui_writable = writable

            t.min = min
            t.max = max
            t.hi = hi
            t.lo = lo
            t.description = description
            t.unit = unit
            t.default = default
            t.interval = interval
            t.subtype = subtype
            t.writable = writable

            def f(v, t, a):
                self.datapoints[name] = v
            self._tagBookKeepers[name] = f
            t.subscribe(f)

            # Be defensive
            if name in self._deviceSpecIntegrationHandlers:
                t.unsubscribe(self._deviceSpecIntegrationHandlers[name])

            if handler:
                self._deviceSpecIntegrationHandlers[name] = handler
                t.subscribe(handler)

            self.tagPoints[name] = t
            self.datapoints[name] = None

            # On demand subscribe to the binding for the tag we just made
            if name in self._kBindings:
                self._kBindings[name].subscribe(
                    t, immediate=(not t.subtype == 'trigger'))

            x = {i[0]: i[1]
                 for i in self.config.get('kaithem.output_bindings', [])}
            if name in x:
                doOutputBinding(t, x[name], 'Set by device: ' + self.name)

            messagebus.post_message("/system/tags/configured", t.name)

    def string_data_point(self,
                          name: str,
                          description: str = "",
                          handler: Optional[Callable[[str, float, Any],
                                                     Any]] = None,
                          default: float = 0,
                          interval: float = 0,
                          writable: bool = True,
                          subtype: str = '',
                          **kwargs):
        with modules_state.modulesLock:
            if "/" in name:
                t = tagpoints.StringTag("/devices/" + self.name + "/" + name)
            else:
                t = tagpoints.StringTag("/devices/" + self.name + "." + name)

            self.__setupTagPerms(t, writable)
            t._dev_ui_writable = writable

            t.description = description
            t.default = default
            t.interval = interval
            t.subtype = subtype
            t.writable = writable

            def f(v, t, a):
                self.datapoints[name] = v
            self._tagBookKeepers[name] = f
            t.subscribe(f)

            # Be defensive
            if name in self._deviceSpecIntegrationHandlers:
                t.unsubscribe(self._deviceSpecIntegrationHandlers[name])

            if handler:
                self._deviceSpecIntegrationHandlers[name] = handler
                t.subscribe(handler)

            self.tagPoints[name] = t
            self.datapoints[name] = None

            # On demand subscribe to the binding for the tag we just made
            if name in self._kBindings:
                self._kBindings[name].subscribe(
                    t, immediate=(not t.subtype == 'trigger'))

            x = {i[0]: i[1]
                 for i in self.config.get('kaithem.output_bindings', [])}
            if name in x:
                doOutputBinding(t, x[name], 'Set by device: ' + self.name)

            messagebus.post_message("/system/tags/configured", t.name)

    def object_data_point(self,
                          name: str,
                          description: str = "",
                          handler: Optional[Callable[[str, float, Any],
                                                     Any]] = None,
                          interval: float = 0,
                          writable: bool = True,
                          subtype: str = '',

                          **kwargs):

        with modules_state.modulesLock:
            if "/" in name:
                t = tagpoints.ObjectTag("/devices/" + self.name + "/" + name)
            else:
                t = tagpoints.ObjectTag("/devices/" + self.name + "." + name)

            self.__setupTagPerms(t, writable)
            t._dev_ui_writable = writable
            t.subtype = subtype

            t.description = description
            t.interval = interval
            t.writable = writable

            def f(v, t, a):
                self.datapoints[name] = v
            self._tagBookKeepers[name] = f
            t.subscribe(f)

            # Be defensive
            if name in self._deviceSpecIntegrationHandlers:
                t.unsubscribe(self._deviceSpecIntegrationHandlers[name])

            if handler:
                self._deviceSpecIntegrationHandlers[name] = handler
                t.subscribe(handler)

            self.tagPoints[name] = t
            self.datapoints[name] = None

            # On demand subscribe to the binding for the tag we just made
            if name in self._kBindings:
                self._kBindings[name].subscribe(
                    t, immediate=(not t.subtype == 'trigger'))

            x = {i[0]: i[1]
                 for i in self.config.get('kaithem.output_bindings', [])}
            if name in x:
                doOutputBinding(t, x[name], 'Set by device: ' + self.name)

            messagebus.post_message("/system/tags/configured", t.name)

    def bytestream_data_point(self,
                              name: str,
                              description: str = "",
                              handler: Optional[Callable[[str, float, Any],
                                                         Any]] = None,
                              interval: float = 0,
                              writable: bool = True,
                              subtype: str = '',

                              **kwargs):

        with modules_state.modulesLock:
            if "/" in name:
                t = tagpoints.BinaryTag("/devices/" + self.name + "/" + name)
            else:
                t = tagpoints.BinaryTag("/devices/" + self.name + "." + name)
            t.unreliable = True

            self.__setupTagPerms(t, writable)
            t._dev_ui_writable = writable
            t.subtype = subtype

            t.description = description
            t.interval = interval

            # Be defensive
            if name in self._deviceSpecIntegrationHandlers:
                t.unsubscribe(self._deviceSpecIntegrationHandlers[name])

            if handler:
                self._deviceSpecIntegrationHandlers[name] = handler
                t.subscribe(handler)

            self.tagPoints[name] = t
            self.datapoints[name] = None

            # On demand subscribe to the binding for the tag we just made
            if name in self._kBindings:
                self._kBindings[name].subscribe(
                    t, immediate=(not t.subtype == 'trigger'))

            x = {i[0]: i[1]
                 for i in self.config.get('kaithem.output_bindings', [])}
            if name in x:
                doOutputBinding(t, x[name], 'Set by device: ' + self.name)

            messagebus.post_message("/system/tags/configured", t.name)

    def push_bytes(self, name, value,):
        self.tagPoints[name].fastPush(value, None, None)

    def set_data_point(self, name, value, timestamp=None, annotation=None):
        self.tagPoints[name](value, timestamp, annotation)
        self.datapoints[name] = copy.deepcopy(value)

    def set_data_point_getter(self, name, value):
        # Tag points have this functionality already
        self.tagPoints[name].value = value

    def set_alarm(self,
                  name: str,
                  datapoint: str,
                  expression: str,
                  priority: str = "info",
                  trip_delay: float = 0,
                  auto_ack: bool = False,
                  release_condition: Optional[str] = None,
                  **kw):

        self.alerts[name] = self.tagPoints[datapoint].setAlarm(
            name,
            condition=expression,
            priority=priority,
            trip_delay=trip_delay,
            auto_ack=auto_ack,
            releaseCondition=release_condition)

    def request_data_point(self, key):
        return self.tagPoints[key].value

    def set_config_option(self, key, value):
        self.setDataKey(key, value)

    def set_config_default(self, key: str, value: str):
        """sets an option in self.config if it does not exist or is blank. used for subclassing as you may want to persist.

         Calls into set_config_option, you should not need to subclass this.
        """

        if key not in self.config or not self.config[key].strip():
            self.set_config_option(key, value.strip())

    def handle_error(self, e: str, title=''):
        self.handle_error(e)

    def on_data_change(self, name: str, value, timestamp: float, annotation):
        """used for subclassing, this is how you watch for data changes.
            Kaithem does not need this, we have direct observable tag points.
        """
        pass

    # Lifecycle

    def onDelete(self):
        self.on_delete()

    def on_delete(self):
        pass

    # FS

    def framework_storage_root(self):
        return directories.vardir

    # UI Integration

    def on_ui_message(self, msg: Union[float, int, str, bool, None, dict,
                                       list], **kw):
        """recieve a json message from the ui page.  the host is responsible for providing a send_ui_message(msg)
        function to the manage and create forms, and a set_ui_message_callback(f) function.

        these messages are not directed at anyone in particular, have no semantics, and will be recieved by all
        manage forms including yourself.  they are only meant for very tiny amounts of general interest data and fast commands.

        this lowest common denominator approach is to ensure that the ui can be fully served over mqtt if desired.

        """

    def send_ui_message(self, msg: Union[float, int, str, bool, None, dict,
                                         list]):
        """
        send a message to everyone including yourself.
        """
        self._admin_ws_channel.send(msg)

    def get_management_form(self) -> Optional[str]:
        """must return a snippet of html suitable for insertion into a form tag, but not the form tag itself.
        the host application is responsible for implementing the post target, the authentication, etc.

        when the user posts the form, the config options will be used to first close the device, then build 
        a completely new device.

        the host is responsible for the name and type parts of config, and everything other than the device.* keys.
        """
        return ''

    def getManagementForm(self, **kw):
        return self.get_management_form()

    @classmethod
    def getCreateForm(cls, **kwargs) -> Optional[str]:
        """must return a snippet of html used the same way as get_management_form, but for creating brand new devices"""
        return cls.get_create_form(**kwargs)

    def print(self, msg, title="Message"):
        "Print a message to the Device's management page"
        t = textwrap.fill(str(msg), 120)
        tm = unitsofmeasure.strftime(time.time())

        # Can't use a def here, wouldn't want it to possibly capture more than just a string,
        # And keep stuff from GCIng for too long
        workers.do(makeBackgroundPrintFunction(t, tm, title, self))

    def handle_exception(self):
        try:
            self.handle_error(traceback.format_exc(chain=True))
        except:
            print(traceback.format_exc())

    @classmethod
    def discoverDevices(cls,
                        config: Dict[str, str] = {},
                        current_device: Optional[object] = None,
                        intent="",
                        **kwargs) -> Dict[str, Dict]:
        "CamelCase compatibility"
        return cls.discover_devices(config=config,
                                    current_device=current_device,
                                    intent=intent,
                                    kwargs=kwargs)

    @staticmethod
    def validateData(*a, **k):
        return True

    #######################################################################################


# Device data always has 2 constants. 1 is the required type, the other
# is name, and that's optional but can be used to rename a device
def updateDevice(devname, kwargs, saveChanges=True):

    # The NEW name, which could just be the old name
    name = kwargs.get('name', None) or devname

    if name not in kwargs:
        kwargs['name'] = name

    ib = kwargs.pop("temp.kaithem.inputbindings", None)
    if ib:
        # Delete empty. We may need empty thanks to very very annoying ui lib bugs
        kwargs['kaithem.input_bindings'] = [
            i for i in json.loads(ib) if i[0] or i[2]
        ]

    ib = kwargs.pop("temp.kaithem.outputbindings", None)
    if ib:
        # Delete empty. We may need empty thanks to very very annoying ui lib bugs
        kwargs['kaithem.output_bindings'] = [
            i for i in json.loads(ib) if i[0] or i[1]
        ]

    raw_dt = getDeviceType(kwargs['type'])
    if hasattr(raw_dt, "validateData"):
        raw_dt.validateData(kwargs)

    old_bindings = {}
    old_read_perms = {}
    old_write_perms = {}

    subdevice = False

    with modules_state.modulesLock:

        if devname in device_data:
            # Not the same as currently being a subdevice. We have placeholders to edit subdevices that don't exist.
            configuredAsSubdevice = device_data[devname].get(
                'is_subdevice', False) in ('true', True, 'True', 'yes', 'Yes', 1, '1')
        if devname in remote_devices:

            subdevice = hasattr(
                remote_devices[devname], "_kaithem_is_subdevice")

            parentModule = remote_devices[devname].parentModule
            parentResource = remote_devices[devname].parentResource
            old_bindings = remote_devices[devname].config.get(
                "kaithem.input_bindings", [])

            old_obindings = remote_devices[devname].config.get(
                "kaithem.output_bindings", [])

            old_read_perms = remote_devices[devname].config.get(
                "kaithem.read_perms", [])

            old_write_perms = remote_devices[devname].config.get(
                "kaithem.write_perms", [])

            if not subdevice:
                remote_devices[devname].close()
                messagebus.post_message("/devices/removed/", devname)

            # Delete and then recreate because we may be renaming to a different name

            if not parentModule:
                del device_data[devname]
            else:
                del modules_state.ActiveModules[parentModule][
                    parentResource]

        else:
            raise RuntimeError("No such device to update")

        gc.collect()
        time.sleep(0.01)
        time.sleep(0.01)
        gc.collect()

        d = {i: kwargs[i] for i in kwargs if (
            not i.startswith('temp.') and not i.startswith('filedata.'))}

        # Propagate subdevice status even if it is just loaded as a placeholder
        if configuredAsSubdevice or subdevice:
            d['is_subdevice'] = True

        # allow forms that don't have the whole binding widget
        if 'kaithem.input_bindings' not in d:
            d['kaithem.input_bindings'] = old_bindings

        if 'kaithem.output_bindings' not in d:
            d['kaithem.output_bindings'] = old_obindings

        if 'kaithem.read_perms' not in d:
            d['kaithem.read_perms'] = old_read_perms or ''

        if 'kaithem.write_perms' not in d:
            d['kaithem.write_perms'] = old_write_perms or ''

        fd = {i: kwargs[i] for i in kwargs if i.startswith('filedata.')}

        for i in fd:
            i2 = i[len('filedata.'):]

            fl = getDeviceConfigFolder(name)

            do = False
            with open(os.path.join(fl, i2), "r") as f:
                if not f.read() == kwargs[i]:
                    do = True

            if do:
                with open(os.path.join(fl, i2), "w") as f:
                    f.write(kwargs[i])

        if parentModule:
            modules_state.ActiveModules[parentModule][
                parentResource] = {
                    'resource-type': 'device',
                    "device": d
            }

            modules_state.saveResource(
                parentModule, parentResource, {
                    'resource-type': 'device',
                    "device": d
                })
            modules_state.modulesHaveChanged()

        else:
            # Allow name changing via data, we save under new, not the old name
            device_data[name] = d
            saveDevice(name)

        if not subdevice:
            remote_devices[name] = makeDevice(name, kwargs, parentModule,
                                              parentResource)
        else:
            kwargs['is_subdevice'] = 'true'

            # Don't pass our special internal keys to that mechanism that expects to only see standard iot_devices keys.
            k = {i: kwargs[i] for i in kwargs if not i.startswith('kaithem')}
            remote_devices[name].update_config(k)

            configureInputBindings(remote_devices[name])

        global remote_devices_atomic
        remote_devices_atomic = wrcopy(remote_devices)
        messagebus.post_message("/devices/added/", name)


def url(u):
    return urllib.parse.quote(u, safe='')


def devStatString(d):
    "Misc status info that we can gather from the device typy"
    s = []

    if 'status' in d.tagPoints:
        s.append(str(d.tagPoints['status']())[:32])

    try:
        if len(d.tagPoints) < 14:
            for i in d.tagPoints:
                if hasattr(d.tagPoints[i], 'meterWidget'):
                    if d.tagPoints[i].type == "number":
                        s.append(d.tagPoints[i].meterWidget.render_oneline(
                            label=i + ": "))

        else:
            if 'rssi' in d.tagPoints:
                s.append(d.tagPoints['rssi'].meterWidget.render_oneline(
                    label="RSSI: "))
            if 'battery' in d.tagPoints:
                s.append(d.tagPoints['battery'].meterWidget.render_oneline(
                    label="Battery: "))
            if 'powered' in d.tagPoints:
                s.append(d.tagPoints['powered'].meterWidget.render_oneline(
                    label="Powered: "))

            if 'switch' in d.tagPoints:
                s.append(d.tagPoints['switch'].meterWidget.render_oneline(
                    label="Switch: "))
            if 'running' in d.tagPoints:
                s.append(d.tagPoints['running'].meterWidget.render_oneline(
                    label="Running: "))
            if 'record' in d.tagPoints:
                s.append(d.tagPoints['record'].meterWidget.render_oneline(
                    label="Recording: "))
            if 'temperature' in d.tagPoints:
                s.append(d.tagPoints['temperature'].meterWidget.render_oneline(
                    label="Temperature: "))
            if 'humidity' in d.tagPoints:
                s.append(d.tagPoints['humidity'].meterWidget.render_oneline(
                    label="Humidity: "))
            if 'uv_index' in d.tagPoints:
                s.append(d.tagPoints['uv_index'].meterWidget.render_oneline(
                    label="UV Index: "))
            if 'wind' in d.tagPoints:
                s.append(d.tagPoints['wind'].meterWidget.render_oneline(
                    label="Wind: "))

            if 'open' in d.tagPoints:
                s.append(d.tagPoints['open'].meterWidget.render_oneline(
                    label="Open: "))

            if 'on' in d.tagPoints:
                s.append(
                    d.tagPoints['on'].meterWidget.render_oneline(label="On: "))

            if 'leak' in d.tagPoints:
                s.append(d.tagPoints['leak'].meterWidget.render_oneline(
                    label="Leak: "))

    except Exception as e:
        s.append(str(e))

    return ''.join([i for i in s])


def url(u):
    return urllib.parse.quote(u, safe='')


def read(f):
    try:
        with open(f) as fd:
            return fd.read()
    except Exception:
        return ""


specialKeys = {

    'subclass',
    'name',
    'title',
    'type',
    'is_subdevice',
    'description',
    'notes'
}


def getshownkeys(obj: Device):
    return sorted([i for i in obj.config.keys() if i not in specialKeys and not i.startswith("kaithem.")])


device_page_env = {
    "specialKeys": specialKeys,
    "read": read,
    "url": url,
    "hasattr": hasattr
}


def render_device_tag(obj, tag):
    try:
        return pages.render_jinja_template("devices/device_tag_component.j2.html", i=tag, obj=obj)
    except Exception as e:
        return f"<article>{e}</article>"


class WebDevices():
    @cherrypy.expose
    def index(self):
        """Index page for web interface"""
        pages.require("/admin/settings.edit")
        cherrypy.response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        return pages.get_template("devices/index.html").render(
            deviceData=remote_devices_atomic, devStatString=devStatString, url=url)

    @cherrypy.expose
    def device(self, name, *args, **kwargs):
        # This is a customizable per-device page
        if args and args[0] == 'web':
            if kwargs:
                # Just don't allow gets that way
                pages.postOnly()
            try:
                return remote_devices[name].webHandler(*args[1:], **kwargs)
            except pages.ServeFileInsteadOfRenderingPageException as e:
                return cherrypy.lib.static.serve_file(e.f_filepath, e.f_MIME,
                                                      e.f_name)

        if args and args[0] == 'manage':
            pages.require("/admin/settings.edit")

            # Some framework only keys are not passed to the actual device since we use what amounts
            # to an extension, so we have to merge them in
            merged = {}

            obj = remote_devices[name]
            if name in device_data:
                merged.update(device_data[name])

            if obj.parentModule:
                from . import modules_state
                merged.update(modules_state.ActiveModules[
                    obj.parentModule][obj.parentResource]['device'])

            # I think stored data is enough, this is just defensive
            merged.update(remote_devices[name].config)

            mf = ''
            # LEGACY kaithem specific stuff
            if hasattr(obj, "getManagementForm"):
                try:
                    mf = obj.getManagementForm()
                except Exception:
                    logging.exception("?")

            return pages.render_jinja_template("devices/device.j2.html",
                                               data=merged, obj=obj, manageForm=mf,
                                               name=name, args=args, kwargs=kwargs, title='' if obj.title == obj.name else obj.title, **device_page_env)
        if not args:
            raise cherrypy.HTTPRedirect(cherrypy.url() + "/manage")

    @cherrypy.expose
    def devicedocs(self, name):
        pages.require("/admin/settings.edit")
        x = remote_devices[name].readme

        if x is None:
            x = "No readme found"
        if x.startswith("/") or (len(x) < 1024 and os.path.exists(x)):
            with open(x) as f:
                x = f.read()

        return pages.get_template("devices/devicedocs.html").render(docs=x)

    @cherrypy.expose
    def updateDevice(self, devname, **kwargs):
        pages.require("/admin/settings.edit")
        pages.postOnly()
        updateDevice(devname, kwargs)
        raise cherrypy.HTTPRedirect("/devices")

    @cherrypy.expose
    def discoveryStep(self, type, devname, **kwargs):
        """
            Do a step of iterative device discovery.  Can start either from just a type or we can take
            an existing device config and ask it for refinements.
        """
        pages.require("/admin/settings.edit")
        pages.postOnly()
        cherrypy.response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        current = kwargs

        if devname and devname in remote_devices:
            # If possible just use the actual object
            d = remote_devices[devname]
            c = copy.deepcopy(d.data)
            c.update(kwargs)
            current = c
            obj = d
        else:
            obj = None
            d = getDeviceType(type)

        # We don't have pt adapter layer with raw classes
        if hasattr(d, "discoverDevices"):
            d = d.discoverDevices(current,
                                  current_device=remote_devices.get(
                                      devname, None),
                                  intent="step")
        else:
            d = d.discover_devices(current,
                                   current_device=remote_devices.get(
                                       devname, None),
                                   intent="step")

        return pages.get_template("devices/discoverstep.html").render(
            data=d, current=current, name=devname, obj=obj)

    @cherrypy.expose
    def createDevice(self, name=None, **kwargs):
        "Actually create the new device"
        pages.require("/admin/settings.edit")
        pages.postOnly()
        cherrypy.response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        name = name or kwargs.get('name', None)
        m = r = None
        with modules_state.modulesLock:
            if 'module' in kwargs:
                m = kwargs['module']
                r = kwargs['resource']
                name = m + "/" + r
                del kwargs['module']
                del kwargs['resource']
                d = {i: kwargs[i] for i in kwargs if not i.startswith('temp.')}

                # Set these as the default
                kwargs['kaithem.read_perms'] = "/users/devices.read"
                kwargs['kaithem.write_perms'] = "/users/devices.write"

                modules_state.ActiveModules[m][r] = {
                    'resource-type': 'device',
                    'device': d
                }
                modules_state.modulesHaveChanged()
            else:
                if not name:
                    raise RuntimeError("No name?")
                d = {
                    i: str(kwargs[i])
                    for i in kwargs if not i.startswith('temp.')
                }
                device_data[name] = d

            if name in remote_devices:
                remote_devices[name].close()
            remote_devices[name] = makeDevice(name, kwargs, m, r)
            global remote_devices_atomic
            remote_devices_atomic = wrcopy(remote_devices)
            messagebus.post_message("/devices/added/", name)

        saveDevice(name)

        raise cherrypy.HTTPRedirect("/devices")

    @cherrypy.expose
    def customCreateDevicePage(self, name, module='', resource='', **kwargs):
        "Ether create a 'blank' device, or, if supported, show the custom page"
        pages.require("/admin/settings.edit")
        pages.postOnly()
        cherrypy.response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        tp = getDeviceType(kwargs['type'])

        if hasattr(tp, "getCreateForm"):
            createForm = tp.getCreateForm()
        else:
            createForm = ""

        return pages.get_template("devices/createpage.html").render(
            customForm=createForm,
            name=name,
            type=kwargs['type'],
            module=module,
            resource=resource)

    @cherrypy.expose
    def deleteDevice(self, name, **kwargs):
        pages.require("/admin/settings.edit")
        cherrypy.response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        name = name or kwargs['name']
        return pages.get_template("devices/confirmdelete.html").render(
            name=name)

    @cherrypy.expose
    def toggletarget(self, name, **kwargs):
        pages.postOnly()
        x = remote_devices[name]

        perms = x.config.get(
            "kaithem.write_perms", '').strip() or "/admin/settings.edit"

        for i in perms.split(","):
            pages.require(i)

        if 'switch' in x.tagpoints:
            x.tagpoints['switch'].value = (
                1 if not x.tagpoints['switch'].value else 0)

    @cherrypy.expose
    def settarget(self, name, tag, value='', **kwargs):
        pages.postOnly()
        x = remote_devices[name]

        perms = x.config.get(
            "kaithem.write_perms", '').strip() or "/admin/settings.edit"

        for i in perms.split(","):
            pages.require(i)

        if tag in x.tagpoints:
            x.tagpoints[tag].value = value

    @cherrypy.expose
    def dimtarget(self, name, tag, value='', **kwargs):
        "Set a color tagpoint to a dimmed version of it."
        pages.postOnly()
        x = remote_devices[name]

        perms = x.config.get(
            "kaithem.write_perms", '').strip() or "/admin/settings.edit"

        for i in perms.split(","):
            pages.require(i)

        if tag in x.tagpoints:
            try:
                x.tagpoints[tag].value = (colorzero.Color.from_string(
                    x.tagpoints[tag].value) * colorzero.Luma(value)).html
            except Exception:
                x.tagpoints[tag].value = (colorzero.Color.from_rgb(
                    1, 1, 1) * colorzero.Luma(value)).html

    @cherrypy.expose
    def triggertarget(self, name, tag, **kwargs):
        pages.postOnly()
        x = remote_devices[name]

        perms = x.config.get(
            "kaithem.write_perms", '').strip() or "/admin/settings.edit"

        for i in perms.split(","):
            pages.require(i)

        if tag in x.tagpoints:
            x.tagpoints[tag].value = x.tagpoints[tag].value + 1

    @cherrypy.expose
    def deletetarget(self, **kwargs):
        pages.require("/admin/settings.edit")
        pages.postOnly()
        name = kwargs['name']
        with modules_state.modulesLock:
            x = remote_devices[name]
            k = []
            for i in x.subdevices:
                k.append(subdevices[i].name)

            x.close()
            gc.collect()
            x.onDelete()
            gc.collect()

            for i in k:
                try:
                    del remote_devices[i]
                except KeyError:
                    pass
                try:
                    del device_data[i]
                except KeyError:
                    pass

            try:
                del remote_devices[name]
            except KeyError:
                pass

            try:
                del device_data[name]
            except KeyError:
                pass

            if x.parentModule:
                r = modules_state.ActiveModules[x.parentModule][
                    x.parentResource]

                del modules_state.ActiveModules[x.parentModule][
                    x.parentResource]

                modules_state.modulesHaveChanged()

                fn = modules_state.getResourceFn(
                    x.parentModule, x.parentResource, r)

                if os.path.exists(fn):
                    os.remove(fn)

            # no zombie reference
            del x

            global remote_devices_atomic
            remote_devices_atomic = wrcopy(remote_devices)
            # Gotta be aggressive about ref cycle breaking!
            gc.collect()
            time.sleep(0.1)
            gc.collect()
            time.sleep(0.2)
            gc.collect()

            saveDevice(name)
            messagebus.post_message("/devices/removed/", name)

        raise cherrypy.HTTPRedirect("/devices")


builtinDeviceTypes = {'device': Device}
deviceTypes = weakref.WeakValueDictionary()


class DeviceNamespace():
    deviceTypes = deviceTypes
    Device = Device

    def __getattr__(self, name):
        if not name.startswith("__"):
            if remote_devices[name].device_type_name == "unsupported":
                raise RuntimeError("There is no driver for this device")
            return weakref.proxy(remote_devices[name])

    def __getitem__(self, name):
        if remote_devices[name].device_type_name == "unsupported":
            raise RuntimeError("There is no driver for this device")
        return weakref.proxy(remote_devices[name])

    def __iter__(self):
        x = remote_devices_atomic
        return (i for i in x if not x[i]().device_type_name == 'unsupported')


class DeviceTypeLookup():
    def __getitem__(self, k):
        if k in builtinDeviceTypes:
            dt = builtinDeviceTypes[k]
        elif k in ("", 'device', 'Device'):
            dt = Device
        return dt


devicesByModuleAndResource = weakref.WeakValueDictionary()


def wrapCrossFramework(dt2, desc):
    # We can't use the class as-is, because it uses the default very simple implementations of things.
    # So we customize it using Device.

    # Due to C3 linearization, Device takes precedence over dt's ancestors.
    class ImportedDeviceClass(CrossFrameworkDevice, dt2):
        # Adapt from the cross-framework spec to the internal spec
        device_type_name = dt2.device_type
        readme = dt2.readme

        description = desc
        pass

        def __init__(self, name, data, **kw):
            # We have to call ours first because we need things like the tag points list
            # to be able to do the things theirs could call
            self.metadata = {}
            Device.__init__(self, name, data, **kw)
            CrossFrameworkDevice.__init__(self, name, data, **kw)
            # Ensure we don't lose any data should the base class ever set any new keys
            dt2.__init__(self, name, self.config, **kw)

        def close(self, *a, **k):
            with modules_state.modulesLock:
                for i in list(self.subdevices.keys()):
                    self.subdevices[i].close()
                    if self.subdevices[i].name in remote_devices:
                        del remote_devices[self.subdevices[i].name]
                    del self.subdevices[i]

                global remote_devices_atomic
                remote_devices_atomic = wrcopy(remote_devices)

            gc.collect()
            time.sleep(0.01)
            gc.collect()
            time.sleep(0.03)
            gc.collect()

            dt2.close(self, *a, **k)
            # Our internal device close.  The plugin should call the iot_devices close itself
            Device.close(self, *a, **k)

    return ImportedDeviceClass


def makeDevice(name, data, module=None, resource=None, cls=None):
    err = None
    desc = ''

    data = copy.deepcopy(data)

    # Cls lets us force make a device of a different type for placeholders if we can't support them yet
    if cls:
        data['name'] = name
        data['type'] = cls.device_type

    if data['type'] in builtinDeviceTypes:
        dt = builtinDeviceTypes[data['type']]
    elif data['type'] in ("", 'device', 'Device'):
        dt = Device
    elif data['type'] in deviceTypes:
        dt = deviceTypes[data['type']]
    else:

        try:
            dt2 = cls or iot_devices.host.get_class(data)

            if not dt2:
                raise ValueError("Couldn't get class")
            try:
                desc = iot_devices.host.get_description(data['type'])
            except Exception:
                log.exception("err getting description")

            dt = wrapCrossFramework(dt2, desc)

        except KeyError:
            dt = UnsupportedDevice
        except ValueError:
            dt = UnsupportedDevice
        except Exception:
            dt = UnsupportedDevice
            log.exception("Err creating device")
            err = traceback.format_exc()

    new_data = copy.deepcopy(data)
    new_data.pop("framework_data", None)

    # Don't pass framewith specific stuff to them.
    # Except a whitelist of known short string only keys that we need to easily access from
    # within the device integration code
    new_data = {
        i: new_data[i]
        for i in new_data if not (i.startswith("kaithem.") and not i in ('kaithem.read_perms', "kaithem.write_perms"))
    }

    try:
        d = dt(name, new_data)
    except Exception:
        d = UnsupportedDevice(name, new_data)
        d.handleException()

    if err:
        d.handle_error(err)

    if module:
        d.parentModule = module
        d.parentResource = resource
        devicesByModuleAndResource[module, resource] = d

        # In case something changed during initializatiion before we set it
        # flush the changes back to the modules object if applicable
        with modules_state.modulesLock:
            modules_state.ActiveModules[d.parentModule][
                d.parentResource] = {
                    'resource-type': 'device',
                    'device': d.config
            }

            modules_state.saveResource(
                d.parentModule, d.parentResource, {
                    'resource-type': 'device',
                    "device": d.config
                })
            modules_state.modulesHaveChanged()

    try:
        configureInputBindings(d)
    except Exception:
        d.handleException()

    return d


def doOutputBinding(tag, dest, annotation):
    if not hasattr(tag, '_kOutputBindings'):
        tag._kOutputBindings = []

    def f(v, t, a):
        if dest in tagpoints.allTagsAtomic:

            d = tagpoints.allTagsAtomic[dest]

            # For triggers, don't copy the raw value, increase the destination's value by 1.
            if d.subtype == 'trigger':
                v = d.value + 1

            d(v, t, annotation)

    tag._kOutputBindings.append[f]


def configureInputBindings(d):
    data = d.config
    needSet = 0
    for i in data.get("kaithem.input_bindings", []):
        if not i[0].strip():
            continue

        t = d.tagPoints.get(i[0], None)
        xt = tagpoints.allTagsAtomic.get(i[2], None)
        t = (t or xt)
        if not i[1].strip():
            if t:
                needSet = 1
                if isinstance(t, weakref.ref):
                    t = t()
                i[1] = t.type
            else:
                raise ValueError("Can't guess type for binding to: " +
                                 i[0])

    if hasattr(d, "_kBindings"):
        for i in d._kBindings:
            try:
                d._kBindings[i].unsubscribe(d.tagPoints[i])
            except Exception:
                log.exception(
                    "Could not unsub. Maybe was never created.")

    for i in d.tagPoints:
        t = d.tagPoints[i]

        if hasattr(t, "_kOutputBindings"):
            for i in t._kOutputBindings:
                try:
                    t.unsubscribe[i]
                except Exception:
                    log.exception(
                        "Could not unsub. Maybe was never created.")

        t._kOutputBindings = []

    for i in data.get("kaithem.input_bindings", []):
        if not i[0].strip():
            continue

        # Can always do this later
        if i[0] in d.tagPoints:
           # Do the setter right away if the tag has data
            doOutputBinding(d.tagPoints[i[0]], i[1],
                            "Set by device: " + d.name)

        else:
            if not hasattr(d, "_isCrossFramework"):
                d.handle_error(
                    "Binding to a data point that the local device doesn't have yet will only work with newer cross-framework devices."
                )

    for i in data.get("kaithem.output_bindings", []):
        if not i[0].strip():
            continue

        if i[0] in d.tagPoints:
            t = d.tagPoints[i[0]]

        else:
            if not hasattr(d, "_isCrossFramework"):
                d.handle_error(
                    "Binding to a data point that the local device doesn't have yet will only work with newer cross-framework devices."
                )

        if t.type == 'numeric' or t.type == 'number':
            t = tagpoints.Tag(i[2])

        if t.type == 'string':
            t = tagpoints.StringTag(i[2])

        if t.type == 'object':
            t = tagpoints.ObjectTag(i[2])

        d._kBindings[i[0]] = t

        # Can always do this later
        if i[0] in d.tagPoints:
            # Do the setter right away if the tag has data
            t.subscribe(d.tagPoints[i[0]], immediate=(
                not t.subtype == 'trigger'))
        else:
            if not hasattr(d, "_isCrossFramework"):
                d.handle_error(
                    "Binding to a data point that the local device doesn't have yet will only work with newer cross-framework devices."
                )

    if needSet:
        # Set the data if we auto-filled the type
        d.setObject("kaithem.input_bindings",
                    data.get("kaithem.input_bindings", []))


def getDeviceType(t):
    if t in builtinDeviceTypes:
        return builtinDeviceTypes[t]
    elif t in deviceTypes:
        return deviceTypes[t]
    else:
        try:
            t = iot_devices.host.get_class({'type': t})
            return t or UnsupportedDevice
        except Exception:
            log.exception("Could not look up class")
            return UnsupportedDevice


class TemplateGetter():
    def __init__(self, fn):
        self.fn = fn

    def __get__(self, instance, owner):
        return lambda: pages.get_vardir_template(self.fn).render(
            data=instance.config, obj=instance, name=instance.name)


deviceTypesFromData = {}


def loadDeviceType(root, i):
    name = i[:-3]
    fn = os.path.join(root, i)
    with open(fn) as f:
        d = f.read()

    # Avoid circular imports, kaithemobj basically depends on everything
    from . import kaithemobj
    codeEvalScope = {
        "Device": Device,
        'kaithem': kaithemobj.kaithem,
        'deviceTypes': DeviceTypeLookup()
    }
    exec(compile(d, "Driver_" + name, 'exec'), codeEvalScope, codeEvalScope)

    # Remove anything in parens
    realname = re.sub(r'\(.*\)', '', name).strip()
    dt = codeEvalScope[realname]
    # Fix missing devicetypename
    dt.device_type_name = realname
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
    global remote_devices_atomic
    for i in list(device_data.keys()):

        cls = None

        # Force it to be a placeholder subdevice
        if device_data[i].get('is_subdevice', False) in ('true', True, 'True', 'yes', 'Yes', 1, '1'):
            cls = UnusedSubdevice

        # We can call this again to reload unsupported devices.
        if i in remote_devices and not remote_devices[
                i].device_type_name == "unsupported":
            continue

        try:
            # Don't overwrite subdevice with placeholder
            if not i in remote_devices:
                # No module or resource here
                remote_devices[i] = makeDevice(i, device_data[i], cls=cls)
            syslogger.info("Created device from config: " + i)
        except Exception:
            messagebus.post_message(
                "/system/notifications/errors",
                "Error creating device: " + i + "\n" + traceback.format_exc())
            syslogger.exception("Error initializing device " + str(i))

    remote_devices_atomic = wrcopy(remote_devices)


unsupportedDevices = weakref.WeakValueDictionary()


def fixUnsupported():
    "For all placeholder unsupported devices, let's see if we can fix them with a newly set up driver"
    global remote_devices_atomic
    with modules_state.modulesLock:
        # Small optimization here
        if not unsupportedDevices:
            return
        s = 0
        for i in list(remote_devices.keys()):
            if remote_devices[i].device_type_name == 'unsupported':
                d = remote_devices[i]
                remote_devices[i] = makeDevice(i, d.config, d.parentModule,
                                               d.parentResource)
                if not remote_devices[i].device_type_name == 'unsupported':
                    s += 1
        if s:
            remote_devices_atomic = wrcopy(remote_devices)


def warnAboutUnsupportedDevices():
    x = remote_devices_atomic
    for i in x:
        if x[i]().device_type_name() == "unsupported":
            try:
                x[i].warn()
            except Exception:
                syslogger.exception(
                    "Error warning about missing device support device " +
                    str(i))


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
                except Exception:
                    messagebus.post_message(
                        "/system/notifications/errors",
                        "Error with device driver :" + i[1] + "\n" +
                        traceback.format_exc(chain=True))

        else:
            os.mkdir(driversLocation)
    except Exception:
        messagebus.post_message(
            "/system/notifications/errors",
            "Error with device drivers:\n" + traceback.format_exc(chain=True))

    createDevicesFromData()


importedDeviceTypes = iot_devices.host.discover()
