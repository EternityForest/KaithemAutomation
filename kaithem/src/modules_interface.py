# SPDX-FileCopyrightText: Copyright 2015 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


import copy
import logging
import os
import weakref

import cherrypy
import quart
import quart.utils
import structlog
import yaml
from quart import request
from quart.ctx import copy_current_request_context
from scullery import scheduling, workers

from . import auth, dialogs, directories, messagebus, module_actions, modules, modules_state, pages, quart_app, unitsofmeasure, util
from .modules_state import in_folder
from .util import url

syslog = structlog.get_logger("system")
searchable = {"event": ["setup", "trigger", "action"], "page": ["body"]}


prev_versions: dict[tuple, dict] = {}


def get_f_size(name, i):
    try:
        return unitsofmeasure.si_format_number(os.path.getsize(modules_state.file_resource_paths[name, i]))
    except Exception:
        return "Could not get size"


def urlForPath(module, path):
    return (
        "/modules/module/"
        + url(module)
        + "/resource/"
        + "/".join([url(i.replace("\\", "\\\\").replace("/", "\\/")) for i in path[0].split("/")[:-1]])
    )


def getDesc(module):
    try:
        return module["__description"]["text"]
    except Exception:
        return "No module description found"


def sorted_module_path_list(name: str, path: list):
    return sorted(
        sorted(modules_state.ls_folder(name, "/".join(path))),
        key=lambda x: (modules_state.ActiveModules[name][x]["resource_type"], x),
    )


def breadcrumbs(path):
    temp_p = ""
    for i in path.split("/"):
        temp_p += f"{i}/"
        yield temp_p[:-1]


module_page_context = {
    "si_format_number": unitsofmeasure.si_format_number,
    "url": util.url,
    "file_resource_paths": modules.file_resource_paths,
    "external_module_locations": modules.external_module_locations,
    "getModuleHash": modules_state.getModuleHash,
    "getModuleWordHash": modules_state.getModuleWordHash,
    "pages": pages,
    "unitsofmeasure": unitsofmeasure,
    "util": util,
    "scheduling": scheduling,
    "modules_state": modules_state,
    "modules": modules,
    "os": os,
    "weakref": weakref,
    "getDesc": getDesc,
    "in_folder": in_folder,
    "urlForPath": urlForPath,
    "sorted_module_path_list": sorted_module_path_list,
    "get_f_size": get_f_size,
    "hasattr": hasattr,
    "breadcrumbs": breadcrumbs,
}


def searchModules(search, max_results=100, start=0, mstart=0):
    pointer = mstart
    results = []
    x = [None, None]
    for i in sorted(modules_state.ActiveModules.keys(), reverse=True)[mstart:]:
        x = searchModuleResources(i, search, max_results, start)
        if x[0]:
            results.append((i, x[0]))
        max_results -= len(x[0])
        start = 0
        pointer += 1
        if not max_results:
            return (results, max(0, pointer - 1), x[1])
    return (results, max(0, pointer - 1), x[1])


def searchModuleResources(modulename, search, max_results=100, start=0):
    search = search.lower()
    m = modules_state.ActiveModules[modulename]
    results = []
    pointer = start
    for i in sorted(m.keys(), reverse=True)[start:]:
        if not max_results > 0:
            return (results, pointer)
        pointer += 1
        if m[i]["resource_type"] in searchable:
            if search in i.lower():
                results.append(i)
                max_results -= 1
                continue
            for j in searchable[m[i]["resource_type"]]:
                x = str(m[i][j]).lower().find(search)
                if x > 0:
                    results.append(i)
                    max_results -= 1
                    break
    return (results, pointer)


# The class defining the interface to allow the user to perform generic create/delete/upload functionality.


@quart_app.app.route("/modules/module/<module>/uploadResource", methods=["POST"])
async def uploadResource(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    upl = None
    for name, file in (await request.files).items():
        upl = file
    kwargs = await request.form

    if not upl:
        raise RuntimeError("No file uploaded")

    @copy_current_request_context
    def f():
        f = b""

        path = kwargs["path"].split("/") + [kwargs["filename"].split(".")[0]]
        path = "/".join([i for i in path if i])

        while True:
            d = upl.read(8192)
            if not d:
                break
            f = f + d

        d2 = yaml.load(f.decode(), yaml.SafeLoader)

        if path in modules_state.ActiveModules[module]:
            raise RuntimeError("Path exists")

        modules_state.rawInsertResource(module, path, d2)
        modules.handleResourceChange(module, path)
        return quart.redirect(f"/modules/module/{util.url(module)}")

    return await quart.utils.run_sync(f)()


@quart_app.app.route("/modules/module/<module>/download_resource/<obj>")
def download_resource(module, obj):
    pages.require("view_admin_info")
    if modules_state.ActiveModules[module][obj]["resource_type"] in modules_state.additionalTypes:
        modules_state.additionalTypes[modules_state.ActiveModules[module][obj]["resource_type"]].flush_unsaved(module, obj)
    r = quart.Response(
        yaml.dump(modules_state.ActiveModules[module][obj]), headers={"Content-Disposition": f'attachment; filename="{obj}.yaml"'}
    )
    return r


@quart_app.app.route("/modules/module/<module>/scanfiles", methods=["POST"])
def scanfiles(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    modules.autoGenerateFileRefResources(modules_state.ActiveModules[module], module)
    return quart.redirect(f"/modules/module/{util.url(module)}")


@quart_app.app.route("/modules/module/<module>/runevent", methods=["POST"])
async def runevent(module):
    kwargs = await request.form
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    @copy_current_request_context
    def f():
        from .plugins import CorePluginEventResources

        CorePluginEventResources.manualRun((module, kwargs["name"]))
        return quart.redirect(f"/modules/module/{util.url(module)}")

    return await quart.utils.run_sync(f)()


@quart_app.app.route("/modules/module/<module>/runeventdialog/<evt>")
async def runeventdialog(module, evt):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    d = dialogs.SimpleDialog("Run event manually")
    d.text_input("name", default=evt)
    d.submit_button("Run")
    return d.render(f"/modules/module/{url(module)}/runevent")


@quart_app.app.route("/modules/module/<module>/getfileresource/<resource>")
async def getfileresource(module, resource):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    d = modules.getModuleDir(module)
    folder = os.path.join(d, "__filedata__")
    data_basename = modules_state.file_resource_paths[module, resource]
    dataname = os.path.join(folder, data_basename)
    if os.path.isfile(dataname):
        return await quart.send_file(dataname)
    else:
        raise FileNotFoundError(f"File not found: {dataname}")


@quart_app.app.route("/modules/module/<module>/action/<resource>")
async def action(module):
    kwargs = await request.form

    @copy_current_request_context
    def f():
        m = module_actions.get_action(kwargs["action"], {"module": module, "path": kwargs["dir"]})
        return quart.redirect(f"/action_step/{m.id}")

    return await quart.utils.run_sync(f)()


@quart_app.app.route("/modules/module/<module>/addfileresource/<target>")
async def addfileresource(module, target):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    path = request.args.get("dir", "")

    # path[1] tells what type of resource is being created and addResourceDispatcher returns the appropriate crud screen
    return pages.get_template("modules/uploadfileresource.html").render(module=module, path=path)


@quart_app.app.route("/modules/module/<module>/uploadfileresourcetarget", methods=["POST"])
async def uploadfileresourcetarget(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    kwargs = await request.form
    path = kwargs["dir"]
    file = None
    for k, v in (await request.files).items():
        file = v
    assert file

    @copy_current_request_context
    def f():
        d = modules.getModuleDir(module)
        folder = os.path.join(d, "__filedata__")

        os.makedirs(folder, exist_ok=True)
        data_basename = kwargs["name"]

        dataname = data_basename
        if len(path) > 1:
            dataname = f"{path[1]}/{dataname}"

        dataname = os.path.join(folder, dataname)

        inputfile = file

        os.makedirs(os.path.dirname(dataname), exist_ok=True)

        syslog.info(f"User uploaded file resource to {dataname}")
        with open(dataname, "wb") as f:
            while True:
                d = inputfile.file.read(8192)
                if not d:
                    break
                f.write(d)

        with modules_state.modulesLock:

            def insertResource(r):
                modules_state.rawInsertResource(module, data_basename, r)

            # END BLOCK OF COPY PASTED CODE.

            modules_state.file_resource_paths[module, data_basename] = dataname
            d = {
                "resource_type": "internal_fileref",
                "serve": "serve" in kwargs,
                "target": "$MODULERESOURCES/" + util.url(data_basename, modules.safeFnChars),
            }

            # Preserve existing metadata
            if data_basename in modules_state.ActiveModules[module]:
                d2 = copy.deepcopy(modules_state.ActiveModules[module])
                d2.update(d)
                d = d2

            insertResource(d)
            modules.handleResourceChange(module, data_basename)
            modules_state.recalcModuleHashes()
        if len(path) > 1:
            return quart.redirect(f"/modules/module/{util.url(module)}/resource/{util.url(path[1])}")
        else:
            return quart.redirect(f"/modules/module/{util.url(module)}")

    return await quart.utils.run_sync(f)()


@quart_app.app.route("/modules/actions/<module>")
def actions(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.render_jinja_template(
        "modules/module_actions.j2.html",
        name=module,
        module_actions=module_actions,
    )


@quart_app.app.route("/modules/search/<module>")
async def search(module):
    kwargs = await request.form
    start = mstart = 0
    if "mstart" in kwargs:
        mstart = int(kwargs["mstart"])
    if "start" in kwargs:
        start = int(kwargs["start"])
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    @copy_current_request_context
    def f():
        if not module == "__all__":
            return pages.get_template("modules/search.html").render(
                search=kwargs["search"],
                name=module,
                results=searchModuleResources(module, kwargs["search"], 100, start),
            )
        else:
            return pages.get_template("modules/search.html").render(
                search=kwargs["search"],
                name=module,
                results=searchModules(kwargs["search"], 100, start, mstart),
            )

    return await quart.utils.run_sync(f)()


# This lets the user download a module as a zip file with yaml encoded resources
@quart_app.app.route("/modules/yamldownload/<module>")
def yamldownload(module):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    cherrypy.response.headers["Content-Disposition"] = 'attachment; filename="%s"' % util.url(
        f"{module[:-4]}_{modules_state.getModuleWordHash(module[:-4]).replace(' ', '')}.zip"
    )

    cherrypy.response.headers["Content-Type"] = "application/zip"
    try:
        return modules_state.getModuleAsYamlZip(
            module[:-4] if module.endswith(".zip") else module,
        )
    except Exception:
        logging.exception("Failed to handle zip download request")
        raise


# This lets the user upload modules
@quart_app.app.route("/modules/upload")
def upload():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("modules/upload.html").render()
    # This lets the user upload modules


@quart_app.app.route("/modules/uploadtarget", methods=["POST"])
async def uploadtarget():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    # Can't actuslly use def in a for loop usually but it;s fine since there;s only one
    for name, file in (await request.files).items():

        @copy_current_request_context
        def f():
            modules_state.recalcModuleHashes()
            modules.load_modules_from_zip(file, replace="replace" in request.args)

        workers.do(f)

    messagebus.post_message("/system/modules/uploaded", {"user": pages.getAcessingUser()})
    return quart.redirect("/modules")


@quart_app.app.route("/modules")
def modules_index():
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("modules/index.html").render(ActiveModules=modules_state.ActiveModules)


@quart_app.app.route("/modules/library")
def library():
    # Require permissions and render page. A lotta that in this file.
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("modules/library.html").render()


@quart_app.app.route("/modules/module/<module>/newmoduletarget", methods=["POST"])
async def loadlibmodule(module):
    "Load a module from the library"
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    name = (await request.form)["name"]
    name = name or module

    @copy_current_request_context
    def f():
        if name in modules_state.ActiveModules:
            return quart.redirect("/errors/alreadyexists")

        modules.loadModule(os.path.join(directories.datadir, "modules", module), name)

        modules_state.recalcModuleHashes()

        modules.bookkeeponemodule(name)
        auth.importPermissionsFromModules()
        modules.saveModule(modules_state.ActiveModules[name], name)
        return quart.redirect("/modules")

    return await quart.utils.run_sync(f)()


# @cherrypy.expose
# def manual_run(self,module, resource):
# These modules handle their own permissions
# if isinstance(EventReferences[module,resource], ManualEvent):
# EventReferences[module,resource].run()
# else:
# raise RuntimeError("Event does not support running manually")
