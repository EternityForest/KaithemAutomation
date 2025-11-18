# mypy: import-untyped=False
# pyright: reportIncompatibleMethodOverride=false
from __future__ import annotations

import copy
import gc
import json
import os
import shutil
import textwrap
import threading
import time
import traceback
import warnings
import weakref
from collections.abc import Callable, Mapping
from typing import Any

import iot_devices.device
import iot_devices.host
import pydantic
import quart
import structlog

# SPDX-FileCopyrightText: Copyright 2018 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later
from kaithem.api import lifespan

from . import (
    alerts,
    directories,
    geolocation,
    messagebus,
    modules_state,
    pages,
    tagpoints,
    unitsofmeasure,
    widgets,
    workers,
)
from .modules_state import ResourceType, resource_types

SUBDEVICE_SEPARATOR = "/"

# Our lock to be the same lock as the modules lock otherwise there would be too may easy ways to make a deadlock, we have to be able to
# edit the state because self modifying devices exist and can be saved in a module
logger = structlog.get_logger(__name__)

saveLocation = os.path.join(directories.vardir, "devices")


recent_scanned_tags = {}

# Used by device tag j2 template
callable = callable

device_types: dict[str, dict[str, Any]] = {}


def scan_devices():
    x = iot_devices.host.discover()
    device_types.clear()
    device_types.update(x)
    return x


workers.do(scan_devices)


def delete_bookkeep(name, confdir=False):
    # It sometimes is not there if the parent device got deleted first
    device_data_cache.pop(name, None)

    if name in devices_host.get_devices():
        rtd = devices_host.devices[name]
        pm = rtd.module_name
        pr = rtd.resource_name
        devices_host.close_device(name)
        gc.collect()

        if confdir:
            try:
                old_dev_conf_folder = get_config_folder_from_info(
                    pm, pr, name, create=False, always_return=True
                )
                if old_dev_conf_folder and os.path.isdir(old_dev_conf_folder):
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

        # Gotta be aggressive about ref cycle breaking!
        gc.collect()
        gc.collect()
        gc.collect()

        messagebus.post_message("/devices/removed/", name)


def log_scanned_tag(v: str, *args):
    recent_scanned_tags[v] = time.time()
    if len(recent_scanned_tags) > 15:
        recent_scanned_tags.pop(next(iter(recent_scanned_tags)))


dbgd: weakref.WeakValueDictionary[str, DeviceRuntimeState] = (
    weakref.WeakValueDictionary()
)


finished_reading_resources = False
deffered_loaders_list_lock = threading.Lock()
# Add module and resource for deterministic sortability
deferred_loaders: list[tuple[str, str, Callable[[], None]]] = []


# module, resource, config
device_data_cache: dict[str, tuple[str, str, Mapping[str, Any]]] = {}


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

        # We may want to store a device in a shortened resource name
        # because of / issues.
        if "name" in dev_data:
            devname = dev_data["name"]
            assert isinstance(devname, str)
        else:
            raise ValueError("No name in device")

        device_data_cache[devname] = (module, resource, data["device"])

        if dev_data.get("is_subdevice", False):
            return

        def load_closure():
            try:
                old_dev = devices_host.devices.get(devname)
            except Exception:
                old_dev = None
            if old_dev and old_dev.device:
                m, r = old_dev.module_name, old_dev.resource_name

                if not (m, r) == (module, resource):
                    modules_state.set_resource_error(
                        module,
                        resource,
                        f"Device with this name already exists and is in {m}/{r}",
                    )
                    raise RuntimeError(
                        "Can't overwrite device from a different resource"
                    )
                if old_dev.device.device_type.lower() not in (
                    "unsupported",
                    "unknown",
                    "unusedsubdevice",
                ):
                    if not old_dev.device.device_type == dev_data["type"]:
                        raise RuntimeError(
                            f"Can't overwrite device with a different type {dev_data['type']} != {old_dev.device.device_type}"
                        )

            if devname in devices_host.devices:
                devices_host.close_device(devname)

            makeDevice(devname, dev_data, cls, module, resource)

        # We aren't finished loading all the modules at startup
        # Save it and do everything at once
        if finished_reading_resources:
            load_closure()
        else:
            with deffered_loaders_list_lock:
                deferred_loaders.append((module, resource, load_closure))

    def on_update(self, module, resource: str, data: Mapping[str, Any]):
        # TODO is this ugly? I think it will be called whenever we change something
        # and only the change detection stops it from double loading
        if data["name"] in device_data_cache:
            if data["device"] == device_data_cache[data["name"]][2]:
                return

        self.on_load(module, resource, data)

    def on_unload(self, module, resource, data):
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

    def edit_page(self, module: str, resource: str, data):
        return quart.redirect(
            "/device/" + f"mr:{module}:{resource}" + "/manage"
        )


drt = DeviceResourceType("device", mdi_icon="chip")
resource_types["device"] = drt


def getZombies():
    x = []
    v = devices_host.get_devices()
    for i in dbgd:
        if dbgd[i] not in v:
            x.append((i, dbgd[i]))
    return x


def get_config_folder_from_device(runtime_obj: DeviceRuntimeState, create=True):
    assert runtime_obj

    if not hasattr(runtime_obj, "parent_module") or not runtime_obj.module_name:
        module = None
        resource = None
    else:
        module = runtime_obj.module_name
        resource = runtime_obj.module_name

    return get_config_folder_from_info(
        module, resource, runtime_obj.name, create=create
    )


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


class DeviceRuntimeState(iot_devices.host.DeviceHostContainer):
    @staticmethod
    def makeGenericUIMsgHandler(wr):
        def f(u, v):
            wr().onGenericUIMessage(u, v)

        return f

    def __init__(
        self,
        host,
        parent: DeviceRuntimeState | None,
        config,
        module: str | None = None,
        resource: str | None = None,
    ):
        super().__init__(host, parent, config)

        self.module_name: str | None = module
        self.resource_name: str | None = resource

        if not module:
            if self.parent:
                self.module_name = self.parent.module_name

        if not resource:
            if self.parent:
                if self.parent.resource_name:
                    resource_dir = "/".join(
                        self.parent.resource_name.split("/")[:-1]
                    )
                    rel_name = ".d/".join(config["name"].split("/"))

                    if resource_dir:
                        self.resource_name = f"{resource_dir}/{rel_name}"
                    else:
                        self.resource_name = rel_name

        if self.name in device_data_cache:
            self.module, self.resource, _config = device_data_cache[self.name]
        # Which points to show in overview
        self.dashboard_datapoints = {}

        self.logWindow = widgets.ScrollingWindow(2500)

        self._tagBookKeepers: dict[str, Callable[[Any, float, Any], None]] = {}

        # This is for extra non device specific stuff we add to all devices
        self._generic_ws_channel = widgets.APIWidget()
        self._generic_ws_channel.require("system_admin")

        onMessage2 = self.makeGenericUIMsgHandler(weakref.ref(self))

        # I don't think this is actually needed
        self._uiMsgRef = onMessage2

        self._generic_ws_channel.attach(onMessage2)

        dbgd[config["name"] + str(time.time())] = self

        # Time, title, text tuples for any "messages" a device might "print"
        self.messages: list[tuple[float, str, str]] = []

        # This dict cannot be changed, only replaced atomically.
        # It is a list of alert objects. Dict keys
        # may not include special chars besides underscores.

        # It is a list of all alerts "owned" by the device.
        self.alerts: dict[str, alerts.Alert] = {}

        # A list of all the tag points owned by the device
        self.tagpoints: dict[str, tagpoints.GenericTagPointClass[Any]] = {}

        # Same dict keys as tagpoints, but a list of handlers
        self.tagpointhandlerfunctions: dict[
            str, Callable[[Any, float, Any], None]
        ] = {}

        # The new devices spec has a way more limited idea of what a data point is.
        self.datapoints: dict[
            str, int | float | str | bytes | Mapping[str, Any] | None
        ] = {}

        self.datapoint_timestamps: dict[str, float] = {}
        # Time, msg
        self.errors: list[tuple[float, str]] = []

    def on_device_ready(self, device: iot_devices.device.Device):
        super().on_device_ready(device)

        data: dict[str, Any] = dict(copy.deepcopy(device.config))

        if "extensions" not in data:
            data["extensions"] = {}

        if "kaithem" not in data["extensions"]:
            data["extensions"]["kaithem"] = {}

        # Legacy porting block
        # TODO
        if "kaithem.use_default_alerts" in data:
            warnings.warn("Auto upgrading legacy config key")
            data["extensions"]["kaithem"]["use_default_alerts"] = data.pop(
                "kaithem.use_default_alerts"
            )
        if "kaithem.read_perms" in data:
            warnings.warn("Auto upgrading legacy config key")
            data["extensions"]["kaithem"]["read_perms"] = data.pop(
                "kaithem.read_perms"
            )
        if "kaithem.write_perms" in data:
            warnings.warn("Auto upgrading legacy config key")
            data["extensions"]["kaithem"]["write_perms"] = data.pop(
                "kaithem.write_perms"
            )

        if device.device_type not in (
            "unsupported",
            "unknown",
            "UnusedSubDevice",
        ):
            device.update_config(data)

        # Legacy stuff used strings
        self.k_use_default_alerts = str(
            data.get("extensions", {})
            .get("kaithem", {})
            .get("use_default_alerts")
        )

    def on_after_device_removed(self):
        for i in self.tagpointhandlerfunctions:
            f = self.tagpointhandlerfunctions[i]
            try:
                self.tagpoints[i].unsubscribe(f)
            except Exception:
                logger.error(
                    f"Error unsubscribing from tagpoint {i} for device {self.name}"
                )

    def onGenericUIMessage(self, u, v):
        if v[0] == "set":
            if v[2] is not None:
                self.tagpoints[v[1]].value = v[2]

        if v[0] == "fake":
            if v[2] is not None:
                self.tagpoints[v[1]]._k_ui_fake = self.tagpoints[v[1]].claim(
                    v[2], "faked", priority=50.5
                )

            else:
                if hasattr(self.tagpoints[v[1]], "_k_ui_fake"):
                    self.tagpoints[v[1]]._k_ui_fake.release()

        elif v[0] == "refresh":
            self.tagpoints[v[1]].poll()

    # delete a device, it should not be used after this
    def close(self):
        with modules_state.modulesLock:
            try:
                for i in self.tagpointhandlerfunctions:
                    if i in self.tagpoints:
                        self.tagpoints[i].unsubscribe(
                            self.tagpointhandlerfunctions[i]
                        )
            except Exception:
                if not lifespan.is_shutting_down:
                    logger.exception("Error unsubscribing from tagpoints")

            try:
                for i in self._tagBookKeepers:
                    if i in self.tagpoints:
                        self.tagpoints[i].unsubscribe(self._tagBookKeepers[i])
            except Exception:
                if not lifespan.is_shutting_down:
                    logger.exception(
                        "Error unsubscribing from tagpoints while closing device"
                    )

            try:
                del self.tagpoints
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
        x = self.tagpoints[datapoint].set_alarm(
            name,
            condition=expression,
            priority=priority,
            trip_delay=trip_delay,
            auto_ack=auto_ack,
            release_condition=release_condition,
            enabled=self.k_use_default_alerts,
        )
        if x:
            self.alerts[name] = x
        else:
            raise RuntimeError("Alarm setter returned nothing")

    def on_data_change(self, name: str, value, timestamp: float, annotation):
        """used for subclassing, this is how you watch for data changes.
        Kaithem does not need this, we have direct observable tag points.
        """

    def get_full_schema(self):
        assert self.device
        s = self.device.get_full_schema()
        if "extensions" not in s["properties"]:
            s["properties"]["extensions"] = {}
        s["properties"]["extensions"]["kaithem"] = {}

        s["properties"]["extensions"]["kaithem"]["read_perms"] = {
            "type": "string",
            "title": "Read Permissions",
            "description": "The permissions required to read this device, comma separated",
        }

        s["properties"]["extensions"]["kaithem"]["write_perms"] = {
            "type": "string",
            "title": "Write Permissions",
            "description": "The permissions required to write this device, comma separated",
        }

        s["properties"]["extensions"]["kaithem"]["use_default_alerts"] = {
            "type": "boolean",
            "title": "Enable the device's default alerts",
            "default": True,
            "description": "The permissions required to read this device, comma separated",
        }

        return s


class DevicesHost(iot_devices.host.Host[DeviceRuntimeState]):
    def on_device_print(self, device, message, title=""):
        "Print a message to the Device's management page"
        t = textwrap.fill(str(message), 120)
        tm = unitsofmeasure.strftime(time.time())

        if title:
            t = f"<b>{title}</b><br>{t}"
        t = t.replace("\n", "<br>")

        # Can't use a def here, wouldn't want it to possibly capture more than just a string,
        # And keep stuff from GCIng for too long
        workers.do(makeBackgroundPrintFunction(t, tm, title, device))

    def get_config_folder(self, device: DeviceRuntimeState, create=True):
        return get_config_folder_from_device(device, create=create)

    def __setupTagPerms(self, device: DeviceRuntimeState, t, writable=True):
        # Devices can have a default exposure

        our_ext = device.config.get("extensions", {}).get("kaithem", {})

        read_perms = (
            our_ext.get("read_perms", "system_admin").strip() or "system_admin"
        )
        write_perms = (
            our_ext.get("write_perms", "system_admin").strip() or "system_admin"
        )
        t.expose(read_perms, write_perms if writable else [])

    def resolve_datapoint_name(self, device_name, datapoint_name):
        return f"/devices/{device_name}.{datapoint_name}"

    def numeric_data_point(
        self,
        device: str,
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
        tagname = self.resolve_datapoint_name(device, name)
        runtimedata = devices_host.devices[device]

        t = tagpoints.Tag(tagname)

        self.__setupTagPerms(runtimedata, t, writable)

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

        runtimedata.dashboard_datapoints[tagname] = dashboard

        # Be defensive
        if tagname in runtimedata.tagpointhandlerfunctions:
            t.unsubscribe(runtimedata.tagpointhandlerfunctions[tagname])

        if handler:
            runtimedata.tagpointhandlerfunctions[tagname] = handler
            t.subscribe(handler)

        runtimedata.tagpoints[tagname] = t

        messagebus.post_message("/system/tags/configured", t.name)

    def string_data_point(
        self,
        device: str,
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
        tagname = self.resolve_datapoint_name(device, name)
        runtimedata = devices_host.devices[device]

        t = tagpoints.StringTag(tagname)

        self.__setupTagPerms(runtimedata, t, writable)

        t.default = default or ""
        t.interval = interval
        t.subtype = subtype
        t.writable = writable

        runtimedata.dashboard_datapoints[tagname] = dashboard

        # Be defensive
        if tagname in runtimedata.tagpointhandlerfunctions:
            t.unsubscribe(runtimedata.tagpointhandlerfunctions[name])

        if handler:
            runtimedata.tagpointhandlerfunctions[tagname] = handler
            t.subscribe(handler)

        runtimedata.tagpoints[tagname] = t

        messagebus.post_message("/system/tags/configured", t.name)

    def object_data_point(
        self,
        device: str,
        name: str,
        description: str = "",
        handler: Callable[[dict[str, Any], float, Any], Any] | None = None,
        interval: float = 0,
        writable: bool = True,
        subtype: str = "",
        dashboard: bool = True,
        default: dict[str, Any] | None = None,
        **kwargs,
    ):
        tagname = self.resolve_datapoint_name(device, name)
        runtimedata = devices_host.devices[device]

        t = tagpoints.ObjectTag(tagname)

        self.__setupTagPerms(runtimedata, t, writable)

        t.default = default or {}
        t.interval = interval
        t.subtype = subtype
        t.writable = writable

        runtimedata.dashboard_datapoints[tagname] = dashboard

        # Be defensive
        if tagname in runtimedata.tagpointhandlerfunctions:
            t.unsubscribe(runtimedata.tagpointhandlerfunctions[tagname])

        if handler:
            runtimedata.tagpointhandlerfunctions[tagname] = handler
            t.subscribe(handler)

        runtimedata.tagpoints[tagname] = t

        messagebus.post_message("/system/tags/configured", t.name)

    def bytestream_data_point(
        self,
        device: str,
        name: str,
        description: str = "",
        handler: Callable[[bytes, float, Any], Any] | None = None,
        interval: float = 0,
        writable: bool = True,
        subtype: str = "",
        dashboard: bool = True,
        default: bytes | None = None,
        **kwargs,
    ):
        tagname = self.resolve_datapoint_name(device, name)
        runtimedata = devices_host.devices[device]

        t = tagpoints.BinaryTag(tagname)

        self.__setupTagPerms(runtimedata, t, writable)

        t.default = default or b""
        t.interval = interval
        t.subtype = subtype
        t.writable = writable

        runtimedata.dashboard_datapoints[tagname] = dashboard

        # Be defensive
        if tagname in runtimedata.tagpointhandlerfunctions:
            t.unsubscribe(runtimedata.tagpointhandlerfunctions[tagname])

        if handler:
            runtimedata.tagpointhandlerfunctions[tagname] = handler
            t.subscribe(handler)

        runtimedata.tagpoints[tagname] = t

        messagebus.post_message("/system/tags/configured", t.name)

    def fast_push_bytes(
        self,
        device: str,
        name: str,
        value: bytes,
        timestamp: float | None = None,
        annotation: Any | None = None,
        force_push_on_repeat: bool = False,
    ):
        n = self.resolve_datapoint_name(device, name)
        runtimedata = devices_host.devices[device]
        runtimedata.tagpoints[n].fast_push(value, timestamp, annotation)

    def set_data_point(
        self,
        device: str,
        name,
        value: str | int | float | str | bytes | Mapping[str, Any],
        timestamp=None,
        annotation=None,
        force_push_on_repeat: bool = False,
    ):
        n = self.resolve_datapoint_name(device, name)
        runtimedata = devices_host.devices[device]
        runtimedata.tagpoints[n](value, timestamp, annotation)

    def set_number(
        self,
        device: str,
        name: str,
        value: float | int,
        timestamp: float | None = None,
        annotation: Any | None = None,
        force_push_on_repeat: bool = False,
    ):
        self.set_data_point(
            device, name, value, timestamp, annotation, force_push_on_repeat
        )

    def set_string(
        self,
        device: str,
        name: str,
        value: str,
        timestamp: float | None = None,
        annotation: Any | None = None,
        force_push_on_repeat: bool = False,
    ):
        self.set_data_point(
            device, name, value, timestamp, annotation, force_push_on_repeat
        )

    def set_bytes(
        self,
        device: str,
        name: str,
        value: bytes,
        timestamp: float | None = None,
        annotation: Any | None = None,
        force_push_on_repeat: bool = False,
    ):
        self.set_data_point(
            device, name, value, timestamp, annotation, force_push_on_repeat
        )

    def set_object(
        self,
        device: str,
        name: str,
        value: dict[str, Any],
        timestamp: float | None = None,
        annotation: Any | None = None,
        force_push_on_repeat: bool = False,
    ):
        self.set_data_point(
            device, name, value, timestamp, annotation, force_push_on_repeat
        )

    def get_datapoint(self, device: str, name: str):
        n = self.resolve_datapoint_name(device, name)
        runtimedata = devices_host.devices[device]
        return runtimedata.tagpoints[n].get_vta()

    def get_number(
        self, device: str, datapoint: str
    ) -> tuple[float | int, float, Any]:
        return self.get_datapoint(device, datapoint)

    def get_string(self, device: str, datapoint: str) -> tuple[str, float, Any]:
        return self.get_datapoint(device, datapoint)

    def get_bytes(
        self, device: str, datapoint: str
    ) -> tuple[bytes, float, Any]:
        return self.get_datapoint(device, datapoint)

    def get_object(
        self, device: str, datapoint: str
    ) -> tuple[dict[str, Any], float, Any]:
        return self.get_datapoint(device, datapoint)

    def get_config_for_device(
        self, parent_device: Any | None, full_device_name: str
    ) -> Mapping[str, Any]:
        return device_data_cache.pop(full_device_name, ("", "", {}))[2]

    def on_config_changed(
        self, device: DeviceRuntimeState, config: Mapping[str, Any]
    ):
        def f():
            with modules_state.modulesLock:
                if device.module_name and device.resource_name:
                    # Todo why are we mutating in place?
                    devdata = modules_state.ActiveModules[device.module_name][
                        device.resource_name
                    ]

                    devdata = dict(copy.deepcopy(devdata))
                    devdata["device"] = dict(copy.deepcopy(config))

                    m, r = device.module_name, device.resource_name

                    modules_state.raw_insert_resource(m, r, devdata)

            use_default_alerts = (
                config.get("extensions", {})
                .get("kaithem", {})
                .get("use_default_alerts", True)
            )

            if use_default_alerts != device.k_use_default_alerts:
                device.k_use_default_alerts = use_default_alerts

                if not use_default_alerts:
                    for alert in device.alerts.values():
                        alert.disable()

                else:
                    for alert in device.alerts.values():
                        alert.enable()

    def on_device_error(self, container: DeviceRuntimeState, s: str):
        container.errors.append((time.time(), str(s)))

        if container.errors:
            if time.time() > container.errors[-1][0] + 15:
                logger.error(f"in device: {container.name}\n{s}")
            else:
                logger.error(f"in device: {container.name}\n{s}")

        if len(container.errors) > 50:
            container.errors.pop(0)

        workers.do(
            makeBackgroundErrorFunction(
                textwrap.fill(s, 120),
                unitsofmeasure.strftime(time.time()),
                container,
            )
        )
        if len(container.errors) == 1:
            messagebus.post_message(
                "/system/notifications/errors",
                f"First error in device: {container.name}",
            )
            logger.error(f"in device: {container.name}\n{s}")


devices_host = DevicesHost(DeviceRuntimeState)
devices_host.host_apis["get_site_coordinates"] = (
    geolocation.deviceLocationGetter
)


class UnsupportedDevice(iot_devices.device.Device):
    description = (
        "This device does not have support, or else the support is not loaded."
    )
    device_type = "unsupported"

    def warn(self):
        self.handle_error("This device type has no support.")

    def __init__(self, data):
        super().__init__(data)


# Device data always has 2 constants. 1 is the required type, the other
# is name, and that's optional but can be used to rename a device


def updateDevice(
    devname: str, kwargs: dict[str, Any], saveChanges: bool = True
):
    # The NEW name, which could just be the old name
    name = kwargs.get("name", None) or devname

    if name not in kwargs:
        kwargs["name"] = name

    subdevice = False

    with modules_state.modulesLock:
        m = kwargs["temp.kaithem.store_in_module"]
        r = kwargs["temp.kaithem.store_in_resource"]
        kwargs.pop("temp.kaithem.store_in_module", None)
        kwargs.pop("temp.kaithem.store_in_resource", None)

        if m:
            if m not in modules_state.ActiveModules:
                raise ValueError("Can't store in nonexistant module")

            if r in modules_state.ActiveModules[m]:
                if (
                    not modules_state.ActiveModules[m][r]["resource"]["type"]
                    == "device"
                ):
                    raise ValueError(
                        "A resource in the module with that name exists and is not a device."
                    )

                if "module_lock" in modules_state.get_module_metadata(m):
                    raise PermissionError("Module is locked")

                if "lock" in modules_state.ActiveModules[m][r]["resource"]:
                    raise PermissionError("Device is locked")
            # Make sure we don't corrupt state by putting a folder where a file already is
            ensure_module_path_ok(m, r)
        else:
            raise RuntimeError("You can now only save devices into modules.")

        if devname not in devices_host.devices:
            raise RuntimeError("No such device to update")

        current_device_object = devices_host.devices[devname]

        subdevice = current_device_object.parent is not None

        parent_module = current_device_object.module_name
        parent_resource = current_device_object.resource_name

        old_dev_conf_folder = get_config_folder_from_info(
            parent_module,
            parent_resource,
            devname,
            create=False,
            always_return=True,
        )

        newparent_module = m
        newparent_resource = r or ".d/".join(name.split("/"))

        new_dev_conf_folder = get_config_folder_from_info(
            newparent_module,
            newparent_resource,
            name,
            create=False,
            always_return=True,
        )

        if parent_module and parent_resource:
            if (
                parent_module in modules_state.ActiveModules
                and parent_resource
                in modules_state.ActiveModules[parent_module]
            ):
                dt = modules_state.ActiveModules[parent_module][
                    parent_resource
                ]["device"]
            else:
                dt = {}

            assert isinstance(dt, dict)

            # Not the same as currently being a subdevice.
            # We have placeholders to edit subdevices that don't exist.
            configuredAsSubdevice = dt.get("is_subdevice", False)

            configuredAsSubdevice = (
                configuredAsSubdevice or dt.get("parent_device", "").strip()
            )  # type: ignore
        else:
            configuredAsSubdevice = current_device_object.config.get(
                "is_subdevice", False
            )

        if not subdevice:
            current_device_object.close()
            messagebus.post_message("/devices/removed/", devname)

        gc.collect()
        time.sleep(0.01)
        time.sleep(0.01)
        gc.collect()

        decoded = json.loads(kwargs["json"])

        savable_data = {
            i: decoded[i]
            for i in decoded
            if ((not i.startswith("temp.")) and not i.startswith("filedata."))
        }

        if "name" in savable_data:
            if savable_data["name"] != name:
                raise ValueError("Internal error: device data inconsistent")
        else:
            # We might update this from some odd place that doesn't
            # Explicitly put name in data.
            savable_data["name"] = name

        # Propagate subdevice status even if it is just loaded as a placeholder
        if configuredAsSubdevice or subdevice:
            savable_data["is_subdevice"] = True

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

        if not subdevice:
            devices_host.close_device(name)
            gc.collect()
            time.sleep(0.01)
            gc.collect()
            makeDevice(
                name, savable_data, None, newparent_module, newparent_resource
            )
        else:
            kwargs["is_subdevice"] = True

            device_data_cache[name] = (
                newparent_module,
                newparent_resource,
                savable_data,
            )

            devices_host.devices[name].module_name = newparent_module
            devices_host.devices[name].resource_name = newparent_resource
            if current_device_object.device:
                current_device_object.device.update_config(savable_data)

        # Only actually update data structures
        # after updating the device runtime successfully

        # Delete and then recreate because we may be renaming to a different name

        # This might be created as a subdevice rather than a configured device

        assert (parent_module and parent_resource) or (
            not parent_module and not parent_resource
        )

        with modules_state.modulesLock:
            if parent_module and parent_resource:
                if not (
                    (parent_module, parent_resource)
                    == (newparent_module, newparent_resource)
                ):
                    if (
                        parent_module in modules_state.ActiveModules
                        and parent_resource
                        in modules_state.ActiveModules[parent_module]
                    ):
                        modules_state.rawDeleteResource(
                            parent_module, parent_resource
                        )

        if newparent_module:
            storeDeviceInModule(
                savable_data, newparent_module, newparent_resource or name
            )
        else:
            raise ValueError("Must choose module")

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


class DeviceNamespace:
    Device = iot_devices.device.Device

    def __getitem__(self, name):
        d = devices_host.devices.get(name)
        if not d:
            raise KeyError(name)
        if not d.device:
            raise KeyError(name)
        if d.device.device_type == "unsupported":
            raise RuntimeError("There is no driver for this device")
        if d.device.device_type == "unknown":
            raise RuntimeError("There is no driver for this device")
        if d.device.device_type.lower() == "unusedsubdevice":
            raise RuntimeError("Unused subdevice config")

        return weakref.proxy(devices_host.devices[name])

    def __iter__(self):
        x = devices_host.get_devices()
        for i in x:
            try:
                x = self[i]
                yield i
            except (KeyError, RuntimeError):
                pass


def makeDevice(
    name: str,
    data: dict[str, Any],
    cls: type[iot_devices.device.Device] | None,
    module: str,
    resource: str,
) -> DeviceRuntimeState:
    err = None

    data = copy.deepcopy(data)
    data["name"] = name

    # We need to make sure we have a name

    # Cls lets us force make a device of a different type for placeholders if we can't support them yet
    if cls:
        data["type"] = cls.device_type

    else:
        try:
            cls = cls or iot_devices.host.get_class(data)

            if not cls:
                raise ValueError("Couldn't get class")

        except KeyError:
            cls = UnsupportedDevice
        except ValueError:
            cls = UnsupportedDevice

        except Exception:
            cls = UnsupportedDevice
            logger.exception("Err creating device")
            err = traceback.format_exc()
            logger.exception("Error making device")

    new_data = copy.deepcopy(data)

    if new_data["name"] in devices_host.devices:
        raise RuntimeError(f"Device name already exists: {new_data['name']}")

    try:
        d = devices_host.add_device_from_class(
            cls,
            new_data,
            host_container_kwargs={"module": module, "resource": resource},
        )
    except Exception:
        d = devices_host.add_device_from_class(UnsupportedDevice, new_data)
        d.wait_device_ready().handle_exception()

    if err:
        if d.device:
            d.device.handle_error(err)
        else:
            logger.exception("Error making device")
    return d


def ensure_module_path_ok(module, resource):
    if resource.count("/"):
        dir = "/".join(resource.split("/")[:-1])
        for i in range(256):
            if dir in modules_state.ActiveModules[module]:
                if (
                    not modules_state.ActiveModules[module][dir]["resource"][
                        "type"
                    ]
                    == "directory"
                ):
                    raise RuntimeError(
                        f"File exists blocking creation of: {module}"
                    )
            if not dir.count("/"):
                break
            dir = "/".join(dir.split("/")[-1:])


@pydantic.validate_call
def storeDeviceInModule(d: dict[str, Any], module: str, resource: str) -> None:
    with modules_state.modulesLock:
        if resource.count("/"):
            dir = "/".join(resource.split("/")[:-1])
            for i in range(256):
                if dir not in modules_state.ActiveModules[module]:
                    r: modules_state.ResourceDictType = {
                        "resource": {
                            "type": "directory",
                            "modified": int(time.time()),
                        }
                    }

                    modules_state.raw_insert_resource(module, dir, r)
                if not dir.count("/"):
                    break
                dir = "/".join(dir.split("/")[:-1])

        if resource in modules_state.ActiveModules[module]:
            r = dict(
                copy.deepcopy(modules_state.ActiveModules[module][resource])
            )  # type: ignore #
        else:
            r = {
                "resource": {
                    "type": "device",
                    "modified": int(time.time()),
                }
            }

        r["device"] = d

        modules_state.raw_insert_resource(module, resource, r)


def getDeviceType(t):
    try:
        t = iot_devices.host.get_class({"type": t})
        return t or UnsupportedDevice
    except Exception:
        logger.exception("Could not look up class")
        return UnsupportedDevice


def init_devices():
    # Load all the stuff from the modules

    # Sort so we get a deterministic-ish order
    with deffered_loaders_list_lock:
        deferred_loaders.sort()

    while deferred_loaders:
        try:
            deferred_loaders.pop(0)[2]()
        except Exception:
            logger.exception("Error loading device")
            messagebus.post_message(
                "/system/notifications/errors", "Error loading device"
            )
