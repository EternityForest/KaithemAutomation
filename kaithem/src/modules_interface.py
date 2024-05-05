# SPDX-FileCopyrightText: Copyright 2015 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


import copy
import json
import logging
import mimetypes
import os
import time
import weakref

import cherrypy
import yaml
from cherrypy.lib.static import serve_file
from scullery import scheduling

from . import (
    auth,
    dialogs,
    directories,
    messagebus,
    module_actions,
    modules,
    modules_state,
    pages,
    unitsofmeasure,
    util,
)
from .modules import check_forbidden, external_module_locations
from .modules_state import in_folder
from .util import url

syslog = logging.getLogger("system")
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


def followAttributes(root, path):
    pathlist = util.split_escape(path, ",", escape="\\")
    for i in pathlist:
        # Following references works by specifying the exact obj id
        if i.startswith("r"):
            import gc

            for ref in gc.get_referrers(root):
                if str(id(ref)) in i:
                    root = ref
        elif i.startswith("t"):
            root = root[tuple(json.loads(i[1:]))]
        elif i.startswith("a"):
            root = getattr(root, i[1:])
        elif i.startswith("i"):
            root = root[int(i[1:])]
        # This one is mostly for weak refs. Watch out we don't make any refs stick around that shouldn't
        elif i.startswith("c"):
            root = root()
        else:
            root = root[util.unurl(i[1:])]
    return root


# The class defining the interface to allow the user to perform generic create/delete/upload functionality.


class WebInterface:
    @cherrypy.expose
    def actions(self, module, **path):
        pages.require("system_admin")
        return pages.render_jinja_template(
            "modules/module_actions.j2.html",
            name=module,
            path=path,
            module_actions=module_actions,
        )

    @cherrypy.expose
    def search(self, module, **kwargs):
        start = mstart = 0
        if "mstart" in kwargs:
            mstart = int(kwargs["mstart"])
        if "start" in kwargs:
            start = int(kwargs["start"])
        pages.require("system_admin")
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

    # This lets the user download a module as a zip file with yaml encoded resources
    @cherrypy.expose
    def yamldownload(self, module):
        pages.require("view_admin_info")
        cherrypy.response.headers["Content-Disposition"] = 'attachment; filename="%s"' % util.url(
            f"{module[:-4]}_{modules_state.getModuleHash(module[:-4])}.zip"
        )

        cherrypy.response.headers["Content-Type"] = "application/zip"
        try:
            return modules.getModuleAsYamlZip(
                module[:-4] if module.endswith(".zip") else module,
            )
        except Exception:
            logging.exception("Failed to handle zip download request")
            raise

    # This lets the user upload modules
    @cherrypy.expose
    def upload(self):
        pages.require("system_admin")
        return pages.get_template("modules/upload.html").render()
        # This lets the user upload modules

    @cherrypy.expose
    def uploadtarget(self, modulesfile, **kwargs):
        pages.require("system_admin")
        pages.postOnly()
        modules_state.modulesHaveChanged()
        for i in modules.load_modules_from_zip(modulesfile.file, replace="replace" in kwargs):
            pass

        messagebus.post_message("/system/modules/uploaded", {"user": pages.getAcessingUser()})
        raise cherrypy.HTTPRedirect("/modules/")

    @cherrypy.expose
    def index(self):
        # Require permissions and render page. A lotta that in this file.
        pages.require("view_admin_info")
        return pages.get_template("modules/index.html").render(ActiveModules=modules_state.ActiveModules)

    @cherrypy.expose
    def library(self):
        # Require permissions and render page. A lotta that in this file.
        pages.require("view_admin_info")
        return pages.get_template("modules/library.html").render()

    @cherrypy.expose
    def newmodule(self):
        pages.require("system_admin")
        d = dialogs.SimpleDialog("Add New Module")
        d.text_input("name", title="Name of New Module")
        d.text("Choose an existing dir to load that module.")
        d.text_input("location", title="Save location(Blank: auto in kaithem dir)")
        d.submit_button("Submit")
        return d.render("/modules/newmoduletarget")

    # @cherrypy.expose
    # def manual_run(self,module, resource):
    # These modules handle their own permissions
    # if isinstance(EventReferences[module,resource], ManualEvent):
    # EventReferences[module,resource].run()
    # else:
    # raise RuntimeError("Event does not support running manually")

    # CRUD screen to delete a module
    @cherrypy.expose
    def deletemodule(self):
        pages.require("system_admin")
        d = dialogs.SimpleDialog("Delete Module")
        d.text_input("name")
        d.submit_button("Submit")
        return d.render("/modules/deletemoduletarget")
        return pages.get_template("modules/delete.html").render()

    # POST target for CRUD screen for deleting module
    @cherrypy.expose
    def deletemoduletarget(self, **kwargs):
        pages.require("system_admin")
        pages.postOnly()
        modules.rmModule(kwargs["name"], f"Module Deleted by {pages.getAcessingUser()}")
        messagebus.post_message(
            "/system/notifications",
            f"User {pages.getAcessingUser()} Deleted module {kwargs['name']}",
        )

        raise cherrypy.HTTPRedirect("/modules")

    @cherrypy.expose
    def newmoduletarget(self, **kwargs):
        pages.require("system_admin")
        pages.postOnly()

        check_forbidden(kwargs["name"])

        # If there is no module by that name, create a blank template and the scope obj
        with modules_state.modulesLock:
            if kwargs["name"] in modules_state.ActiveModules:
                return pages.get_template("error.html").render(info=" A module already exists by that name,")
            modules.newModule(kwargs["name"], kwargs.get("location", None))
            raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(kwargs['name'])}")

    @cherrypy.expose
    def loadlibmodule(self, module, name=""):
        "Load a module from the library"
        pages.require("system_admin")
        pages.postOnly()
        name = name or module

        if name in modules_state.ActiveModules:
            raise cherrypy.HTTPRedirect("/errors/alreadyexists")

        modules.loadModule(os.path.join(directories.datadir, "modules", module), name)

        modules_state.modulesHaveChanged()

        modules.bookkeeponemodule(name)
        auth.importPermissionsFromModules()
        modules.saveModule(modules_state.ActiveModules[name], name)
        raise cherrypy.HTTPRedirect("/modules")

    @cherrypy.expose
    # This function handles HTTP requests of or relating to one specific already existing module.
    # The URLs that this function handles are of the form /modules/module/<modulename>[something?]
    def module(self, module, *path, **kwargs):
        root = module.split("/")[0]
        modulepath = module.split("/")[1:]
        fullpath = module
        if len(path) > 2:
            fullpath += f"/{path[2]}"
        # If we are not performing an action on a module just going to its page
        if not path:
            pages.require("view_admin_info")

            return pages.render_jinja_template(
                "modules/module.j2.html",
                module=modules_state.ActiveModules[root],
                name=root,
                path=modulepath,
                fullpath=fullpath,
                module_actions=module_actions,
                **module_page_context,
            )

        else:
            if path[0] == "download_resource":
                pages.require("view_admin_info")
                cherrypy.response.headers["Content-Disposition"] = "attachment; filename=" + path[1] + ".yaml"
                return yaml.dump(modules_state.ActiveModules[root][path[1]])

            if path[0] == "scanfiles":
                pages.require("system_admin")
                pages.postOnly()
                modules.autoGenerateFileRefResources(modules_state.ActiveModules[root], root)
                raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(root)}")

            if path[0] == "runevent":
                pages.require("system_admin")
                pages.postOnly()
                from .plugins import CorePluginEventResources

                CorePluginEventResources.manualRun((module, kwargs["name"]))
                raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(root)}")

            if path[0] == "runeventdialog":
                # There might be a password or something important in the actual module object. Best to restrict who can access it.
                pages.require("system_admin")
                cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"

                d = dialogs.SimpleDialog("Run event manually")
                d.text_input("name", default=path[1])
                d.submit_button("Run")
                return d.render(f"/modules/module/{url(module)}/runevent")

            if path[0] == "obj":
                # There might be a password or something important in the actual module object. Best to restrict who can access it.
                pages.require("system_admin")
                pages.postOnly()

                if not len(path) > 1:
                    raise ValueError("No object specified")

                if path[1] == "module":
                    obj = modules_state.scopes[root]
                    objname = f"Module Obj: {root}"

                if path[1] == "event":
                    from .plugins import CorePluginEventResources

                    obj = CorePluginEventResources._events_by_module_resource[root, path[2]].pymodule
                    objname = f"Event: {path[2]}"

                # Inspector should prob be its own module since it does all this.
                if path[1] == "sys":
                    import kaithem

                    obj = kaithem
                    objname = "PythonRoot"

                if path[1] == "sysmodule":
                    import sys

                    obj = sys
                    objname = "sys"

                if "objname" in kwargs:
                    objname = kwargs["objname"]

                if "objpath" not in kwargs:
                    return pages.get_template("modules/modulescope.html").render(kwargs=kwargs, name=root, obj=obj, objname=objname)
                else:
                    return pages.get_template("obj_insp.html").render(
                        objpath=kwargs["objpath"],
                        objname=objname,
                        obj=followAttributes(obj, kwargs["objpath"]),
                        getGC=kwargs.get("gcinfo", False),
                    )

            if path[0] == "uploadresource":
                pages.require("system_admin", noautoreturn=True)

                if len(path) > 1:
                    x = path[1]
                else:
                    x = ""
                d = dialogs.SimpleDialog(f"Upload resource in {root}")
                d.file_input("file")
                d.text_input("filename")
                d.submit_button("Submit")
                return d.render(f"/modules/module/{url(module)}/uploadresourcetarget", hidden_inputs={"path": x})

            if path[0] == "uploadresourcetarget":
                pages.require("system_admin", noautoreturn=True)
                pages.postOnly()
                inputfile = kwargs["file"]
                f = b""

                path = kwargs["path"].split("/") + [kwargs["filename"].split(".")[0]]
                path = "/".join([i for i in path if i])

                while True:
                    d = inputfile.file.read(8192)
                    if not d:
                        break
                    f = f + d

                d2 = yaml.load(f.decode(), yaml.SafeLoader)

                if path in modules_state.ActiveModules[root]:
                    raise RuntimeError("Path exists")

                modules_state.rawInsertResource(module, path, d2)
                modules.handleResourceChange(module, path)
                raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(root)}")

            # This gets the interface to add a page
            if path[0] == "addresource":
                cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
                if len(path) > 2:
                    x = path[2]
                else:
                    x = ""
                # path[1] tells what type of resource is being created and addResourceDispatcher returns the appropriate crud screen
                return addResourceDispatcher(module, path[1], x)

            # This case handles the POST request from the new resource target
            if path[0] == "addresourcetarget":
                pages.require("system_admin")
                pages.postOnly()
                if len(path) > 2:
                    x = path[2]
                elif len(path) == 2:
                    x = ""
                else:
                    raise ValueError("Expected resource type")

                check_forbidden(kwargs["name"])
                return addResourceTarget(module, path[1], kwargs["name"], kwargs, x)

            # This case shows the information and editing page for one resource
            if path[0] == "resource":
                cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
                version = "__default__"
                if len(path) > 2:
                    version = path[2]
                return resourceEditPage(module, path[1], version, kwargs)

            # This goes to a dispatcher that takes into account the type of resource and updates everything about the resource.
            if path[0] == "updateresource":
                return resourceUpdateTarget(module, path[1], kwargs)

            # This goes to a dispatcher that takes into account the type of resource and updates everything about the resource.
            if path[0] == "reloadresource":
                pages.require("system_admin")
                pages.postOnly()
                modules.reloadOneResource(module, path[1])
                return resourceEditPage(module, path[1], kwargs=kwargs)

            if path[0] == "getfileresource":
                pages.require("system_admin")
                d = modules.getModuleDir(module)
                folder = os.path.join(d, "__filedata__")
                data_basename = modules_state.file_resource_paths[module, path[1]]
                dataname = os.path.join(folder, data_basename)
                if os.path.isfile(dataname):
                    return serve_file(
                        dataname,
                        content_type=mimetypes.guess_type(path[1], False)[0] or "application/x-unknown",
                        disposition="inline;",
                        name=path[1],
                    )

            if path[0] == "action":
                if len(path) > 1:
                    x = path[1]
                else:
                    x = ""
                m = module_actions.get_action(kwargs["action"], {"module": module, "path": x})

                raise cherrypy.HTTPRedirect(f"/action_step/{m.id}")

            # This gets the interface to add a page
            if path[0] == "addfileresource":
                cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
                pages.require("system_admin")
                if len(path) > 1:
                    x = path[1]
                else:
                    x = ""
                # path[1] tells what type of resource is being created and addResourceDispatcher returns the appropriate crud screen
                return pages.get_template("modules/uploadfileresource.html").render(module=module, path=x)

            # This goes to a dispatcher that takes into account the type of resource and updates everything about the resource.
            if path[0] == "uploadfileresourcetarget":
                pages.require("system_admin", noautoreturn=True)
                pages.postOnly()
                d = modules.getModuleDir(module)
                folder = os.path.join(d, "__filedata__")

                os.makedirs(folder, exist_ok=True)
                data_basename = kwargs["name"]

                dataname = data_basename
                if len(path) > 1:
                    dataname = f"{path[1]}/{dataname}"

                dataname = os.path.join(folder, dataname)

                inputfile = kwargs["file"]

                os.makedirs(os.path.dirname(dataname), exist_ok=True)

                syslog.info(f"User uploaded file resource to {dataname}")
                with open(dataname, "wb") as f:
                    while True:
                        d = inputfile.file.read(8192)
                        if not d:
                            break
                        f.write(d)

                with modules_state.modulesLock:
                    # BEGIN BLOCK OF CODE COPY PASTED FROM ANOTHER PART OF CODE. I DO NOT REALLY UNDERSTAND IT
                    # Wow is this code ever ugly. Bascially we are going to pack the path and the module together.
                    escapedName = kwargs["name"].replace("\\", "\\\\").replace("/", "\\/")
                    if len(path) > 1:
                        escapedName = f"{path[1]}/{escapedName}"
                    x = module.split("/")
                    escapedName = "/".join(x[1:] + [escapedName])
                    root = x[0]

                    def insertResource(r):
                        modules_state.ActiveModules[root][escapedName] = r
                        modules.saveResource(root, escapedName, r)

                    # END BLOCK OF COPY PASTED CODE.

                    modules_state.file_resource_paths[root, escapedName] = dataname
                    d = {
                        "resource_type": "internal_fileref",
                        "serve": "serve" in kwargs,
                        "target": "$MODULERESOURCES/" + util.url(escapedName, modules.safeFnChars),
                    }

                    # Preserve existing metadata
                    if escapedName in modules_state.ActiveModules[root]:
                        d2 = copy.deepcopy(modules_state.ActiveModules[root])
                        d2.update(d)
                        d = d2

                    insertResource(d)
                    modules.handleResourceChange(root, escapedName)
                    modules_state.modulesHaveChanged()
                if len(path) > 1:
                    raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(root)}/resource/{util.url(path[1])}")
                else:
                    raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(root)}")

            # This returns a page to delete any resource by name
            if path[0] == "deleteresource":
                cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
                pages.require("system_admin", noautoreturn=True)

                d = dialogs.SimpleDialog(f"Delete resource in {root}")
                d.text_input("name", default=path[1])
                d.submit_button("Submit")
                return d.render(f"/modules/module/{url(root)}/deleteresourcetarget")

            if path[0] == "moveresource":
                cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
                pages.require("system_admin", noautoreturn=True)

                d = dialogs.SimpleDialog(f"Move resource in {root}")
                d.text_input("name", default=path[1])
                d.text_input("newname", default=path[1], title="New Name")
                d.text_input("newmodule", default=root, title="New Module")
                d.submit_button("Submit")
                return d.render(f"/modules/module/{url(root)}/moveresourcetarget")

            # This handles the POST request to actually do the deletion
            if path[0] == "deleteresourcetarget":
                pages.require("system_admin")
                pages.postOnly()
                modules.rmResource(
                    module,
                    kwargs["name"],
                    f"Resource Deleted by {pages.getAcessingUser()}",
                )

                messagebus.post_message(
                    "/system/notifications",
                    "User " + pages.getAcessingUser() + " deleted resource " + kwargs["name"] + " from module " + module,
                )
                messagebus.post_message(
                    "/system/modules/deletedresource",
                    {
                        "ip": cherrypy.request.remote.ip,
                        "user": pages.getAcessingUser(),
                        "module": module,
                        "resource": kwargs["name"],
                    },
                )
                if len(kwargs["name"].split("/")) > 1:
                    raise cherrypy.HTTPRedirect(
                        "/modules/module/" + util.url(module) + "/resource/" + util.url(util.module_onelevelup(kwargs["name"]))
                    )
                else:
                    raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(module)}")

            if path[0] == "moveresourcetarget":
                pages.require("system_admin")
                pages.postOnly()

                # Allow / to move stuf to dirs
                check_forbidden(kwargs["newname"].replace("/", ""))

                modules.mvResource(module, kwargs["name"], kwargs["newmodule"], kwargs["newname"])
                raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(module)}")

            # This is the target used to change the name and description(basic info) of a module
            if path[0] == "update":
                pages.require("system_admin")
                pages.postOnly()
                modules_state.modulesHaveChanged()
                if not kwargs["name"] == root:
                    if "." in kwargs:
                        raise ValueError("No . in resource name")
                with modules_state.modulesLock:
                    if "location" in kwargs and kwargs["location"]:
                        external_module_locations[kwargs["name"]] = kwargs["location"]
                        # We can't just do a delete and then set, what if something odd happens between?
                        if not kwargs["name"] == root and root in external_module_locations:
                            del external_module_locations[root]
                    else:
                        # We must delete this before deleting the actual external_module_locations entry
                        # If this fails, we can still save, and will reload correctly.
                        # But if there was no entry, but there was a file,
                        # It would reload from the external, but save to the internal,
                        # Which would be very confusing. We want to load from where we saved.

                        # If we somehow have no file but an entry, saving will remake the file.
                        # If there's no entry, we will only be able to save by saving the whole state.
                        if os.path.isfile(
                            os.path.join(
                                directories.moduledir,
                                "data",
                                f"__{util.url(root)}.location",
                            )
                        ):
                            if root in external_module_locations:
                                os.remove(external_module_locations[root])

                        if root in external_module_locations:
                            external_module_locations.pop(root)
                    # Missing descriptions have caused a lot of bugs
                    if "__description" in modules_state.ActiveModules[root]:
                        modules_state.ActiveModules[root]["__description"]["text"] = kwargs["description"]
                    else:
                        modules_state.ActiveModules[root]["__description"] = {
                            "resource_type": "module-description",
                            "text": kwargs["description"],
                        }

                    # Renaming reloads the entire module.
                    # TODO This needs to handle custom resource types if we ever implement them.
                    if not kwargs["name"] == root:
                        modules_state.ActiveModules[kwargs["name"]] = modules_state.ActiveModules.pop(root)

                        for rt in modules_state.additionalTypes:
                            modules_state.additionalTypes[rt].ondeletemodule(root)

                        # Calll the deleter
                        for r, obj in modules_state.ActiveModules[kwargs["name"]].items():
                            rt = modules_state.ActiveModules[kwargs["name"]]["resource_type"]
                            assert isinstance(rt, str)
                            if rt in modules_state.additionalTypes:
                                modules_state.additionalTypes[rt].ondelete(root, r, obj)

                        # And calls this function the generate the new cache
                        modules.bookkeeponemodule(kwargs["name"], update=True)
                        # Just for fun, we should probably also sync the permissions
                        auth.importPermissionsFromModules()

                raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(kwargs['name'])}")


# Return a CRUD screen to create a new resource taking into the type of resource the user wants to create


def addResourceDispatcher(module, type, path):
    pages.require("system_admin")

    # Return a crud to add a new permission
    if type in ("permission", "directory"):
        d = dialogs.SimpleDialog(f"New {type.capitalize()} in {module}")
        d.text_input("name")

        if type in ("permission",):
            d.text_input("description")

        d.submit_button("Create")
        return d.render(f"/modules/module/{url(module)}/addresourcetarget/{type}/{url(path)}")
    else:
        return modules_state.additionalTypes[type].createpage(module, path)


# The target for the POST from the CRUD to actually create the new resource
# Basically it takes a module, a new resource name, and a type, and creates a template resource


def addResourceTarget(module, type, name, kwargs, path):
    pages.require("system_admin")
    pages.postOnly()
    modules_state.modulesHaveChanged()

    check_forbidden(kwargs["name"])

    name_with_path = kwargs["name"]
    if path:
        name_with_path = f"{path}/{name_with_path}"
    x = module.split("/")
    name_with_path = "/".join(x[1:] + [name_with_path])
    root = x[0]

    def insertResource(r):
        r["resource_timestamp"] = int(time.time() * 1000000)
        modules_state.ActiveModules[root][name_with_path] = r
        modules.saveResource(root, name_with_path, r)

    with modules_state.modulesLock:
        # Check if a resource by that name is already there
        if name_with_path in modules_state.ActiveModules[root]:
            raise cherrypy.HTTPRedirect("/errors/alreadyexists")

        if type == "directory":
            insertResource({"resource_type": "directory"})
            raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(module)}")

        elif type == "permission":
            insertResource({"resource_type": "permission", "description": kwargs["description"]})
            # has its own lock
            auth.importPermissionsFromModules()  # sync auth's list of permissions

        else:
            rt = modules_state.additionalTypes[type]
            # If create returns None, assume it doesn't want to insert a module or handles it by itself
            r = rt.oncreaterequest(module, name, kwargs)
            rt._validate(r)
            if r:
                insertResource(r)
                rt.onload(module, name_with_path, r)

        messagebus.post_message(
            "/system/notifications",
            "User " + pages.getAcessingUser() + " added resource " + name_with_path + " of type " + type + " to module " + root,
        )
        # Take the user straight to the resource page
        raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(module)}/resource/{util.url(name_with_path)}")


# show a edit page for a resource. No side effect here so it only requires the view permission
def resourceEditPage(module, resource, version="default", kwargs={}):
    pages.require("view_admin_info")
    cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"
    with modules_state.modulesLock:
        resourceinquestion = modules_state.ActiveModules[module][resource]

        if version == "__old__":
            resourceinquestion = prev_versions[(module, resource)]

        elif version == "__default__":
            try:
                resourceinquestion = modules_state.ActiveModules[module][resource]["versions"]["__draft__"]
                version = "__draft__"
            except KeyError:
                version = "__live__"
        else:
            version = "__live__"

        assert isinstance(resourceinquestion, dict)

        if "resource_type" not in resourceinquestion:
            logging.warning(f"No resource type found for {resource}")
            return

        if resourceinquestion["resource_type"] == "permission":
            return permissionEditPage(module, resource)

        if resourceinquestion["resource_type"] == "internal_fileref":
            if "require_permissions" in resourceinquestion:
                requiredpermissions = resourceinquestion["require_permissions"]
            else:
                requiredpermissions = []
            return pages.get_template("modules/fileresources/fileresource.html").render(
                module=module,
                resource=resource,
                resourceobj=resourceinquestion,
                requiredpermissions=requiredpermissions,
            )

        if resourceinquestion["resource_type"] == "directory":
            pages.require("view_admin_info")

            return pages.render_jinja_template(
                "modules/module.j2.html",
                module=modules_state.ActiveModules[module],
                name=module,
                path=resource.split("/"),
                fullpath=f"{module}/{resource}",
                module_actions=module_actions,
                **module_page_context,
            )

        # This is for the custom resource types interface stuff.
        return modules_state.additionalTypes[resourceinquestion["resource_type"]].editpage(module, resource, resourceinquestion)


def permissionEditPage(module, resource):
    pages.require("view_admin_info")

    d = dialogs.SimpleDialog(f"Permission: {resource} in {module}")
    d.text_input(
        "description",
        default=modules_state.ActiveModules[module][resource]["description"],
    )
    d.submit_button("Submit")
    return d.render(f"/modules/module/{url(module)}/updateresource/{url(resource)}/")


# The actual POST target to modify a resource. Context dependant based on resource type.
def resourceUpdateTarget(module, resource, kwargs):
    newname = kwargs.get("newname", "")

    pages.require("system_admin", noautoreturn=True)
    pages.postOnly()
    modules_state.modulesHaveChanged()

    compiled_object = None

    with modules_state.modulesLock:
        resourceobj = modules_state.ActiveModules[module][resource]

        old_resource = copy.deepcopy(resourceobj)

        t = resourceobj["resource_type"]
        resourceobj["resource_timestamp"] = int(time.time() * 1000000)

        if t in modules_state.additionalTypes:
            n = modules_state.additionalTypes[t].onupdaterequest(module, resource, old_resource, kwargs)
            modules_state.additionalTypes[t].validate(n)

            if n:
                resourceobj = n
                modules_state.ActiveModules[module][resource] = n
                modules.saveResource(module, resource, n, resource)

        elif t == "permission":
            resourceobj["description"] = kwargs["description"]
            # has its own lock
            modules.saveResource(module, resource, resourceobj, newname)

        elif t == "internal_fileref":
            # If this was autogenerated make sure it actually gets saved now
            resourceobj.pop("ephemeral", False)

            resourceobj["serve"] = "serve" in kwargs
            # has its own lock
            resourceobj["allow_xss"] = "allow_xss" in kwargs
            resourceobj["allow_origins"] = [i.strip() for i in kwargs["allow_origins"].split(",")]
            resourceobj["mimetype"] = kwargs["mimetype"]

            # Just like pages, file resources are permissioned
            resourceobj["require_permissions"] = []
            for i in kwargs:
                # Since HTTP args don't have namespaces we prefix all the
                # permission checkboxes with permission
                if i[:10] == "Permission":
                    if kwargs[i] == "true":
                        resourceobj["require_permissions"].append(i[10:])

            modules.saveResource(module, resource, resourceobj, newname)

        else:
            modules.saveResource(module, resource, resourceobj, newname)

        # We can pass a compiled object for things like events that would otherwise
        # have to have a test compile then the real compile
        modules.handleResourceChange(module, resource, compiled_object)

        prev_versions[(module, resource)] = old_resource

    messagebus.post_message(
        "/system/notifications",
        "User " + pages.getAcessingUser() + " modified resource " + resource + " of module " + module,
    )
    r = resource
    if "name" in kwargs:
        r = kwargs["name"]
    if "GoNow" in kwargs:
        raise cherrypy.HTTPRedirect(f"/pages/{module}/{r}")
    # Return user to the module page. If name has a folder, return the
    # user to it;s containing folder.
    x = r.split("/")
    if len(x) > 1:
        raise cherrypy.HTTPRedirect(
            "/modules/module/" + util.url(module) + "/resource/" + "/".join([util.url(i) for i in x[:-1]]) + "#resources"
        )
    else:
        # +'/resource/'+util.url(resource))
        raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(module)}#resources")
