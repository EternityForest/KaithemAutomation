# SPDX-FileCopyrightText: Copyright 2024 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

# This file just has the basic core editing and viewing handlers

import copy
import os
import shutil
import time

import quart
import quart.utils
import structlog
from quart import request
from quart.ctx import copy_current_request_context
from scullery import messagebus

from kaithem.src import (
    auth,
    dialogs,
    directories,
    module_actions,
    modules,
    modules_state,
    pages,
    quart_app,
    util,
)
from kaithem.src.modules_interface.page_context import module_page_context
from kaithem.src.modules_state import (
    check_forbidden,
    external_module_locations,
    prev_versions,
)
from kaithem.src.util import url

logger = structlog.get_logger(__name__)


@quart_app.app.route("/modules/module/<module>/resource/<path:resource>")
def resource_page(module, resource):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    kwargs = request.args
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    version = kwargs.get("version", "__live__")

    with modules_state.modulesLock:
        resourceinquestion = modules_state.ActiveModules[module][resource]

        if version == "__old__":
            resourceinquestion = prev_versions[(module, resource)]

        elif version == "__default__":
            try:
                resourceinquestion = modules_state.ActiveModules[module][
                    resource
                ]["versions"]["__draft__"]
                version = "__draft__"
            except KeyError:
                version = "__live__"
        else:
            version = "__live__"

        assert isinstance(resourceinquestion, dict)

        if "resource_type" not in resourceinquestion:
            raise RuntimeError("No resource type found")

        if resourceinquestion["resource_type"] == "permission":
            try:
                pages.require("view_admin_info")
            except PermissionError:
                return pages.loginredirect(pages.geturl())

            d = dialogs.SimpleDialog(f"Permission: {resource} in {module}")
            d.text_input(
                "description",
                default=modules_state.ActiveModules[module][resource][
                    "description"
                ],
            )
            d.submit_button("Submit")
            return d.render(
                f"/modules/module/{url(module)}/updateresource/{url(resource)}"
            )

        if resourceinquestion["resource_type"] == "directory":
            try:
                pages.require("view_admin_info")
            except PermissionError:
                return pages.loginredirect(pages.geturl())

            return pages.render_jinja_template(
                "modules/module.j2.html",
                module=modules_state.ActiveModules[module],
                name=module,
                path=resource.split("/"),
                fullpath=f"{module}/{resource}",
                module_actions=module_actions,
                ro=modules_state.is_module_readonly(module),
                **module_page_context,
            )

        # This is for the custom resource types interface stuff.
        return modules_state.additionalTypes[
            resourceinquestion["resource_type"]
        ].edit_page(module, resource, resourceinquestion)


@quart_app.app.route("/modules/module/<module>/addresource/<type>")
def addresource(module, type):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    if modules_state.is_module_readonly(module):
        raise PermissionError("Module is read only")

    path = request.args.get("dir", "")

    if type in ("permission", "directory"):
        d = dialogs.SimpleDialog(f"New {type.capitalize()} in {module}")
        d.text_input("name")

        if type in ("permission",):
            d.text_input("description")

        d.submit_button("Create")
        return d.render(
            f"/modules/module/{url(module)}/addresourcetarget/{type}",
            hidden_inputs={"dir": path},
        )
    else:
        return modules_state.additionalTypes[type].create_page(module, path)


@quart_app.app.route(
    "/modules/module/<module>/addresourcetarget/<rtype>/<path:path>",
    methods=["POST"],
)
@quart_app.app.route(
    "/modules/module/<module>/addresourcetarget/<rtype>", methods=["POST"]
)
async def addresourcetarget(module, rtype, path=""):
    """Path can be passed as the dir kwarg, or as path component in the url.
    Expects a name in the kwargs
    """
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    if modules_state.is_module_readonly(module):
        raise PermissionError("Module is read only")

    kwargs = dict(await request.form)
    kwargs.update(request.args)

    check_forbidden(kwargs["name"])

    @copy_current_request_context
    def f():
        type = rtype
        name = kwargs["name"]
        path = path = kwargs.get("dir", "")

        modules_state.recalcModuleHashes()

        check_forbidden(kwargs["name"])

        name_with_path = kwargs["name"]
        if path:
            name_with_path = f"{path}/{name_with_path}"
        x = module.split("/")
        name_with_path = "/".join(x[1:] + [name_with_path])
        root = x[0]

        def insertResource(r):
            r["resource_timestamp"] = int(time.time() * 1000000)
            modules_state.rawInsertResource(root, name_with_path, r)

        with modules_state.modulesLock:
            # Check if a resource by that name is already there
            if name_with_path in modules_state.ActiveModules[root]:
                return quart.redirect("/errors/alreadyexists")

            if type == "directory":
                insertResource({"resource_type": "directory"})
                return quart.redirect(f"/modules/module/{util.url(module)}")

            elif type == "permission":
                insertResource(
                    {
                        "resource_type": "permission",
                        "description": kwargs["description"],
                    }
                )
                # has its own lock
                auth.importPermissionsFromModules()  # sync auth's list of permissions

            else:
                rt = modules_state.additionalTypes[type]
                # If create returns None, assume it doesn't want to insert a module or handles it by itself
                r = rt.on_create_request(module, name, kwargs)
                rt._validate(r)
                if r:
                    insertResource(r)
                    rt.on_load(module, name_with_path, r)

            messagebus.post_message(
                "/system/notifications",
                "User "
                + pages.getAcessingUser()
                + " added resource "
                + name_with_path
                + " of type "
                + type
                + " to module "
                + root,
            )
            # Take the user straight to the resource page
            return quart.redirect(
                f"/modules/module/{util.url(module)}/resource/{util.url(name_with_path)}"
            )

    return await f()


# This goes to a dispatcher that takes into account the type of resource and updates everything about the resource.
@quart_app.app.route(
    "/modules/module/<module>/updateresource/<path:resource>", methods=["POST"]
)
async def resource_update_handler(module, resource):
    kwargs = await request.form
    kwargs = dict(kwargs)
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    if modules_state.is_module_readonly(module):
        raise PermissionError("Module is read only")

    @copy_current_request_context
    def f():
        newname = kwargs.get("newname", "")

        modules_state.recalcModuleHashes()

        compiled_object = None

        with modules_state.modulesLock:
            resourceobj = dict(
                copy.deepcopy(modules_state.ActiveModules[module][resource])
            )

            if "module_lock" in modules_state.get_module_metadata(module):
                raise PermissionError("Module is locked")

            if "resource_lock" in resourceobj and resourceobj["resource_lock"]:
                raise PermissionError(
                    "This resource can only be edited by manually removing the resource_lock from the file."
                )

            old_resource = copy.deepcopy(resourceobj)

            t = resourceobj["resource_type"]
            resourceobj["resource_timestamp"] = int(time.time() * 1000000)

            if t in modules_state.additionalTypes:
                n = modules_state.additionalTypes[t].on_update_request(
                    module, resource, old_resource, kwargs
                )
                modules_state.additionalTypes[t].validate(n)

                if n:
                    resourceobj = n
                    modules_state.ActiveModules[module][resource] = n
                    modules_state.save_resource(module, resource, n, resource)

            elif t == "permission":
                resourceobj["description"] = kwargs["description"]
                # has its own lock
                modules_state.save_resource(
                    module, resource, resourceobj, newname
                )

            else:
                modules_state.save_resource(
                    module, resource, resourceobj, newname
                )

            # We can pass a compiled object for things like events that would otherwise
            # have to have a test compile then the real compile
            modules.handleResourceChange(module, resource, compiled_object)

            prev_versions[(module, resource)] = old_resource

        messagebus.post_message(
            "/system/notifications",
            "User "
            + pages.getAcessingUser()
            + " modified resource "
            + resource
            + " of module "
            + module,
        )
        r = resource
        if "name" in kwargs:
            r = kwargs["name"]
        if "GoNow" in kwargs:
            return quart.redirect(f"/pages/{module}/{r}")
        # Return user to the module page. If name has a folder, return the
        # user to it;s containing folder.
        x = r.split("/")
        if len(x) > 1:
            return quart.redirect(
                "/modules/module/"
                + util.url(module)
                + "/resource/"
                + "/".join([util.url(i) for i in x[:-1]])
                + "#resources"
            )
        else:
            # +'/resource/'+util.url(resource))
            return quart.redirect(
                f"/modules/module/{util.url(module)}#resources"
            )

    return await f()


@quart_app.app.route("/modules/deletemodule")
def deletemodule():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    d = dialogs.SimpleDialog("Delete Module")
    d.text_input("name")
    d.submit_button("Submit")
    return d.render("/modules/deletemoduletarget")


# POST target for CRUD screen for deleting module
@quart_app.app.route("/modules/deletemoduletarget", methods=["POST"])
async def deletemoduletarget():
    kwargs = await quart.request.form
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    pages.postOnly()
    m = modules_state.get_module_metadata(kwargs["name"])

    if "module_lock" in m and m["module_lock"]:
        raise PermissionError(
            "This module can only be deleted by manually removing the module_lock from the file."
        )

    modules.rmModule(
        kwargs["name"], f"Module Deleted by {pages.getAcessingUser()}"
    )
    messagebus.post_message(
        "/system/notifications",
        f"User {pages.getAcessingUser()} Deleted module {kwargs['name']}",
    )

    return quart.redirect("/modules")


@quart_app.app.route("/modules/module/<module>/deleteresource/<path:target>")
async def deleteresource(module, target):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    if modules_state.is_module_readonly(module):
        raise PermissionError("Module is read only")

    if "module_lock" in modules_state.get_module_metadata(module):
        raise PermissionError("Module is locked")

    d = dialogs.SimpleDialog(f"Delete resource in {module}")
    d.text_input("name", default=target)
    d.submit_button("Submit")
    return d.render(f"/modules/module/{url(module)}/deleteresourcetarget")


@quart_app.app.route("/modules/module/<module>/moveresource/<path:target>")
async def moveresource(module, target):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    if modules_state.is_module_readonly(module):
        raise PermissionError("Module is read only")

    if "module_lock" in modules_state.get_module_metadata(module):
        raise PermissionError("Module is locked")

    d = dialogs.SimpleDialog(f"Move resource in {module}")
    d.text_input("name", default=target)
    d.text_input("newname", default=target, title="New Name")
    d.text_input("newmodule", default=module, title="New Module")
    d.submit_button("Submit")
    return d.render(f"/modules/module/{url(module)}/moveresourcetarget")


@quart_app.app.route(
    "/modules/module/<module>/deleteresourcetarget", methods=["POST"]
)
async def deleteresourcetarget(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    kwargs = await quart.request.form

    if modules_state.is_module_readonly(module):
        raise PermissionError("Module is read only")

    @copy_current_request_context
    def f():
        if "module_lock" in modules_state.get_module_metadata(module):
            raise PermissionError("Module is locked")

        if kwargs["name"] not in modules_state.ActiveModules[module]:
            fn = modules_state.filename_for_file_resource(
                module, kwargs["name"]
            )
            if os.path.isfile(fn):
                os.remove(fn)

        else:
            resourceobj = modules_state.ActiveModules[module][kwargs["name"]]

            if "resource_lock" in resourceobj and resourceobj["resource_lock"]:
                raise PermissionError(
                    "This resource can only be edited by manually removing the resource_lock from the file."
                )

            modules.rmResource(
                module,
                kwargs["name"],
                f"Resource Deleted by {pages.getAcessingUser()}",
            )

        messagebus.post_message(
            "/system/notifications",
            "User "
            + pages.getAcessingUser()
            + " deleted resource "
            + kwargs["name"]
            + " from module "
            + module,
        )
        messagebus.post_message(
            "/system/modules/deletedresource",
            {
                "ip": quart.request.remote_addr,
                "user": pages.getAcessingUser(),
                "module": module,
                "resource": kwargs["name"],
            },
        )
        if len(kwargs["name"].split("/")) > 1:
            return quart.redirect(
                "/modules/module/"
                + util.url(module)
                + "/resource/"
                + util.url(util.module_onelevelup(kwargs["name"]))
            )
        else:
            return quart.redirect(f"/modules/module/{util.url(module)}")

    return await f()


@quart_app.app.route(
    "/modules/module/<module>/moveresourcetarget", methods=["POST"]
)
async def moveresourcetarget(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    kwargs = await quart.request.form

    if modules_state.is_module_readonly(module):
        raise PermissionError("Module is read only")

    @copy_current_request_context
    def f():
        resourceobj = modules_state.ActiveModules[module][kwargs["name"]]

        if "module_lock" in modules_state.get_module_metadata(module):
            raise PermissionError("Module is locked")

        if "resource_lock" in resourceobj and resourceobj["resource_lock"]:
            raise PermissionError(
                "This resource can only be edited by manually removing the resource_lock from the file."
            )

        # Allow / to move stuf to dirs
        check_forbidden(kwargs["newname"].replace("/", ""))

        modules.mvResource(
            module, kwargs["name"], kwargs["newmodule"], kwargs["newname"]
        )
        return quart.redirect(f"/modules/module/{util.url(module)}")

    return await f()


@quart_app.app.route(
    "/modules/module/<module>/updateresourcemetadata/<path:resource>",
    methods=["POST"],
)
async def update_resource_metadata(module, resource):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    kwargs = await quart.request.form
    with modules_state.modulesLock:
        d = modules_state.mutable_copy_resource(
            modules_state.ActiveModules[module][resource]
        )
        for i in kwargs:
            d[i] = kwargs[i]

        modules_state.rawInsertResource(module, resource, d)

    path = "/".join(resource.split("/")[:-1])
    if len(path) > 0:
        return quart.redirect(
            f"/modules/module/{util.url(module)}/resource/{path}"
        )
    else:
        return quart.redirect(f"/modules/module/{util.url(module)}")


@quart_app.app.route(
    "/modules/module/<module>/resource/<path:resource>/metadata"
)
async def resource_metadata_page(module, resource):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    d = dialogs.SimpleDialog(f"Update resource metadata in {module}")
    d.begin_section("Display")

    builtin_img = os.listdir(
        os.path.join(directories.datadir, "static", "img", "16x9")
    )
    builtin_img = [("16x9/" + i, i) for i in builtin_img]
    builtin_img.sort()

    for i in modules_state.ActiveModules.keys():
        file_data_dir = os.path.join(
            modules_state.getModuleDir(i),
            "__filedata__",
            "media",
            "16x9",
        )

        if os.path.isdir(file_data_dir):
            for j in os.listdir(file_data_dir):
                if j.endswith(
                    (".png", ".jpg", ".avif", ".png", ".gif", ".svg")
                ):
                    fn = os.path.join(file_data_dir, j)
                    if os.path.isfile(fn):
                        builtin_img.append(
                            (
                                f"16x9/{j}",
                                j,
                            )
                        )

    d.text_input(
        "resource_label_image",
        title="Label Image URL",
        suggestions=builtin_img,
        default=modules_state.ActiveModules[module][resource].get(
            "resource_label_image", ""
        ),
    )

    lnk = "/excalidraw-plugin/edit?"
    lnk += f"module={module}&resource=media/resource_labels/{resource}.excalidraw.png"
    lnk += f"&callback=/modules/set_label_image/{module}/{resource}&ratio_guide=16_9"
    d.link("Draw with Excalidraw", lnk)
    d.end_section()

    d.submit_button("", title="Save")

    return d.render(
        f"/modules/module/{util.url(module)}/updateresourcemetadata/{util.url(resource)}"
    )


@quart_app.app.route("/modules/module/<module>/update", methods=["POST"])
async def module_update(module):
    kwargs = await quart.request.form
    "This is the target used to change the name and description(basic info) of a module"
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    @copy_current_request_context
    def f():
        m = modules_state.get_module_metadata(module)

        if "module_lock" in m and m["module_lock"]:
            raise PermissionError(
                "This module can only be edited by manually removing the module_lock from the file."
            )

        if not kwargs["name"] == module:
            if modules_state.is_module_readonly(module):
                raise PermissionError("Module is read only, cannot rename")

            if "." in kwargs:
                raise ValueError("No . in resource name")

        with modules_state.modulesLock:
            old_external_module_location = external_module_locations.get(
                module, None
            )
            new_location = kwargs.get("location", None).strip() or None

            # Where it *would* be if it was an internal module
            internal_location = os.path.join(
                directories.vardir, "modules", "data", kwargs["name"]
            )

            # Where the ext location marker would be.
            # We don't yet know if it actually exists.
            ext_location_marker = os.path.join(
                directories.moduledir,
                "data",
                f"__{util.url(module)}.location",
            )
            if not new_location == old_external_module_location:
                logger.info(f"Moving module {module} to {new_location}")

                if not new_location:
                    if not old_external_module_location:
                        raise RuntimeError(
                            "Module was not external or internal, state may be corrupt"
                        )

                    # This means saving to an internal module

                    if os.path.exists(internal_location):
                        raise ValueError(
                            f"Module {kwargs['name']} already exists as internal"
                        )
                    shutil.copytree(
                        old_external_module_location, internal_location
                    )
                    # Delete the external module location marker
                    if os.path.isfile(ext_location_marker):
                        os.remove(ext_location_marker)

                    if module in external_module_locations:
                        del external_module_locations[module]
                else:
                    # This means saving to an external module
                    if os.path.exists(new_location):
                        if os.listdir(new_location):
                            raise ValueError(
                                f"Module {kwargs['name']} already exists as external"
                            )

                    old_location = (
                        old_external_module_location or internal_location
                    )

                    shutil.copytree(
                        old_location,
                        new_location,
                    )

                    external_module_locations[kwargs["name"]] = new_location

            # Missing descriptions have caused a lot of bugs
            if "__metadata__" in modules_state.ActiveModules[module]:
                dsc = dict(
                    copy.deepcopy(
                        modules_state.ActiveModules[module]["__metadata__"]
                    )
                )
                dsc["description"] = kwargs["description"]

            else:
                dsc = {
                    "resource_type": "module-description",
                    "description": kwargs["description"],
                    "resource_timestamp": int(time.time() * 1000000),
                }

            modules_state.rawInsertResource(module, "__metadata__", dsc)

            # Renaming reloads the entire module.
            # TODO This needs to handle custom resource types if we ever implement them.
            if not kwargs["name"] == module:
                if module in external_module_locations:
                    external_module_locations[kwargs["name"]] = (
                        external_module_locations.pop(module)
                    )

                modules_state.ActiveModules[kwargs["name"]] = (
                    modules_state.ActiveModules.pop(module)
                )

                for rt in modules_state.additionalTypes:
                    modules_state.additionalTypes[rt].on_delete_module(module)

                # Calll the deleter
                for r, obj in modules_state.ActiveModules[
                    kwargs["name"]
                ].items():
                    rt = obj["resource_type"]
                    assert isinstance(rt, str)
                    if rt in modules_state.additionalTypes:
                        modules_state.additionalTypes[rt].on_delete(
                            module, r, obj
                        )

                # And calls this function the generate the new cache
                modules.bookkeeponemodule(kwargs["name"], update=True)
                # Just for fun, we should probably also sync the permissions
                auth.importPermissionsFromModules()
                modules_state.importFiledataFolderStructure(kwargs["name"])

        modules_state.recalcModuleHashes()
        return quart.redirect(f"/modules/module/{util.url(kwargs['name'])}")

    return await f()
