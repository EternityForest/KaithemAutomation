# mypy: import-untyped=False
# pyright: reportIncompatibleMethodOverride=false
from __future__ import annotations

import copy
import gc
import os
import shutil
import textwrap
import time
import traceback
import weakref
from collections.abc import Callable
from typing import Any

import iot_devices.device
import iot_devices.host
import structlog

# SPDX-FileCopyrightText: Copyright 2018 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
from . import (
    alerts,
    directories,
    messagebus,
    modules_state,
    pages,
    tagpoints,
    unitsofmeasure,
    widgets,
    workers,
)
from .modules_state import ResourceType, additionalTypes

SUBDEVICE_SEPARATOR = "/"

# Our lock to be the same lock as the modules lock otherwise there would be too may easy ways to make a deadlock, we have to be able to
# edit the state because self modifying devices exist and can be saved in a module
logger = structlog.get_logger(__name__)

remote_devices: dict[str, Device] = {}
remote_devices_atomic: dict[str, weakref.ref[Device]] = {}

# Data awaiting someone to use it for making a subevice
subdevice_data_cache: dict[str, dict[str, Any]] = {}

# Stores the (module, resource) or subdevices that might not yet exist but have config
# Since it needs to work
device_location_cache: dict[str, tuple[str, str]] = {}

saveLocation = os.path.join(directories.vardir, "devices")

driversLocation = os.path.join(directories.vardir, "devicedrivers")


recent_scanned_tags = {}

# Used by device tag j2 template
callable = callable


load_order: list[weakref.ref[Device]] = []


def delete_bookkeep(name, confdir=False):
    with modules_state.modulesLock:
        # It sometimes is not there if the parent device got deleted first
        if name in remote_devices:
            x = remote_devices[name]
            k = []
            for i in x.subdevices:
                k.append(x.subdevices[i].name)

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
                    del subdevice_data_cache[i]
                except KeyError:
                    pass
                try:
                    del device_location_cache[i]
                except KeyError:
                    pass
            try:
                del remote_devices[name]
            except KeyError:
                pass

            pm = x.parent_module
            pr = x.parent_resource

            if confdir:
                try:
                    old_dev_conf_folder = get_config_folder_from_info(
                        pm, pr, name, create=False, always_return=True
                    )
                    if old_dev_conf_folder and os.path.isdir(
                        old_dev_conf_folder
                    ):
                        if not old_dev_conf_folder.count("/") > 3:
                            # Basically since rmtree is so dangerous we make sure
                            # it absolutely cannot be any root or nearly root level folder
                            # in the user's home dir even if some unknown future error happens.
                            # I have no reason to think this will ever actually be needed.
                            raise RuntimeError(
                                f"Defensive check failed: {old_dev_conf_folder}"
                            )

                        shutil.rmtree(old_dev_conf_folder)
                except Exception:
                    logger.exception("Err deleting conf dir")

            # no zombie reference
            del x

        try:
            del remote_devices[name]
        except KeyError:
            pass

        try:
            del subdevice_data_cache[name]
        except KeyError:
            pass
        try:
            del device_location_cache[name]
        except KeyError:
            pass

        global remote_devices_atomic
        remote_devices_atomic = wrcopy(remote_devices)
        # Gotta be aggressive about ref cycle breaking!
        gc.collect()
        time.sleep(0.1)
        gc.collect()
        time.sleep(0.2)

        gc.collect()
        messagebus.post_message("/devices/removed/", name)


def log_scanned_tag(v: str, *args):
    recent_scanned_tags[v] = time.time()
    if len(recent_scanned_tags) > 15:
        recent_scanned_tags.pop(next(iter(recent_scanned_tags)))


dbgd: weakref.WeakValueDictionary[str, Device] = weakref.WeakValueDictionary()


def closeAll(*a):
    global load_order
    with modules_state.modulesLock:
        for i in reversed(load_order):
            x = i()
            if x:
                try:
                    x.close()
                except Exception:
                    logger.exception("Error in shutdown cleanup")


finished_reading_resources = False
deferred_loaders = []


class DeviceResourceType(ResourceType):
    def on_finished_loading(self, module):
        if module is None:
            init_devices()
            global finished_reading_resources
            finished_reading_resources = True

    def on_load(self, module, resource, data):
        cls = None

        dev_data = data["device"]
        assert isinstance(dev_data, dict)

        # It's a subdevice, we don't actually make the real thing
        if dev_data.get("is_subdevice", False) in (
            "true",
            True,
            "True",
            "yes",
            "Yes",
            1,
            "1",
        ):
            cls = UnusedSubdevice

        if dev_data.get("parent_device", ""):
            cls = UnusedSubdevice

        assert isinstance(dev_data, dict)

        # We may want to store a device in a shortened resource name
        # because of / issues.
        if "name" in dev_data:
            devname = dev_data["name"]
            assert isinstance(devname, str)
        else:
            raise ValueError("No name in device")

        if cls:
            subdevice_data_cache[devname] = dev_data

        device_location_cache[devname] = (module, resource)

        def load_closure():
            with modules_state.modulesLock:
                if devname in remote_devices:
                    assert isinstance(dev_data, dict)
                    # This is a subdevice which already exists as the real thing, not the placeholder.
                    if cls:
                        return
                    else:
                        if (
                            not dev_data["type"]
                            == remote_devices[devname].device_type_name
                        ):
                            raise RuntimeError(
                                "Name in user, can't overwrite this device name with a different type"
                            )
                        remote_devices[devname].close()

                d = makeDevice(devname, dev_data, cls)
                remote_devices[devname] = d
                d.parent_module = module
                d.parent_resource = resource

                global remote_devices_atomic
                remote_devices_atomic = wrcopy(remote_devices)

        # We aren't finished loading all the modules at startup
        # Save it and do everything at once
        if finished_reading_resources:
            load_closure()
        else:
            deferred_loaders.append(load_closure)

    def on_delete(self, module, resource, data):
        with modules_state.modulesLock:
            n = resource.split(SUBDEVICE_SEPARATOR)[-1]
            if "name" in data["device"]:
                n = data["device"]["name"]

            delete_bookkeep(n, True)

    def on_create_request(self, module, resource, kwargs):
        raise RuntimeError("Not implemented, devices uses it's own create page")

    def create_page(self, module, path):
        return pages.get_template("devices/deviceintomodule.html").render(
            module=module, path=path
        )

    def edit_page(self, module, resource, value):
        with modules_state.modulesLock:
            n = resource.split(SUBDEVICE_SEPARATOR)[-1]
            if "name" in value["device"]:
                n = value["device"]["name"]
        return pages.get_template("devices/device.html").render(
            data=remote_devices[n].config, obj=remote_devices[n], name=n
        )


drt = DeviceResourceType("device")
additionalTypes["device"] = drt


def getZombies():
    x = []
    v = remote_devices.values()
    for i in dbgd:
        if dbgd[i] not in v:
            x.append((i, dbgd[i]))
    return x


def get_config_folder_from_device(d: str, create=True):
    if (
        not hasattr(remote_devices[d], "parent_module")
        or not remote_devices[d].parent_module
    ):
        module = None
        resource = None
    else:
        module = remote_devices[d].parent_module
        resource = remote_devices[d].parent_module

    return get_config_folder_from_info(module, resource, d, create=create)


def get_config_folder_from_info(
    module: str | None,
    resource: str | None,
    name: str,
    create=True,
    always_return=False,
):
    if not module:
        saveLocation = os.path.join(
            directories.vardir, "devices", f"{name}.config.d"
        )
    else:
        # or '' makes linker happy, idk why it doesn't detect the if statement.
        saveLocation = os.path.join(
            directories.vardir,
            "modules",
            "data",
            module or "",
            "__filedata__",
            f"{resource or name}.config.d",
        )

    if not os.path.exists(saveLocation):
        if not create:
            if not always_return:
                return None
        else:
            os.makedirs(saveLocation, mode=0o700, exist_ok=True)

    return saveLocation


def wrcopy(x):
    "Copy a dict but replace all vals with weak refs to the value"
    return {i: weakref.ref(x[i]) for i in x}


def makeBackgroundPrintFunction(p, t, title, self):
    def f():
        self.logWindow.write(f"<b>{title} at {t}</b><br>{p}")

    return f


def makeBackgroundErrorFunction(t, time, self):
    # Don't block everything up
    def f():
        self.logWindow.write(
            f'<div class="danger"><b>Error at {time}</b><br><pre>{t}</pre></div>'
        )

    return f


class Device(iot_devices.device.Device):
    ######################################################################################
    # Compatibility block for this spec https://github.com/EternityForest/iot_devices
    # Musy ONLY have things we want to override from the imported driver class,
    # as this will have the highest priority
    # Keep this pretty self contained.  That makes it clear what's a Kaithem feature and
    # what is in the generic spec
    ######################################################################################

    # Alarms are only done via the new tags way with these
    _noset_alarmPriority = True

    _isCrossFramework = True

    description = ""
    readme = ""
    device_type_name = "device"

    # We are renaming data to config for clarity.
    # This is the legacy alias.
    @property
    def data(self):
        return self.config

    @data.setter
    def data(self, v):
        return self.config.update(v)

    def setDataKey(self, key: str, val):
        "Lets a device set it's own persistent stored data"

        v = str(val)

        with modules_state.modulesLock:
            self.config[key] = v

            if (
                not self.config.get("is_ephemeral", False)
                and not key.startswith("temp.")
                and not key.startswith("kaithem.temp.")
            ):
                if self.parent_module:
                    assert self.parent_resource
                    devdata = modules_state.ActiveModules[self.parent_module][
                        self.parent_resource
                    ]["device"]
                    assert isinstance(devdata, dict)
                    devdata[key] = v

                    modules_state.rawInsertResource(
                        self.parent_module,
                        self.parent_resource,
                        modules_state.ActiveModules[self.parent_module][
                            self.parent_resource
                        ],
                    )

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

    def __init__(self, name: str, data: dict[str, Any]):
        if (
            not data["type"] == self.device_type_name
            and not self.device_type_name == "unsupported"
        ):
            raise ValueError(
                "Incorrect device type in info dict,"
                + data["type"]
                + " does not match device_type_name "
                + self.device_type_name
            )
        global remote_devices_atomic
        global remote_devices

        try:
            self.title: str = data.get("title", "").strip() or name
        except Exception:
            self.title = name

        self.k_use_default_alerts = data.get(
            "kaithem.use_default_alerts", "true"
        ).lower() in ("yes", "on", "true", "1")

        # Which points to show in overview
        self.dashboard_datapoints = {}

        self.logWindow = widgets.ScrollingWindow(2500)

        self._tagBookKeepers: dict[str, Callable[[Any, float, Any], None]] = {}

        # The single shared broadcast data channel the spec suggests we have
        self._admin_ws_channel = widgets.APIWidget()
        self._admin_ws_channel.require("system_admin")

        # This is for extra non device specific stuff we add to all devices
        self._generic_ws_channel = widgets.APIWidget()
        self._generic_ws_channel.require("system_admin")

        # Widgets could potentially stay around after this was deleted,
        # because a connection was open. We wouldn't want that to keep this device around when it should not
        # be.
        onMessage = self.makeUIMsgHandler(weakref.ref(self))

        onMessage2 = self.makeGenericUIMsgHandler(weakref.ref(self))

        # I don't think this is actually needed
        self._uiMsgRef = onMessage

        self._admin_ws_channel.attach(onMessage)
        self._generic_ws_channel.attach(onMessage2)

        dbgd[name + str(time.time())] = self

        # If the device is from a module, tells us where
        # None only when we haven't fully set it up.
        # Or when we are a subdevice just kind of floating
        # With no config
        self.parent_module: str | None = None

        # This can exist even without parent module, not doing
        # anything but telling us what the name would be.
        self.parent_resource: str | None = None

        # Time, title, text tuples for any "messages" a device might "print"
        self.messages: list[tuple[float, str, str]] = []

        # This data dict represents all persistent configuration
        # for the alert object.
        self.config = copy.deepcopy(data)

        # This dict cannot be changed, only replaced atomically.
        # It is a list of alert objects. Dict keys
        # may not include special chars besides underscores.

        # It is a list of all alerts "owned" by the device.
        self.alerts: dict[str, alerts.Alert] = {}

        # A list of all the tag points owned by the device
        self.tagPoints: dict[str, tagpoints.GenericTagPointClass[Any]] = {}
        # Where we stash our claims on the tags
        self.tagClaims: dict[str, tagpoints.Claim] = {}

        self._deviceSpecIntegrationHandlers: dict[
            str, Callable[[Any, float, Any], None]
        ] = {}

        # The new devices spec has a way more limited idea of what a data point is.
        self.datapoints: dict[str, Any] = {}

        self.name = data.get("name", None) or name
        # Time, msg
        self.errors: list[tuple[float, str]] = []

        with modules_state.modulesLock:
            remote_devices[name] = self
            remote_devices_atomic = wrcopy(remote_devices)

            global load_order
            load_order.append(weakref.ref(self))
            load_order = load_order[-1000:]

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

    def handle_error(self, s):
        self.errors.append((time.time(), str(s)))

        if self.errors:
            if time.time() > self.errors[-1][0] + 15:
                logger.error(f"in device: {self.name}\n{s}")
            else:
                logger.error(f"in device: {self.name}\n{s}")

        if len(self.errors) > 50:
            self.errors.pop(0)

        workers.do(
            makeBackgroundErrorFunction(
                textwrap.fill(s, 120),
                unitsofmeasure.strftime(time.time()),
                self,
            )
        )
        if len(self.errors) == 1:
            messagebus.post_message(
                "/system/notifications/errors",
                f"First error in device: {self.name}",
            )
            logger.error(f"in device: {self.name}\n{s}")

    def onGenericUIMessage(self, u, v):
        if v[0] == "set":
            if v[2] is not None:
                self.tagPoints[v[1]].value = v[2]

        if v[0] == "fake":
            if v[2] is not None:
                self.tagPoints[v[1]]._k_ui_fake = self.tagPoints[v[1]].claim(
                    v[2], "faked", priority=50.5
                )

            else:
                if hasattr(self.tagPoints[v[1]], "_k_ui_fake"):
                    self.tagPoints[v[1]]._k_ui_fake.release()

        elif v[0] == "refresh":
            self.tagPoints[v[1]].poll()

    # delete a device, it should not be used after this
    def close(self):
        global remote_devices_atomic
        with modules_state.modulesLock:
            if self.name in remote_devices:
                del remote_devices[self.name]
                remote_devices_atomic = wrcopy(remote_devices)

            try:
                del self.tagPoints
            except Exception:
                pass
        try:
            for i in self.alerts:
                try:
                    self.alerts[i].release()
                except Exception:
                    logger.exception("Error releasing alerts")
        except Exception:
            logger.exception("Error releasing alerts")

    def status(self):
        return "norm"

    def print(self, msg, title="Message"):
        "Print a message to the Device's management page"
        t = textwrap.fill(str(msg), 120)
        tm = unitsofmeasure.strftime(time.time())

        # Can't use a def here, wouldn't want it to possibly capture more than just a string,
        # And keep stuff from GCIng for too long
        workers.do(makeBackgroundPrintFunction(t, tm, title, self))

    def get_config_folder(self, create=True):
        return get_config_folder_from_device(self.name, create=create)

    def create_subdevice(self, cls, name: str, config: dict, *a, **k):
        """
        Allows a device to create it's own subdevices.
        """
        if self.config.get("is_subdevice", False):
            raise RuntimeError(
                "Kaithem does not support more than two layers of subdevice"
            )

        global remote_devices_atomic

        originalName = name

        name = self.name + SUBDEVICE_SEPARATOR + name

        config = copy.deepcopy(config)
        config["name"] = name
        config["is_subdevice"] = "true"

        with modules_state.modulesLock:
            if name in remote_devices_atomic:
                tmp = remote_devices_atomic.get(name, None)
                if tmp:
                    n = tmp()
                    if n:
                        if n.device_type_name not in [
                            "UnusedSubdevice",
                            "unsupported",
                        ]:
                            raise RuntimeError(
                                "Subdevice name is already in use"
                            )
                        remote_devices.pop(name)

                        remote_devices_atomic = wrcopy(remote_devices)

            # Mix in user config
            if name in subdevice_data_cache:
                config.update(subdevice_data_cache[name])

        if name not in device_location_cache:
            # TODO what happens with more than two layers?
            # Get rid of the module name part in the resource
            if self.parent_module:
                device_location_cache[name] = (
                    self.parent_module,
                    ".d/".join(
                        name.split("/")[1 if self.parent_module else 0 :]
                    ),
                )

        m = makeDevice(name=name, data=config, cls=cls)

        if name in device_location_cache:
            m.parent_module, m.parent_resource = device_location_cache[name]

        m._kaithem_is_subdevice = True

        with modules_state.modulesLock:
            c2 = copy.deepcopy(config)
            c2.pop("type", cls.device_type)
            self.subdevices[originalName] = m
            remote_devices[name] = m
            remote_devices_atomic = wrcopy(remote_devices)

        return m

    def serve_file(self, fn, mime="", name=None):
        from . import kaithemobj

        return kaithemobj.kaithem.web.serve_file(fn, mime, name)

    def __setupTagPerms(self, t, writable=True):
        # Devices can have a default exposure
        read_perms = (
            self.config.get("kaithem.read_perms", "system_admin").strip()
            or "system_admin"
        )
        write_perms = (
            self.config.get("kaithem.write_perms", "system_admin").strip()
            or "system_admin"
        )
        t.expose(read_perms, write_perms if writable else [])

    def handle_web_request(self, relpath, params, method, **kwargs):
        "To be called by the framework"
        return "No web content here"

    def web_serve_file(self, path, filename=None, mime=None):
        """
        From within your web handler, you can return the result of this to serve that file
        """
        return pages.serveFile(path, mime or "", filename)

    def numeric_data_point(
        self,
        name: str,
        min: float | None = None,
        max: float | None = None,
        hi: float | None = None,
        lo: float | None = None,
        default: float | None = None,
        description: str = "",
        unit: str = "",
        handler: Callable[[float, float, Any], Any] | None = None,
        interval: float = 0,
        writable: bool = True,
        subtype: str = "",
        dashboard: bool = True,
        **kwargs,
    ):
        with modules_state.modulesLock:
            t = tagpoints.Tag(f"/devices/{self.name}.{name}")

            self.__setupTagPerms(t, writable)

            t.min = min
            t.max = max
            t.hi = hi
            t.lo = lo
            t.description = description
            t.unit = unit
            t.default = default or 0
            t.interval = interval
            t.subtype = subtype
            t.writable = writable

            self.dashboard_datapoints[name] = dashboard

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
            self.datapoints[name] = default

            messagebus.post_message("/system/tags/configured", t.name)

    def string_data_point(
        self,
        name: str,
        description: str = "",
        handler: Callable[[str, float, Any], Any] | None = None,
        default: str | None = None,
        interval: float = 0,
        writable: bool = True,
        subtype: str = "",
        dashboard: bool = True,
        **kwargs,
    ):
        with modules_state.modulesLock:
            if "/" in name:
                t = tagpoints.StringTag(f"/devices/{self.name}/{name}")
            else:
                t = tagpoints.StringTag(f"/devices/{self.name}.{name}")

            self.__setupTagPerms(t, writable)
            t.description = description
            t.default = default or ""
            t.interval = interval
            t.subtype = subtype
            t.writable = writable
            self.dashboard_datapoints[name] = dashboard

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
            self.datapoints[name] = ""

            messagebus.post_message("/system/tags/configured", t.name)

    def object_data_point(
        self,
        name: str,
        description: str = "",
        handler: Callable[[dict[str, Any], float, Any], Any] | None = None,
        interval: float = 0,
        writable: bool = True,
        subtype: str = "",
        **kwargs,
    ):
        with modules_state.modulesLock:
            if "/" in name:
                t = tagpoints.ObjectTag(f"/devices/{self.name}/{name}")
            else:
                t = tagpoints.ObjectTag(f"/devices/{self.name}.{name}")

            self.__setupTagPerms(t, writable)
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

            messagebus.post_message("/system/tags/configured", t.name)

    def bytestream_data_point(
        self,
        name: str,
        description: str = "",
        handler: Callable[[bytes, float, Any], Any] | None = None,
        interval: float = 0,
        writable: bool = True,
        subtype: str = "",
        **kwargs,
    ):
        with modules_state.modulesLock:
            if "/" in name:
                t = tagpoints.BinaryTag(f"/devices/{self.name}/{name}")
            else:
                t = tagpoints.BinaryTag(f"/devices/{self.name}.{name}")
            t.unreliable = True

            self.__setupTagPerms(t, writable)
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

            messagebus.post_message("/system/tags/configured", t.name)

    def push_bytes(
        self,
        name,
        value,
    ):
        self.tagPoints[name].fast_push(value, None, None)

    def set_data_point(self, name, value, timestamp=None, annotation=None):
        self.tagPoints[name](value, timestamp, annotation)
        self.datapoints[name] = copy.deepcopy(value)

    def set_data_point_getter(self, name, value):
        # Tag points have this functionality already
        self.tagPoints[name].value = value

    def set_alarm(
        self,
        name: str,
        datapoint: str,
        expression: str,
        priority: str = "info",
        trip_delay: float = 0,
        auto_ack: bool = False,
        release_condition: str | None = None,
        **kw,
    ):
        if not self.k_use_default_alerts:
            return

        x = self.tagPoints[datapoint].set_alarm(
            name,
            condition=expression,
            priority=priority,
            trip_delay=trip_delay,
            auto_ack=auto_ack,
            release_condition=release_condition,
        )
        if x:
            self.alerts[name] = x
        else:
            raise RuntimeError("Alarm setter returned nothing")

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

    def on_data_change(self, name: str, value, timestamp: float, annotation):
        """used for subclassing, this is how you watch for data changes.
        Kaithem does not need this, we have direct observable tag points.
        """

    # Lifecycle

    def onDelete(self):
        self.on_delete()

    # FS

    def framework_storage_root(self):
        return directories.vardir

    # UI Integration

    def on_ui_message(
        self, msg: float | int | str | bool | None | dict | list, **kw
    ):
        """recieve a json message from the ui page.  the host is responsible for providing a window.send_ui_message(msg)
        function to the manage and create forms, and a set_ui_message_callback(f) function.

        these messages are not directed at anyone in particular, have no semantics, and will be recieved by all
        manage forms including yourself.  they are only meant for very tiny amounts of general interest data and fast commands.

        this lowest common denominator approach is to ensure that the ui can be fully served over mqtt if desired.

        """

    def send_ui_message(
        self, msg: float | int | str | bool | None | dict | list
    ):
        """
        send a message to everyone including yourself.
        """
        self._admin_ws_channel.send(msg)

    def get_management_form(self) -> str | None:
        """must return a snippet of html suitable for insertion into a form tag, but not the form tag itself.
        the host application is responsible for implementing the post target, the authentication, etc.

        when the user posts the form, the config options will be used to first close the device, then build
        a completely new device.

        the host is responsible for the name and type parts of config, and everything other than the device.* keys.
        """
        return ""

    def handle_exception(self):
        try:
            self.handle_error(traceback.format_exc(chain=True))
        except Exception:
            print(traceback.format_exc())

    #######################################################################################


class UnsupportedDevice(iot_devices.device.Device):
    description = (
        "This device does not have support, or else the support is not loaded."
    )
    device_type_name = "unsupported"
    device_type = "unsupported"

    def warn(self):
        self.handle_error("This device type has no support.")

    def __init__(self, name, data):
        super().__init__(name, data)
        unsupportedDevices[name] = self


class UnusedSubdevice(iot_devices.device.Device):
    description = "Someone created configuration for a subdevice that is no longer in use or has not yet loaded"
    device_type_name = "UnusedSubdevice"
    device_type = "UnusedSubdevice"

    def warn(self):
        self.handle_error("This device's parent never properly set it up.'")

    def __init__(self, name, data):
        super().__init__(name, data)


# Device data always has 2 constants. 1 is the required type, the other
# is name, and that's optional but can be used to rename a device


def updateDevice(devname, kwargs: dict[str, Any], saveChanges=True):
    # The NEW name, which could just be the old name
    name = kwargs.get("name", None) or devname

    if name not in kwargs:
        kwargs["name"] = name

    old_read_perms = ""
    old_write_perms = ""
    subdevice = False

    with modules_state.modulesLock:
        if kwargs.get("temp.kaithem.store_in_module", None):
            if (
                kwargs["temp.kaithem.store_in_module"]
                not in modules_state.ActiveModules
            ):
                raise ValueError("Can't store in nonexistant module")

            m = kwargs["temp.kaithem.store_in_module"]
            r = kwargs["temp.kaithem.store_in_resource"] or ".d/".join(
                name.split("/")
            )

            if r in modules_state.ActiveModules[m]:
                if (
                    not modules_state.ActiveModules[m][r]["resource_type"]
                    == "device"
                ):
                    raise ValueError(
                        "A resource in the module with that name exists and is not a device."
                    )

                if "module_lock" in modules_state.get_module_metadata(m):
                    raise PermissionError("Module is locked")

                if "resource_lock" in modules_state.ActiveModules[m][r]:
                    raise PermissionError("Device is locked")
            # Make sure we don't corrupt state by putting a folder where a file already is
            ensure_module_path_ok(m, r)
        else:
            raise RuntimeError("You can now only save devices into modules.")

        if devname not in remote_devices:
            raise RuntimeError("No such device to update")

        subdevice = hasattr(remote_devices[devname], "_kaithem_is_subdevice")

        parent_module = remote_devices[devname].parent_module
        parent_resource = remote_devices[devname].parent_resource
        old_dev_conf_folder = get_config_folder_from_info(
            parent_module,
            parent_resource,
            devname,
            create=False,
            always_return=True,
        )

        if "temp.kaithem.store_in_module" in kwargs:
            newparent_module = kwargs["temp.kaithem.store_in_module"]
            newparent_resource = kwargs[
                "temp.kaithem.store_in_resource"
            ] or ".d/".join(name.split("/"))

        else:
            raise ValueError("Can only save in module")

        new_dev_conf_folder = get_config_folder_from_info(
            newparent_module,
            newparent_resource,
            name,
            create=False,
            always_return=True,
        )

        assert parent_module
        assert parent_resource
        dt = modules_state.ActiveModules[parent_module][parent_resource][
            "device"
        ]

        assert isinstance(dt, dict)

        # Not the same as currently being a subdevice. We have placeholders to edit subdevices that don't exist.
        configuredAsSubdevice = dt.get("is_subdevice", False) in (
            "true",
            True,
            "True",
            "yes",
            "Yes",
            1,
            "1",
        )
        configuredAsSubdevice = (
            configuredAsSubdevice or dt.get("parent_device", "").strip()
        )  # type: ignore

        old_read_perms = remote_devices[devname].config.get(
            "kaithem.read_perms", ""
        )

        old_write_perms = remote_devices[devname].config.get(
            "kaithem.write_perms", ""
        )

        if not subdevice:
            remote_devices[devname].close()
            messagebus.post_message("/devices/removed/", devname)

        gc.collect()
        time.sleep(0.01)
        time.sleep(0.01)
        gc.collect()

        savable_data = {
            i: kwargs[i]
            for i in kwargs
            if ((not i.startswith("temp.")) and not i.startswith("filedata."))
        }

        # Propagate subdevice status even if it is just loaded as a placeholder
        if configuredAsSubdevice or subdevice:
            savable_data["is_subdevice"] = True

        if "kaithem.read_perms" not in savable_data:
            savable_data["kaithem.read_perms"] = old_read_perms or ""

        if "kaithem.write_perms" not in savable_data:
            savable_data["kaithem.write_perms"] = old_write_perms or ""

        # Save file data

        fd = {i: kwargs[i] for i in kwargs if i.startswith("filedata.")}

        # handle moved config folder
        if not new_dev_conf_folder == old_dev_conf_folder:
            if new_dev_conf_folder:
                if old_dev_conf_folder and os.path.exists(old_dev_conf_folder):
                    os.makedirs(new_dev_conf_folder, exist_ok=True, mode=0o700)
                    shutil.copytree(
                        old_dev_conf_folder,
                        new_dev_conf_folder,
                        dirs_exist_ok=True,
                    )
                    if not old_dev_conf_folder.count("/") > 3:
                        # Basically since rmtree is so dangerous we make sure
                        # it absolutely cannot be any root or nearly root level folder
                        # in the user's home dir even if some unknown future error happens.
                        # I have no reason to think this will ever actually be needed.
                        raise RuntimeError(
                            f"Defensive check failed: {old_dev_conf_folder}"
                        )
                    shutil.rmtree(old_dev_conf_folder)

        for i in fd:
            i2 = i[len("filedata.") :]
            fl = new_dev_conf_folder

            if fl is None:
                raise RuntimeError(f"{name} has no config dir")

            do = False
            if os.path.exists(os.path.join(fl, i2)):
                with open(os.path.join(fl, i2)) as f:
                    if not f.read() == kwargs[i]:
                        do = True
            else:
                do = True

            if do:
                os.makedirs(fl, exist_ok=True, mode=0o700)
                with open(os.path.join(fl, i2), "w") as f:
                    f.write(kwargs[i])

        if not subdevice:
            remote_devices[name] = makeDevice(name, kwargs)
        else:
            kwargs["is_subdevice"] = "true"

            # Don't pass our special internal keys to that mechanism that expects to only see standard iot_devices keys.
            k = {
                i: kwargs[i]
                for i in kwargs
                if not i.startswith("filedata.")
                and not i.startswith("temp.kaithem.")
            }
            subdevice_data_cache[name] = savable_data
            device_location_cache[name] = newparent_module, newparent_resource

            remote_devices[name].update_config(k)

        # Only actually update data structures
        # after updating the device runtime successfully

        # Delete and then recreate because we may be renaming to a different name

        assert parent_module
        assert parent_resource

        if not parent_resource:
            raise RuntimeError("?????????????")
        modules_state.rawDeleteResource(parent_module, parent_resource)

        # set the location info
        remote_devices[name].parent_module = newparent_module
        remote_devices[name].parent_resource = newparent_resource

        if newparent_module:
            storeDeviceInModule(
                savable_data, newparent_module, newparent_resource or name
            )
        else:
            raise ValueError("Must choose module")

        global remote_devices_atomic
        remote_devices_atomic = wrcopy(remote_devices)
        messagebus.post_message("/devices/added/", name)


specialKeys = {
    "subclass",
    "name",
    "title",
    "type",
    "is_subdevice",
    "description",
    "notes",
}


device_types = {"device": Device}


class DeviceNamespace:
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
        for i in x:
            y = x[i]()
            if y and not y.device_type_name == "unsupported":
                yield i


def wrapCrossFramework(dt2, desc):
    # We can't use the class as-is, because it uses the default very simple implementations of things.
    # So we customize it using Device.

    # Due to C3 linearization, Device takes precedence over dt's ancestors.
    class ImportedDeviceClass(Device, dt2):
        # Adapt from the cross-framework spec to the internal spec
        device_type_name = dt2.device_type
        readme = dt2.readme

        description = desc

        def __init__(self, name, data, **kw):
            # We have to call ours first because we need things like the tag points list
            # to be able to do the things theirs could call
            self.metadata = {}
            Device.__init__(self, name, data, **kw)
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


def makeDevice(name, data, cls=None):
    err = None
    desc = ""

    data = copy.deepcopy(data)
    data["name"] = name

    # Cls lets us force make a device of a different type for placeholders if we can't support them yet
    if cls:
        data["type"] = cls.device_type

    if data["type"] in device_types:
        dt = device_types[data["type"]]
    elif data["type"] in ("", "device", "Device"):
        dt = Device
    else:
        try:
            dt2 = cls or iot_devices.host.get_class(data)

            if not dt2:
                raise ValueError("Couldn't get class")
            try:
                desc = iot_devices.host.get_description(data["type"])
            except Exception:
                logger.exception("err getting description")

            dt = wrapCrossFramework(dt2, desc)

        except KeyError:
            dt = UnsupportedDevice
            dt = wrapCrossFramework(dt, "Placeholder device")
        except ValueError:
            dt = UnsupportedDevice
            dt = wrapCrossFramework(dt, "Placeholder device")

        except Exception:
            dt = UnsupportedDevice
            dt = wrapCrossFramework(dt, "Placeholder device")
            logger.exception("Err creating device")
            err = traceback.format_exc()
            logger.exception("Error making device")

    new_data = copy.deepcopy(data)
    new_data.pop("framework_data", None)

    # Don't pass framewith specific stuff to them.
    # Except a whitelist of known short string only keys that we need to easily access from
    # within the device integration code
    new_data = {
        i: new_data[i]
        for i in new_data
        if (
            (not i.startswith("temp.kaithem."))
            and (not i.startswith("filedata."))
        )
    }

    try:
        d = dt(name, new_data)
    except Exception:
        d = UnsupportedDevice(name, new_data)
        d.handle_exception()

    if err:
        d.handle_error(err)

    return d


def ensure_module_path_ok(module, resource):
    if resource.count("/"):
        dir = "/".join(resource.split("/")[:-1])
        for i in range(256):
            if dir in modules_state.ActiveModules[module]:
                if (
                    not modules_state.ActiveModules[module][dir][
                        "resource_type"
                    ]
                    == "directory"
                ):
                    raise RuntimeError(
                        f"File exists blocking creation of: {module}"
                    )
            if not dir.count("/"):
                break
            dir = "/".join(dir.split("/")[-1:])


def storeDeviceInModule(d: dict, module: str, resource: str) -> None:
    with modules_state.modulesLock:
        if resource.count("/"):
            dir = "/".join(resource.split("/")[:-1])
            for i in range(256):
                if dir not in modules_state.ActiveModules[module]:
                    r: modules_state.ResourceDictType = {
                        "resource_type": "directory",
                        "resource_timestamp": int(time.time() * 1000000),
                    }

                    modules_state.rawInsertResource(module, dir, r)
                if not dir.count("/"):
                    break
                dir = "/".join(dir.split("/")[:-1])

        modules_state.rawInsertResource(
            module, resource, {"resource_type": "device", "device": d}
        )


def getDeviceType(t):
    if t in device_types:
        return device_types[t]
    else:
        try:
            t = iot_devices.host.get_class({"type": t})
            return t or UnsupportedDevice
        except Exception:
            logger.exception("Could not look up class")
            return UnsupportedDevice


class TemplateGetter:
    def __init__(self, fn):
        self.fn = fn

    def __get__(self, instance, owner):
        return lambda: pages.get_vardir_template(self.fn).render(
            data=instance.config, obj=instance, name=instance.name
        )


unsupportedDevices: weakref.WeakValueDictionary[str, UnsupportedDevice] = (
    weakref.WeakValueDictionary()
)


def warnAboutUnsupportedDevices():
    x = remote_devices_atomic
    for i in x:
        d = x[i]()
        if not d:
            continue
        if not hasattr(d, "device_type_name"):
            continue

        if d.device_type_name == "unsupported":
            try:
                if isinstance(d, UnsupportedDevice):
                    d.warn()
                messagebus.post_message(
                    "/system/notifications/errors",
                    f"Device {str(i)} not supported",
                )
            except Exception:
                logger.exception(
                    f"Error warning about missing device support device {str(i)}"
                )


def init_devices():
    # Load all the stuff from the modules
    while deferred_loaders:
        try:
            deferred_loaders.pop()()
        except Exception:
            logger.exception("Err with device")
            messagebus.post_message(
                "/system/notifications/errors", "Err with device"
            )


importedDeviceTypes = iot_devices.host.discover()
