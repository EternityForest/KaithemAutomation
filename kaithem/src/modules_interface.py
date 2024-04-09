# SPDX-FileCopyrightText: Copyright 2015 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


import copy
import json
import logging
import mimetypes
import os
import time
import traceback
import weakref

import cherrypy
from cherrypy.lib.static import serve_file
from scullery import scheduling

from . import (
    auth,
    dialogs,
    directories,
    messagebus,
    modules,
    modules_state,
    newevt,
    pages,
    schemas,
    unitsofmeasure,
    usrpages,
    util,
)
from .config import config
from .modules import external_module_locations
from .util import url

syslog = logging.getLogger("system")
searchable = {"event": ["setup", "trigger", "action"], "page": ["body"]}


prev_versions: dict[tuple, dict] = {}


def get_time(ev):
    try:
        if not newevt.EventReferences[ev].nextruntime:
            return 0
        return newevt.dt_to_ts(newevt.EventReferences[ev].nextruntime or 0, newevt.EventReferences[ev].tz)
    except Exception:
        return -1


def get_next_run(name, i):
    xyz = get_time((name, i))
    unitsofmeasure.strftime()
    if xyz == 0:
        xyz = "<b>Not Scheduled to Run</b>"
    elif xyz == -1:
        xyz = "Error getting next run time, try refreshing page again."
    else:
        xyz = unitsofmeasure.strftime(xyz)

    return xyz


# n is the module name
# f is the folder we are checking if it is in, including the module name
# r is the path of the resource


def in_folder(r, f, n):
    # Get the path as a list, including the module name
    r = [n] + util.split_escape(r, "/", "\\")
    # Get the path of the folder
    f = util.split_escape(f, "/", "\\")
    # make sure the resource path is one longer than module
    if not len(r) == len(f) + 1:
        return False
    x = 0
    for i in f:
        if not r[x] == i:
            return False
        x += 1
    return True


def get_f_size(name, i):
    try:
        return unitsofmeasure.si_format_number(os.path.getsize(modules_state.fileResourceAbsPaths[name, i]))
    except Exception:
        return "Could not get size"


def urlForPath(module, path):
    return (
        "/modules/module/"
        + url(module)
        + "/resource/"
        + "/".join([url(i.replace("\\", "\\\\").replace("/", "\\/")) for i in util.split_escape(path[0], "/", "\\")[:-1]])
    )


def getDesc(module):
    try:
        return module["__description"]["text"]
    except Exception:
        return "No module description found"


def sorted_module_path_list(name: str, path: list):
    return sorted(
        sorted(modules_state.ls_folder(name, "/".join(path))),
        key=lambda x: (modules_state.ActiveModules[name][x]["resource-type"], x),
    )


def breadcrumbs(path):
    temp_p = ""
    for i in util.split_escape(path, "/", "\\"):
        temp_p += f"{i}/"
        yield temp_p[:-1]


module_page_context = {
    "si_format_number": unitsofmeasure.si_format_number,
    "url": util.url,
    "fileResourceAbsPaths": modules.fileResourceAbsPaths,
    "external_module_locations": modules.external_module_locations,
    "getModuleHash": modules_state.getModuleHash,
    "getModuleWordHash": modules_state.getModuleWordHash,
    "pages": pages,
    "newevt": newevt,
    "usrpages": usrpages,
    "unitsofmeasure": unitsofmeasure,
    "util": util,
    "scheduling": scheduling,
    "modules_state": modules_state,
    "modules": modules,
    "os": os,
    "weakref": weakref,
    "getDesc": getDesc,
    "in_folder": in_folder,
    "get_time": get_time,
    "get_next_run": get_next_run,
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


def searchTags(search):
    p = []
    from . import tagpoints

    for i in tagpoints.configTagData:
        if search in json.dumps(tagpoints.configTagData[i].data) or search in i:
            p.append(i)
    return p


def searchModuleResources(modulename, search, max_results=100, start=0):
    search = search.lower()
    m = modules_state.ActiveModules[modulename]
    results = []
    pointer = start
    for i in sorted(m.keys(), reverse=True)[start:]:
        if not max_results > 0:
            return (results, pointer)
        pointer += 1
        if m[i]["resource-type"] in searchable:
            if search in i.lower():
                results.append(i)
                max_results -= 1
                continue
            for j in searchable[m[i]["resource-type"]]:
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
                tagr=searchTags(kwargs["search"]),
            )

    # This lets the user download a module as a zip file with yaml encoded resources
    @cherrypy.expose
    def yamldownload(self, module):
        pages.require("view_admin_info")
        if config["downloads-include-md5-in-filename"]:
            cherrypy.response.headers["Content-Disposition"] = 'attachment; filename="%s"' % util.url(
                f"{module[:-4]}_{modules_state.getModuleHash(module[:-4])}.zip"
            )
        cherrypy.response.headers["Content-Type"] = "application/zip"
        try:
            return modules.getModuleAsYamlZip(
                module[:-4] if module.endswith(".zip") else module,
                noFiles=not pages.canUserDoThis("system_admin"),
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
        d = dialogs.Dialog("Add New Module")
        d.text_input("name", title="Name of New Module")
        d.text("Choose an existing dir to load that module.")
        d.text_input("location", title="Save location(Blank: auto in kaithem dir)")
        d.submit_button("Submit")
        return d.render("/modules/newmoduletarget")

    # @cherrypy.expose
    # def manual_run(self,module, resource):
    # These modules handle their own permissions
    # if isinstance(EventReferences[module,resource], newevt.ManualEvent):
    # EventReferences[module,resource].run()
    # else:
    # raise RuntimeError("Event does not support running manually")

    # CRUD screen to delete a module
    @cherrypy.expose
    def deletemodule(self):
        pages.require("system_admin")
        d = dialogs.Dialog("Delete Module")
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
        global scopes
        pages.require("system_admin")
        pages.postOnly()

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
        root = util.split_escape(module, "/")[0]
        modulepath = util.split_escape(module, "/")[1:]
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
                **module_page_context,
            )

        else:
            if path[0] == "scanfiles":
                pages.require("system_admin")
                pages.postOnly()
                modules.autoGenerateFileRefResources(modules_state.ActiveModules[root], root)
                raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(root)}")

            if path[0] == "runevent":
                pages.require("system_admin")
                pages.postOnly()
                newevt.manualRun((module, kwargs["name"]))
                raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(root)}")

            if path[0] == "runeventdialog":
                # There might be a password or something important in the actual module object. Best to restrict who can access it.
                pages.require("system_admin")
                cherrypy.response.headers["X-Frame-Options"] = "SAMEORIGIN"

                d = dialogs.Dialog("Run event manually")
                d.text_input("name", default=path[1])
                d.submit_button("Run")
                return d.render(f"/modules/module/{url(module)}/runevent")

            if path[0] == "obj":
                # There might be a password or something important in the actual module object. Best to restrict who can access it.
                pages.require("system_admin")
                pages.postOnly()

                if path[1] == "module":
                    obj = scopes[root]
                    objname = f"Module Obj: {root}"

                if path[1] == "event":
                    obj = newevt.EventReferences[root, path[2]].pymodule
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
                else:
                    x = ""
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
                data_basename = modules_state.fileResourceAbsPaths[module, path[1]]
                dataname = os.path.join(folder, data_basename)
                if os.path.isfile(dataname):
                    return serve_file(
                        dataname,
                        content_type=mimetypes.guess_type(path[1], False)[0] or "application/x-unknown",
                        disposition="inline;",
                        name=path[1],
                    )

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
                    x = util.split_escape(module, "/", "\\")
                    escapedName = "/".join(x[1:] + [escapedName])
                    root = x[0]

                    def insertResource(r):
                        modules_state.ActiveModules[root][escapedName] = r
                        modules.saveResource(root, escapedName, r)

                    # END BLOCK OF COPY PASTED CODE.

                    modules_state.fileResourceAbsPaths[root, escapedName] = dataname
                    d = {
                        "resource-type": "internal-fileref",
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

                d = dialogs.Dialog(f"Delete resource in {root}")
                d.text_input("name", default=path[1])
                d.submit_button("Submit")
                return d.render(f"/modules/module/{url(root)}/deleteresourcetarget")

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
                if len(util.split_escape(kwargs["name"], "/", "\\")) > 1:
                    raise cherrypy.HTTPRedirect(
                        "/modules/module/" + util.url(module) + "/resource/" + util.url(util.module_onelevelup(kwargs["name"]))
                    )
                else:
                    raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(module)}")

            # This is the target used to change the name and description(basic info) of a module
            if path[0] == "update":
                pages.require("system_admin")
                pages.postOnly()
                modules_state.modulesHaveChanged()
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
                            "resource-type": "module-description",
                            "text": kwargs["description"],
                        }

                    # Renaming reloads the entire module.
                    # TODO This needs to handle custom resource types if we ever implement them.
                    if not kwargs["name"] == root:
                        modules_state.ActiveModules[kwargs["name"]] = modules_state.ActiveModules.pop(root)
                        # UHHG. So very much code tht just syncs data structures.
                        # This gets rid of the cache under the old name
                        newevt.removeModuleEvents(root)
                        usrpages.removeModulePages(root)
                        # And calls this function the generate the new cache
                        modules.bookkeeponemodule(kwargs["name"], update=True)
                        # Just for fun, we should probably also sync the permissions
                        auth.importPermissionsFromModules()
                raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(kwargs['name'])}")


# Return a CRUD screen to create a new resource taking into the type of resource the user wants to create


def addResourceDispatcher(module, type, path):
    pages.require("system_admin")

    # Return a crud to add a new permission
    if type in ("permission", "event", "page", "directory"):
        d = dialogs.Dialog(f"New {type.capitalize()} in {module}")
        d.text_input("name")

        if type in ("permission",):
            d.text_input("description")

        if type == "page":
            d.selection("template", options=["default", "freeboard"])

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

    # Wow is this code ever ugly. Bascially we are going to pack the path and the module together.
    escapedName = kwargs["name"].replace("\\", "\\\\").replace("/", "\\/")
    if path:
        escapedName = f"{path}/{escapedName}"
    x = util.split_escape(module, "/", "\\")
    escapedName = "/".join(x[1:] + [escapedName])
    root = x[0]

    def insertResource(r):
        r["resource-timestamp"] = int(time.time() * 1000000)
        modules_state.ActiveModules[root][escapedName] = r
        modules.saveResource(root, escapedName, r)

    with modules_state.modulesLock:
        # Check if a resource by that name is already there
        if escapedName in modules_state.ActiveModules[root]:
            raise cherrypy.HTTPRedirect("/errors/alreadyexists")

        if type == "directory":
            insertResource({"resource-type": "directory"})
            raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(module)}")

        elif type == "permission":
            insertResource({"resource-type": "permission", "description": kwargs["description"]})
            # has its own lock
            auth.importPermissionsFromModules()  # sync auth's list of permissions

        elif type == "event":
            insertResource(
                {
                    "resource-type": "event",
                    "setup": "# This code runs once when the event loads.\n__doc__=''",
                    "trigger": "False",
                    "action": "pass",
                    "once": True,
                    "enable": True,
                }
            )
            # newevt maintains a cache of precompiled events that must be kept in sync with
            # the modules
            newevt.updateOneEvent(escapedName, root)

        elif type == "page":
            from . import pageresourcetemplates

            template = kwargs["template"]
            basename = util.split_escape(name, "/", "\\")[-1]
            insertResource(pageresourcetemplates.templates[template](basename))
            usrpages.updateOnePage(escapedName, root)

        else:
            # If create returns None, assume it doesn't want to insert a module or handles it by itself
            r = modules_state.additionalTypes[type].create(module, path, name, kwargs)
            if r:
                insertResource(r)
                f = modules_state.additionalTypes[type].onload
                if f:
                    f(module, name, r)

        messagebus.post_message(
            "/system/notifications",
            "User " + pages.getAcessingUser() + " added resource " + escapedName + " of type " + type + " to module " + root,
        )
        # Take the user straight to the resource page
        raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(module)}/resource/{util.url(escapedName)}")


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

        if "resource-type" not in resourceinquestion:
            logging.warning(f"No resource type found for {resource}")
            return

        if resourceinquestion["resource-type"] == "permission":
            return permissionEditPage(module, resource)

        if resourceinquestion["resource-type"] == "event":
            return pages.get_template("modules/events/event.html").render(
                module=module, name=resource, event=resourceinquestion, version=version
            )

        if resourceinquestion["resource-type"] == "internal-fileref":
            if "require-permissions" in resourceinquestion:
                requiredpermissions = resourceinquestion["require-permissions"]
            else:
                requiredpermissions = []
            return pages.get_template("modules/fileresources/fileresource.html").render(
                module=module,
                resource=resource,
                resourceobj=resourceinquestion,
                requiredpermissions=requiredpermissions,
            )

        if resourceinquestion["resource-type"] == "page":
            if "require-permissions" in resourceinquestion:
                requiredpermissions = resourceinquestion["require-permissions"]
            else:
                requiredpermissions = []

            return pages.get_template("modules/pages/page.html").render(
                module=module,
                name=resource,
                kwargs=kwargs,
                page=resourceinquestion,
                requiredpermissions=requiredpermissions,
            )

        if resourceinquestion["resource-type"] == "directory":
            pages.require("view_admin_info")

            return pages.render_jinja_template(
                "modules/module.j2.html",
                module=modules_state.ActiveModules[module],
                name=module,
                path=util.split_escape(resource, "\\"),
                fullpath=f"{module}/{resource}",
                **module_page_context,
            )

        # This is for the custom resource types interface stuff.
        return modules_state.additionalTypes[resourceinquestion["resource-type"]].editpage(module, resource, resourceinquestion)


def permissionEditPage(module, resource):
    pages.require("view_admin_info")

    d = dialogs.Dialog(f"Permission: {resource} in {module}")
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

        t = resourceobj["resource-type"]
        resourceobj["resource-timestamp"] = int(time.time() * 1000000)

        if t == "permission":
            resourceobj["description"] = kwargs["description"]
            # has its own lock
            modules.saveResource(module, resource, resourceobj, newname)

        elif t == "internal-fileref":
            # If this was autogenerated make sure it actually gets saved now
            resourceobj.pop("ephemeral", False)

            resourceobj["serve"] = "serve" in kwargs
            # has its own lock
            resourceobj["allow-xss"] = "allow-xss" in kwargs
            resourceobj["allow-origins"] = [i.strip() for i in kwargs["allow-origins"].split(",")]
            resourceobj["mimetype"] = kwargs["mimetype"]

            # Just like pages, file resources are permissioned
            resourceobj["require-permissions"] = []
            for i in kwargs:
                # Since HTTP args don't have namespaces we prefix all the
                # permission checkboxes with permission
                if i[:10] == "Permission":
                    if kwargs[i] == "true":
                        resourceobj["require-permissions"].append(i[10:])

            modules.saveResource(module, resource, resourceobj, newname)

        elif t == "event":
            compiled_object = None
            # Test compile, throw error on fail.

            if "tabtospace" in kwargs:
                actioncode = kwargs["action"].replace("\t", "    ")
                setupcode = kwargs["setup"].replace("\t", "    ")
            else:
                actioncode = kwargs["action"]
                setupcode = kwargs["setup"]

            if "enable" in kwargs:
                try:
                    # Make a copy of the old resource object and modify it
                    r2 = resourceobj.copy()
                    r2["trigger"] = kwargs["trigger"]
                    r2["action"] = actioncode
                    r2["setup"] = setupcode
                    r2["priority"] = kwargs["priority"]
                    r2["continual"] = "continual" in kwargs
                    r2["rate-limit"] = float(kwargs["ratelimit"])
                    r2["enable"] = "enable" in kwargs

                    # Test for syntax errors at least, before we do anything more
                    newevt.test_compile(setupcode, actioncode)

                    # Remove the old event even before we even do a test run of setup.
                    # If we can't do the new version just put the old one back.
                    # Todo actually put old one back
                    newevt.removeOneEvent(module, resource)
                    # Leave a delay so that effects of cleanup can fully propagate.
                    time.sleep(0.08)
                    # Make event from resource, but use our substitute modified dict
                    compiled_object = newevt.make_event_from_resource(module, resource, r2)

                except Exception:
                    if "versions" not in resourceobj:
                        resourceobj["versions"] = {}
                    if "versions" in r2:
                        r2.pop("versions")

                    resourceobj["versions"]["__draft__"] = copy.deepcopy(r2)
                    modules.saveResource(module, resource, resourceobj, newname)

                    messagebus.post_message(
                        "system/errors/misc/failedeventupdate",
                        f"In: {module} {resource}\n{traceback.format_exc(4)}",
                    )
                    raise

                # If everything seems fine, then we update the actual resource data
                modules_state.ActiveModules[module][resource] = r2
                resourceobj = r2
            # Save but don't enable
            else:
                # Make a copy of the old resource object and modify it
                r2 = resourceobj.copy()
                r2["trigger"] = kwargs["trigger"]
                r2["action"] = actioncode
                r2["setup"] = setupcode
                r2["priority"] = kwargs["priority"]
                r2["continual"] = "continual" in kwargs
                r2["rate-limit"] = float(kwargs["ratelimit"])
                r2["enable"] = False

                # Remove the old event even before we do a test compile.
                # If we can't do the new version just put the old one back.
                newevt.removeOneEvent(module, resource)
                # Leave a delay so that effects of cleanup can fully propagate.
                time.sleep(0.08)

                # If everything seems fine, then we update the actual resource data
                modules_state.ActiveModules[module][resource] = r2

            # I really need to do something about this possibly brittle bookkeeping system
            # But anyway, when the active modules thing changes we must update
            # the newevt cache thing.

            # Delete the draft if any
            try:
                del resourceobj["versions"]["__draft__"]
            except KeyError:
                pass

            modules.saveResource(module, resource, resourceobj, newname)
            resourceobj = r2

        elif t == "page":
            if "tabtospace" in kwargs:
                body = kwargs["body"].replace("\t", "    ")
            else:
                body = kwargs["body"]

            if "tabtospace" in kwargs:
                code = kwargs["code"].replace("\t", "    ")
            else:
                code = kwargs["code"]

            if "tabtospace" in kwargs:
                setupcode = kwargs["setupcode"].replace("\t", "    ")
            else:
                setupcode = kwargs["setupcode"]

            resourceobj["body"] = body
            resourceobj["theme-css-url"] = kwargs["themecss"].strip()
            resourceobj["code"] = code
            resourceobj["setupcode"] = setupcode
            resourceobj["alt-top-banner"] = kwargs["alttopbanner"]

            resourceobj["mimetype"] = kwargs["mimetype"]
            resourceobj["template-engine"] = kwargs["template-engine"]
            resourceobj["no-navheader"] = "no-navheader" in kwargs
            resourceobj["streaming-response"] = "streaming-response" in kwargs

            resourceobj["no-header"] = "no-header" in kwargs
            resourceobj["auto-reload"] = "autoreload" in kwargs
            resourceobj["allow-xss"] = "allow-xss" in kwargs
            resourceobj["allow-origins"] = [i.strip() for i in kwargs["allow-origins"].split(",")]
            resourceobj["auto-reload-interval"] = float(kwargs["autoreloadinterval"])
            # Method checkboxes
            resourceobj["require-method"] = []
            if "allow-GET" in kwargs:
                resourceobj["require-method"].append("GET")
            if "allow-POST" in kwargs:
                resourceobj["require-method"].append("POST")
            # permission checkboxes
            resourceobj["require-permissions"] = []
            for i in kwargs:
                # Since HTTP args don't have namespaces we prefix all the permission
                # checkboxes with permission
                if i[:10] == "Permission":
                    if kwargs[i] == "true":
                        resourceobj["require-permissions"].append(i[10:])

            schemas.get_validator("resources/page").validate(resourceobj)
            modules.saveResource(module, resource, resourceobj, newname)

        else:
            modules.saveResource(module, resource, resourceobj, newname)

        if "name" in kwargs:
            if not kwargs["name"] == resource:
                # Just handles the internal stuff
                modules.mvResource(module, resource, module, kwargs["name"])

        # We can pass a compiled object for things like events that would otherwise
        # have to have a test compile then the real compile
        modules.handleResourceChange(module, kwargs.get("name", resource), compiled_object)

        prev_versions[(module, resource)] = old_resource

    messagebus.post_message(
        "/system/notifications",
        "User " + pages.getAcessingUser() + " modified resource " + resource + " of module " + module,
    )
    r = resource
    if "name" in kwargs:
        r = kwargs["name"]
    if "GoNow" in kwargs:
        raise cherrypy.HTTPRedirect(usrpages.url_for_resource(module, r))
    # Return user to the module page. If name has a folder, return the
    # user to it;s containing folder.
    x = util.split_escape(r, "/", "\\")
    if len(x) > 1:
        raise cherrypy.HTTPRedirect(
            "/modules/module/" + util.url(module) + "/resource/" + "/".join([util.url(i) for i in x[:-1]]) + "#resources"
        )
    else:
        # +'/resource/'+util.url(resource))
        raise cherrypy.HTTPRedirect(f"/modules/module/{util.url(module)}#resources")
