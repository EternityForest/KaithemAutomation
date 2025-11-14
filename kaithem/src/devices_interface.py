import copy
import gc
import json
import os
import subprocess
import time
import traceback
import urllib.parse

import colorzero
import mako.exceptions
import quart
from iot_devices import device
from quart import Response, redirect
from quart.ctx import copy_current_request_context
from scullery import units

from kaithem.src import (
    devices,
    messagebus,
    modules_state,
    pages,
    udisks,
    validation_util,
)
from kaithem.src.devices import (
    delete_bookkeep,
    getDeviceType,
    makeDevice,
    specialKeys,
    storeDeviceInModule,
    updateDevice,
)
from kaithem.src.quart_app import app, wrap_sync_route_handler


def read(f):
    try:
        with open(f) as fd:
            return fd.read()
    except Exception:
        return ""


def url(u):
    return urllib.parse.quote(u, safe="")


def getshownkeys(obj: device.Device):
    return sorted(
        [
            i
            for i in obj.config.keys()
            if i not in specialKeys
            and not i.startswith("kaithem.")
            and not i.startswith("temp.kaithem")
        ]
    )


device_page_env = {
    "specialKeys": specialKeys,
    "read": read,
    "url": url,
    "hasattr": hasattr,
}


def render_device_tag(obj, tag):
    try:
        return pages.render_jinja_template(
            "devices/device_tag_component.j2.html", i=tag, obj=obj
        )
    except Exception:
        return f"<article>{traceback.format_exc()}</article>"


@app.route("/devices")
def devices_index():
    """Index page for web interface"""
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    try:
        d = pages.get_template("devices/index.html").render(
            deviceData=devices.devices_host.get_devices(),
            url=url,
            disks=udisks.list_drives(),
            is_mounted=udisks.is_mounted,
            si=units.si_format_number,
        )

        return Response(
            d, mimetype="text/html", headers={"X-Frame-Options": "SAMEORIGIN"}
        )
    except Exception:
        return mako.exceptions.html_error_template().render()


@app.route("/devices/report")
def report():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    def get_report_data(dev: device.Device):
        o = {}
        for i in dev.config:
            if i not in ("notes", "subclass") or len(str(dev.config[i])) < 256:
                o[i] = dev.config[i]
                continue
        return json.dumps(o)

    def has_secrets(dev: device.Device):
        for i in dev.config:
            if (
                dev.config_schema.get("properties", {})
                .get(i, {})
                .get("format", False)
                == "password"
            ):
                if dev.config[i]:
                    return True

    return pages.render_jinja_template(
        "devices/device_report.j2.html",
        devs=devices.devices_host.get_devices(),
        has_secrets=has_secrets,
        get_report_data=get_report_data,
        **device_page_env,
    )


@app.route("/device/<path:name>/manage")
def device_manage(name):
    try:
        pages.require("enumerate_endpoints")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    # Some framework only keys are not passed to the actual device since we use what amounts
    # to an extension, so we have to merge them in
    merged = {}

    obj = devices.devices_host.devices[name]

    if obj.module_name:
        assert obj.resource_name
        merged.update(
            modules_state.ActiveModules[obj.module_name][obj.resource_name][
                "device"
            ]
        )

    # I think stored data is enough, this is just defensive
    merged.update(devices.devices_host.devices[name].config)

    try:
        return pages.render_jinja_template(
            "devices/device.j2.html",
            data=merged,
            obj=obj,
            name=name,
            title="" if obj.device.title == obj.name else obj.device.title,
            **device_page_env,
        )
    except Exception:
        return mako.exceptions.html_error_template().render()


@app.route("/device/<name>")
def device(name):
    try:
        pages.require("enumerate_endpoints")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return redirect(f"/device/{name}/manage")


@app.route("/devices/devicedocs/<name>")
def devicedocs(name):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    x = devices.devices_host.devices[name].readme

    if x is None:
        x = "No readme found"
    if x.startswith("/") or (len(x) < 1024 and os.path.exists(x)):
        with open(x) as f:
            x = f.read()

    return pages.get_template("devices/devicedocs.html").render(docs=x)


@app.route("/devices/updateDevice/<devname>", methods=["POST"])
@wrap_sync_route_handler
def updateDeviceTarget(devname, **kwargs):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    updateDevice(devname, kwargs)
    return redirect("/devices")


@app.route("/devices/discoveryStep/<type>/<devname>", methods=["POST"])
@wrap_sync_route_handler
def discoveryStep(type, devname, **kwargs):
    """
    Do a step of iterative device discovery.  Can start either from just a type or we can take
    an existing device config and ask it for refinements.
    """
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    current = kwargs

    if devname and devname in devices.devices_host.devices:
        # If possible just use the actual object
        d = devices.devices_host.devices[devname]
        c = copy.deepcopy(d.config)
        c.update(current)
        obj = d
    else:
        obj = None
        d = getDeviceType(type)
        c = current

    d = d.discover_devices(
        c,
        current_device=devices.devices_host.devices.get(devname, None),
        intent="step",
    )

    dt = pages.get_template("devices/discoverstep.html").render(
        data=d,
        current=c,
        name=devname,
        obj=obj,
        parent_module=obj.module_name if obj else None,
        parent_resource=obj.resource_name if obj else None,
    )
    return Response(
        dt, mimetype="text/html", headers={"X-Frame-Options": "SAMEORIGIN"}
    )


@app.route("/devices/createDevice", methods=["POST"])
@wrap_sync_route_handler
def createDevice(**kwargs):
    "Actually create the new device"
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return create_blank_device(**kwargs)


@validation_util.validate_args
def create_blank_device(name: str, module: str, resource: str, type: str):
    data = {}
    name = name or resource

    data["name"] = name
    data["type"] = type

    data["extensions"] = {}
    data["extensions"]["kaithem"] = {}

    # Set these as the default
    data["extensions"]["kaithem"]["read_perms"] = "view_devices"
    data["extensions"]["kaithem"]["write_perms"] = "write_devices"

    dt = {"resource": {"type": "device"}, "device": data}

    modules_state.raw_insert_resource(module, resource, dt)

    if name in devices.devices_host.devices:
        devices.devices_host.devices[name].close()

    devices.devices_host.devices[name] = makeDevice(
        name, data, None, module, resource
    )

    storeDeviceInModule(dt, module, resource)

    messagebus.post_message("/devices/added/", name)

    return redirect("/devices")


@app.route("/devices/settarget/<name>/<tag>", methods=["POST"])
@wrap_sync_route_handler
def settarget(name, tag, **kwargs):
    try:
        pages.require("enumerate_endpoints")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    x = devices.devices_host.devices[name]

    perms = x.config.get("kaithem.write_perms", "").strip() or "system_admin"

    for i in perms.split(","):
        try:
            pages.require(i)
        except PermissionError:
            return pages.loginredirect(pages.geturl())

    if tag in x.tagpoints:
        x.tagpoints[tag].value = kwargs["value"]

    return ""


@app.route("/devices/dimtarget/<name>/<tag>", methods=["POST"])
@wrap_sync_route_handler
def dimtarget(name, tag, **kwargs):
    "Set a color tagpoint to a dimmed version of it."
    try:
        pages.require("enumerate_endpoints")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    x = devices.devices_host.devices[name]

    perms = x.config.get("kaithem.write_perms", "").strip() or "system_admin"

    for i in perms.split(","):
        try:
            pages.require(i)
        except PermissionError:
            return pages.loginredirect(pages.geturl())

    if tag in x.tagpoints:
        try:
            x.tagpoints[tag].value = (
                colorzero.Color.from_string(x.tagpoints[tag].value)
                * colorzero.Luma(kwargs["value"])
            ).html
        except Exception:
            x.tagpoints[tag].value = (
                colorzero.Color.from_rgb(1, 1, 1)
                * colorzero.Luma(kwargs["value"])
            ).html
    return ""


@app.route("/devices/triggertarget/<name>/<tag>", methods=["POST"])
@wrap_sync_route_handler
def triggertarget(name, tag, **kwargs):
    try:
        pages.require("enumerate_endpoints")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    x = devices.devices_host.devices[name]

    perms = x.config.get("kaithem.write_perms", "").strip() or "system_admin"

    for i in perms.split(","):
        try:
            pages.require(i)
        except PermissionError:
            return pages.loginredirect(pages.geturl())

    if tag in x.tagpoints:
        x.tagpoints[tag].value = x.tagpoints[tag].value + 1
    return ""


@app.route("/devices/deletetarget", methods=["POST"])
@wrap_sync_route_handler
def deletetarget(**kwargs):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    name = kwargs["name"]

    delete_device(name, delete_conf_dir="delete_conf_dir" in kwargs)

    return redirect("/devices")


def delete_device(name, delete_conf_dir=False):
    with modules_state.modulesLock:
        x = devices.devices_host.devices[name]
        # Delete bookkeep removes it from device data if present
        delete_bookkeep(name, delete_conf_dir)

        if x.module_name:
            modules_state.rawDeleteResource(
                x.module_name, x.resource_name or name
            )

        # no zombie reference
        del x

        devices.devices_host.close_device(name)
        # Gotta be aggressive about ref cycle breaking!
        gc.collect()
        time.sleep(0.1)
        gc.collect()
        time.sleep(0.2)
        gc.collect()

        messagebus.post_message("/devices/removed/", name)


@app.route("/udisks/mount", methods=["POST"])
async def mount_device():
    pages.require("system_admin")
    form = await quart.request.form

    dev = str(form.get("partition"))
    dev = os.path.realpath(dev)

    @copy_current_request_context
    def f():
        subprocess.check_call(["udisksctl", "mount", "-b", dev])

    await f()

    return redirect("/devices")


@app.route("/udisks/unmount", methods=["POST"])
async def unmount_device():
    pages.require("system_admin")
    form = await quart.request.form

    dev = str(form.get("partition"))
    dev = os.path.realpath(dev)

    @copy_current_request_context
    def f():
        subprocess.check_call(["udisksctl", "unmount", "-b", dev])

    await f()

    return redirect("/devices")
