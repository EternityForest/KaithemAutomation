# SPDX-FileCopyrightText: Copyright 2015 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


import copy
import os

import quart
import quart.utils
import structlog
from quart import request
from quart.ctx import copy_current_request_context

from kaithem.src.modules_interface.page_context import module_page_context
from kaithem.src.modules_state import ActiveModules, check_forbidden

from .. import (
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
from ..util import url

# Here's where most of the actual page routes are
from . import (
    fileresources,  # noqa: F401
    importexport,  # noqa: F401
    resources,  # noqa: F401
    search,  # noqa: F401
)

logger = structlog.get_logger(__name__)


@quart_app.app.route("/modules/module/<module>/scanfiles", methods=["POST"])
def scanfiles(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    modules_state.importFiledataFolderStructure(module)
    modules_state.recalcModuleHashes()
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

    return await f()


@quart_app.app.route("/modules/module/<module>/runeventdialog/<evt>")
@quart_app.wrap_sync_route_handler
def runeventdialog(module, evt):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    d = dialogs.SimpleDialog("Run event manually")
    d.text_input("name", default=evt)
    d.submit_button("Run")
    return d.render(f"/modules/module/{url(module)}/runevent")


@quart_app.app.route("/modules/module/<module>/action", methods=["POST"])
@quart_app.wrap_sync_route_handler
def action(module, action, dir):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    m = module_actions.get_action(action, {"module": module, "path": dir})

    d = dialogs.SimpleDialog(m.title)
    d.submit_button("Begin Action")

    return d.render(f"/action_step/{m.id}")


@quart_app.app.route("/modules/actions/<module>")
@quart_app.wrap_sync_route_handler
def actions(module, dir):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.render_jinja_template(
        "modules/module_actions.j2.html",
        name=module,
        module_actions=module_actions,
        dir=dir,
    )


# This lets the user upload modules
@quart_app.app.route("/modules/upload")
def upload():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("modules/upload.html").render()
    # This lets the user upload modules


@quart_app.app.route("/modules")
def modules_index():
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("modules/index.html").render(
        ActiveModules=modules_state.ActiveModules
    )


@quart_app.app.route("/modules/library")
def library():
    # Require permissions and render page. A lotta that in this file.
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("modules/library.html").render()


@quart_app.app.route("/modules/newmoduletarget", methods=["POST"])
async def newmoduletarget():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    kwargs = dict(await request.form)

    @copy_current_request_context
    def f():
        check_forbidden(kwargs["name"])

        # If there is no module by that name, create a blank template and the scope obj
        with modules_state.modulesLock:
            if kwargs["name"] in modules_state.ActiveModules:
                return pages.get_template("error.html").render(
                    info=" A module already exists by that name,"
                )
            modules.newModule(kwargs["name"], kwargs.get("location", None))
            return quart.redirect(f"/modules/module/{util.url(kwargs['name'])}")

    return await f()


@quart_app.app.route("/modules/loadlibmodule/<module>", methods=["POST"])
async def loadlibmodule(module):
    "Load a module from the library"
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    name = module

    @copy_current_request_context
    def f():
        if name in modules_state.ActiveModules:
            return quart.redirect("/errors/alreadyexists")

        modules.loadModule(
            os.path.join(directories.datadir, "modules", module), name
        )

        auth.importPermissionsFromModules()
        modules.saveModule(modules_state.ActiveModules[name], name)
        modules.bookkeeponemodule(name)

        return quart.redirect("/modules")

    return await f()


@quart_app.app.route("/modules/newmodule")
def newmodule():
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    d = dialogs.SimpleDialog("Add New Module")
    d.text_input("name", title="Name of New Module")
    d.text("Choose an existing dir to load that module.")
    d.text_input("location", title="Save location(Blank: auto in kaithem dir)")
    d.submit_button("Submit")
    return d.render("/modules/newmoduletarget")


@quart_app.app.route("/modules/module/<module>")
def indvidual_module(module):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    fullpath = module

    return pages.render_jinja_template(
        "modules/module.j2.html",
        module=ActiveModules[module],
        name=module,
        path="",
        fullpath=fullpath,
        module_actions=module_actions,
        **module_page_context,
    )


@quart_app.app.route("/modules/label_image/<module>/<path:path>/")
async def get_resource_label_image(module: str, path: str):
    pages.require("view_admin_info")

    @quart.ctx.copy_current_request_context
    def f():
        data = modules_state.ActiveModules[module][path]

        mf = modules_state.getModuleDir(module)
        mf = os.path.join(mf, "__filedata__/media")

        if os.path.isfile(os.path.join(mf, data["resource_label_image"])):
            return os.path.join(mf, data["resource_label_image"])

    fn = await f()
    return await quart.send_file(fn)


@quart_app.app.route(
    "/modules/set_label_image/<module>/<path:path>", methods=["POST"]
)
async def set_resource_label(module: str, path: str):
    pages.require("system_admin")
    kw = dict(await quart.request.form)
    kw.update(quart.request.args)
    data = modules_state.ActiveModules[module][path]

    mf = modules_state.getModuleDir(module)
    mf = os.path.join(mf, "__filedata__/media")

    data = modules_state.ActiveModules[module][path]
    data2 = dict(copy.deepcopy(data))
    data2["resource_label_image"] = kw["resource"][len("media/") :]
    modules_state.rawInsertResource(module, path, data2)
    return "OK"


# def manual_run(self,module, resource):
# These modules handle their own permissions
# if isinstance(EventReferences[module,resource], ManualEvent):
# EventReferences[module,resource].run()
# else:
# raise RuntimeError("Event does not support running manually")
