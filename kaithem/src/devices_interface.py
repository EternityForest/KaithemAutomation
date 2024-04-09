import json
import os
import time
import urllib.parse
import gc
import copy
import traceback

import colorzero
import cherrypy
import cherrypy.lib.static


from kaithem.src import pages
from kaithem.src import devices
from kaithem.src import modules_state
from kaithem.src import messagebus

from kaithem.src.devices import (
    Device,
    specialKeys,
    getDeviceType,
    delete_bookkeep,
    storeDeviceInModule,
    saveDevice,
    updateDevice,
    makeDevice,
    wrcopy,
)


def read(f):
    try:
        with open(f) as fd:
            return fd.read()
    except Exception:
        return ""


def url(u):
    return urllib.parse.quote(u, safe="")


def devStatString(d):
    "Misc status info that we can gather from the device typy"
    s = []

    try:
        if "status" in d.tagPoints:
            s.append(str(d.tagPoints["status"]())[:32])

        if len(d.tagPoints) < 14:
            for i in d.tagPoints:
                if hasattr(d.tagPoints[i], "meterWidget"):
                    if d.tagPoints[i].type == "number":
                        s.append(
                            d.tagPoints[i].meterWidget.render_oneline(label=i + ": ")
                        )

        else:
            if "rssi" in d.tagPoints:
                s.append(d.tagPoints["rssi"].meterWidget.render_oneline(label="RSSI: "))
            if "battery" in d.tagPoints:
                s.append(
                    d.tagPoints["battery"].meterWidget.render_oneline(label="Battery: ")
                )
            if "powered" in d.tagPoints:
                s.append(
                    d.tagPoints["powered"].meterWidget.render_oneline(label="Powered: ")
                )

            if "switch" in d.tagPoints:
                s.append(
                    d.tagPoints["switch"].meterWidget.render_oneline(label="Switch: ")
                )
            if "running" in d.tagPoints:
                s.append(
                    d.tagPoints["running"].meterWidget.render_oneline(label="Running: ")
                )
            if "record" in d.tagPoints:
                s.append(
                    d.tagPoints["record"].meterWidget.render_oneline(
                        label="Recording: "
                    )
                )
            if "temperature" in d.tagPoints:
                s.append(
                    d.tagPoints["temperature"].meterWidget.render_oneline(
                        label="Temperature: "
                    )
                )
            if "humidity" in d.tagPoints:
                s.append(
                    d.tagPoints["humidity"].meterWidget.render_oneline(
                        label="Humidity: "
                    )
                )
            if "uv_index" in d.tagPoints:
                s.append(
                    d.tagPoints["uv_index"].meterWidget.render_oneline(
                        label="UV Index: "
                    )
                )
            if "wind" in d.tagPoints:
                s.append(d.tagPoints["wind"].meterWidget.render_oneline(label="Wind: "))

            if "open" in d.tagPoints:
                s.append(d.tagPoints["open"].meterWidget.render_oneline(label="Open: "))

            if "on" in d.tagPoints:
                s.append(d.tagPoints["on"].meterWidget.render_oneline(label="On: "))

            if "leak" in d.tagPoints:
                s.append(d.tagPoints["leak"].meterWidget.render_oneline(label="Leak: "))

    except Exception as e:
        s.append(str(e))

    return "".join([i for i in s])


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


class WebDevices:
    @cherrypy.expose
    def index(self):
        """Index page for web interface"""
        pages.require("system_admin")
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"

        return pages.get_template("devices/index.html").render(
            deviceData=devices.remote_devices_atomic,
            devStatString=devStatString,
            url=url,
        )

    @cherrypy.expose
    def report(self):
        pages.require("system_admin")

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

    @cherrypy.expose
    def device(self, name, *args, **kwargs):
        # This is a customizable per-device page
        if args and args[0] == "web":
            if kwargs:
                # Just don't allow gets that way
                pages.postOnly()
            try:
                return devices.remote_devices[name].webHandler(*args[1:], **kwargs)
            except pages.ServeFileInsteadOfRenderingPageException as e:
                return cherrypy.lib.static.serve_file(e.f_filepath, e.f_MIME, e.f_name)

        if args and args[0] == "manage":
            pages.require("system_admin")

            # Some framework only keys are not passed to the actual device since we use what amounts
            # to an extension, so we have to merge them in
            merged = {}

            obj = devices.remote_devices[name]
            if name in devices.device_data:
                merged.update(devices.device_data[name])

            if obj.parentModule:
                merged.update(
                    modules_state.ActiveModules[obj.parentModule][obj.parentResource][
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
                args=args,
                kwargs=kwargs,
                title="" if obj.title == obj.name else obj.title,
                **device_page_env,
            )
        if not args:
            raise cherrypy.HTTPRedirect(cherrypy.url() + "/manage")

    @cherrypy.expose
    def devicedocs(self, name):
        pages.require("system_admin")
        x = devices.remote_devices[name].readme

        if x is None:
            x = "No readme found"
        if x.startswith("/") or (len(x) < 1024 and os.path.exists(x)):
            with open(x) as f:
                x = f.read()

        return pages.get_template("devices/devicedocs.html").render(docs=x)

    @cherrypy.expose
    def updateDevice(self, devname, **kwargs):
        pages.require("system_admin")
        pages.postOnly()
        updateDevice(devname, kwargs)
        raise cherrypy.HTTPRedirect("/devices")

    @cherrypy.expose
    def discoveryStep(self, type, devname, **kwargs):
        """
        Do a step of iterative device discovery.  Can start either from just a type or we can take
        an existing device config and ask it for refinements.
        """
        pages.require("system_admin")
        pages.postOnly()
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"

        current = kwargs

        if devname and devname in devices.remote_devices:
            # If possible just use the actual object
            d = devices.remote_devices[devname]
            c = copy.deepcopy(d.config)
            c.update(kwargs)
            current = c
            obj = d
        else:
            obj = None
            d = getDeviceType(type)

        d = d.discover_devices(
            current,
            current_device=devices.remote_devices.get(devname, None),
            intent="step",
        )

        return pages.get_template("devices/discoverstep.html").render(
            data=d, current=current, name=devname, obj=obj
        )

    @cherrypy.expose
    def createDevice(self, name=None, **kwargs):
        "Actually create the new device"
        pages.require("system_admin")
        pages.postOnly()
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"

        name = name or kwargs.get("name", None)
        m = r = None
        with modules_state.modulesLock:
            if "module" in kwargs:
                m = str(kwargs["module"])
                r = str(kwargs["resource"])
                name = r
                del kwargs["module"]
                del kwargs["resource"]
                d = {i: kwargs[i] for i in kwargs if not i.startswith("temp.")}
                d["name"] = name

                # Set these as the default
                kwargs["kaithem.read_perms"] = "view_devices"
                kwargs["kaithem.write_perms"] = "write_devices"

                modules_state.ActiveModules[m][r] = {
                    "resource-type": "device",
                    "device": d,
                }
                modules_state.modulesHaveChanged()
            else:
                raise RuntimeError(
                    "Creating devices outside of modules is no longer supported."
                )
                if not name:
                    raise RuntimeError("No name?")
                d = {i: str(kwargs[i]) for i in kwargs if not i.startswith("temp.")}

            if name in devices.remote_devices:
                devices.remote_devices[name].close()
            devices.remote_devices[name] = makeDevice(name, kwargs)

            if m and r:
                storeDeviceInModule(d, m, r)
            else:
                raise RuntimeError(
                    "Creating devices outside of modules is no longer supported."
                )
                devices.device_data[name] = d
                saveDevice(name)

            devices.remote_devices[name].parentModule = m
            devices.remote_devices[name].parentResource = r
            devices.remote_devices_atomic = devices.wrcopy(devices.remote_devices)
            messagebus.post_message("/devices/added/", name)

        saveDevice(name)

        raise cherrypy.HTTPRedirect("/devices")

    @cherrypy.expose
    def createDevicePage(self, name, module="", resource="", **kwargs):
        "Ether create a 'blank' device, or, if supported, show the custom page"
        pages.require("system_admin")
        pages.postOnly()
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"

        tp = getDeviceType(kwargs["type"])
        assert tp

        return pages.get_template("devices/createpage.html").render(
            name=name, type=kwargs["type"], module=module, resource=resource
        )

    @cherrypy.expose
    def deleteDevice(self, name, **kwargs):
        pages.require("system_admin")
        cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"

        name = name or kwargs["name"]
        return pages.get_template("devices/confirmdelete.html").render(name=name)

    @cherrypy.expose
    def toggletarget(self, name, **kwargs):
        pages.postOnly()
        x = devices.remote_devices[name]

        perms = x.config.get("kaithem.write_perms", "").strip() or "system_admin"

        for i in perms.split(","):
            pages.require(i)

        if "switch" in x.tagpoints:
            x.tagpoints["switch"].value = 1 if not x.tagpoints["switch"].value else 0

    @cherrypy.expose
    def settarget(self, name, tag, value="", **kwargs):
        pages.postOnly()
        x = devices.remote_devices[name]

        perms = x.config.get("kaithem.write_perms", "").strip() or "system_admin"

        for i in perms.split(","):
            pages.require(i)

        if tag in x.tagpoints:
            x.tagpoints[tag].value = value

    @cherrypy.expose
    def dimtarget(self, name, tag, value="", **kwargs):
        "Set a color tagpoint to a dimmed version of it."
        pages.postOnly()
        x = devices.remote_devices[name]

        perms = x.config.get("kaithem.write_perms", "").strip() or "system_admin"

        for i in perms.split(","):
            pages.require(i)

        if tag in x.tagpoints:
            try:
                x.tagpoints[tag].value = (
                    colorzero.Color.from_string(x.tagpoints[tag].value)
                    * colorzero.Luma(value)
                ).html
            except Exception:
                x.tagpoints[tag].value = (
                    colorzero.Color.from_rgb(1, 1, 1) * colorzero.Luma(value)
                ).html

    @cherrypy.expose
    def triggertarget(self, name, tag, **kwargs):
        pages.postOnly()
        x = devices.remote_devices[name]

        perms = x.config.get("kaithem.write_perms", "").strip() or "system_admin"

        for i in perms.split(","):
            pages.require(i)

        if tag in x.tagpoints:
            x.tagpoints[tag].value = x.tagpoints[tag].value + 1

    @cherrypy.expose
    def deletetarget(self, **kwargs):
        pages.require("system_admin")
        pages.postOnly()
        name = kwargs["name"]
        with modules_state.modulesLock:
            x = devices.remote_devices[name]
            # Delete bookkeep removes it from device data if present
            delete_bookkeep(name, "delete_conf_dir" in kwargs)

            if x.parentModule:
                modules_state.rawDeleteResource(
                    x.parentModule, x.parentResource or name
                )
                modules_state.modulesHaveChanged()

            # no zombie reference
            del x

            devices.remote_devices_atomic = wrcopy(devices.remote_devices)
            # Gotta be aggressive about ref cycle breaking!
            gc.collect()
            time.sleep(0.1)
            gc.collect()
            time.sleep(0.2)
            gc.collect()

            saveDevice(name)
            messagebus.post_message("/devices/removed/", name)

        raise cherrypy.HTTPRedirect("/devices")