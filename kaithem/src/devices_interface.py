import copy
import gc
import json
import os
import subprocess
import time
import traceback
import urllib.parse

import colorzero
import quart
from quart import Response, redirect
from quart.ctx import copy_current_request_context
from scullery import units

from kaithem.src import devices, messagebus, modules_state, pages, udisks
from kaithem.src.devices import (
    Device,
    delete_bookkeep,
    getDeviceType,
    makeDevice,
    specialKeys,
    storeDeviceInModule,
    updateDevice,
    wrcopy,
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


def getshownkeys(obj: Device):
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
    d = pages.get_template("devices/index.html").render(
        deviceData=devices.remote_devices_atomic,
        url=url,
        disks=udisks.list_drives(),
        is_mounted=udisks.is_mounted,
        si=units.si_format_number,
    )

    return Response(
        d, mimetype="text/html", headers={"X-Frame-Options": "SAMEORIGIN"}
    )


@app.route("/devices/report")
def report():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    def get_report_data(dev: Device):
        o = {}
        for i in dev.config:
            if i not in ("notes", "subclass") or len(str(dev.config[i])) < 256:
                o[i] = dev.config[i]
                continue
        return json.dumps(o)

    def has_secrets(dev: Device):
        for i in dev.config:
            if dev.config_properties.get(i, {}).get("secret", False):
                if dev.config[i]:
                    return True

    return pages.render_jinja_template(
        "devices/device_report.j2.html",
        devs=devices.remote_devices_atomic,
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

    obj = devices.remote_devices[name]

    if obj.parent_module:
        assert obj.parent_resource
        merged.update(
            modules_state.ActiveModules[obj.parent_module][obj.parent_resource][
                "device"
            ]
        )

    # I think stored data is enough, this is just defensive
    merged.update(devices.remote_devices[name].config)

    return pages.render_jinja_template(
        "devices/device.j2.html",
        data=merged,
        obj=obj,
        name=name,
        title="" if obj.title == obj.name else obj.title,
        **device_page_env,
    )


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
    x = devices.remote_devices[name].readme

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

    if devname and devname in devices.remote_devices:
        # If possible just use the actual object
        d = devices.remote_devices[devname]
        c = copy.deepcopy(d.config)
        c.update(current)
        obj = d
    else:
        obj = None
        d = getDeviceType(type)
        c = current

    d = d.discover_devices(
        c,
        current_device=devices.remote_devices.get(devname, None),
        intent="step",
    )

    dt = pages.get_template("devices/discoverstep.html").render(
        data=d, current=c, name=devname, obj=obj
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
    return create_device_from_kwargs(**kwargs)


def create_device_from_kwargs(**kwargs):
    """This pretty much exists so we can call it from a tests without going through the web"""
    name = kwargs.get("name", None)
    m = r = None

    with modules_state.modulesLock:
        if "module" in kwargs:
            m = str(kwargs["module"])
            r = str(kwargs["resource"])
            name = name or r
            del kwargs["module"]
            del kwargs["resource"]
            d = {i: kwargs[i] for i in kwargs if not i.startswith("temp.")}
            d["name"] = name

            # Set these as the default
            kwargs["kaithem.read_perms"] = "view_devices"
            kwargs["kaithem.write_perms"] = "write_devices"

            dt = {"resource_type": "device", "device": d}

            modules_state.rawInsertResource(m, r, dt)
        else:
            raise RuntimeError(
                "Creating devices outside of modules is no longer supported."
            )

        if name in devices.remote_devices:
            devices.remote_devices[name].close()
        devices.remote_devices[name] = makeDevice(name, kwargs)

        if m and r:
            storeDeviceInModule(d, m, r)
        else:
            raise RuntimeError(
                "Creating devices outside of modules is no longer supported."
            )

        devices.remote_devices[name].parent_module = m
        devices.remote_devices[name].parent_resource = r
        devices.remote_devices_atomic = devices.wrcopy(devices.remote_devices)
        messagebus.post_message("/devices/added/", name)

    return redirect("/devices")


@app.route("/devices/createDevicePage", methods=["POST"])
@wrap_sync_route_handler
def createDevicePage(module, resource, type):
    "Ether create a 'blank' device, or, if supported, show the custom page"
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    tp = getDeviceType(type)
    assert tp

    d = pages.get_template("devices/createpage.html").render(
        name=resource, type=type, module=module, resource=resource
    )
    return Response(
        d, mimetype="text/html", headers={"X-Frame-Options": "SAMEORIGIN"}
    )


@app.route("/devices/deleteDevice/<name>")
def delete_device_dialog(name):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    d = pages.get_template("devices/confirmdelete.html").render(name=name)
    return Response(
        d, mimetype="text/html", headers={"X-Frame-Options": "SAMEORIGIN"}
    )


@app.route("/devices/settarget/<name>/<tag>", methods=["POST"])
@wrap_sync_route_handler
def settarget(name, tag, **kwargs):
    try:
        pages.require("enumerate_endpoints")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    x = devices.remote_devices[name]

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
    x = devices.remote_devices[name]

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
    x = devices.remote_devices[name]

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
        x = devices.remote_devices[name]
        # Delete bookkeep removes it from device data if present
        delete_bookkeep(name, delete_conf_dir)

        if x.parent_module:
            modules_state.rawDeleteResource(
                x.parent_module, x.parent_resource or name
            )

        # no zombie reference
        del x

        devices.remote_devices_atomic = wrcopy(devices.remote_devices)
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
