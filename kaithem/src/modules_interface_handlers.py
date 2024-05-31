# SPDX-FileCopyrightText: Copyright 2024 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

# This file just has the basic core editing and viewing handlers


import quart
import quart.utils
from quart import request
from scullery import messagebus

from kaithem.src import dialogs, module_actions, modules, pages, quart_app
from kaithem.src.modules_interface import (
    addResourceDispatcher,
    addResourceTarget,
    module_page_context,
    resourceEditPage,
    resourceUpdateTarget,
    url,
)
from kaithem.src.modules_state import ActiveModules, check_forbidden


@quart_app.app.route("/modules/module/<module>")
def indvidual_module(module, dir=""):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    fullpath = module
    if dir:
        fullpath += f"/{dir}"

    return pages.render_jinja_template(
        "modules/module.j2.html",
        module=ActiveModules[module],
        name=module,
        path=dir,
        fullpath=fullpath,
        module_actions=module_actions,
        **module_page_context,
    )


@quart_app.app.route("/modules/module/<module>/resource/<resource>")
def resource_page(module, resource):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    kwargs = request.args
    return resourceEditPage(module, resource, "__default__", kwargs)


@quart_app.app.route("/modules/module/<module>/uploadresource")
async def uploadresourcedialog(module):
    path = request.args.get("path", "")
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    d = dialogs.SimpleDialog(f"Upload resource in {module}")
    d.file_input("file")
    d.text_input("filename")
    d.submit_button("Submit")
    return d.render(f"/modules/module/{url(module)}/uploadresourcetarget", hidden_inputs={"path": path})


@quart_app.app.route("/modules/module/<module>/addresource")
def addresource(module):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    path = request.args.get("path", "")
    # path[1] tells what type of resource is being created and addResourceDispatcher returns the appropriate crud screen
    return addResourceDispatcher(module, module, path)


@quart_app.app.route("/modules/module/<module>/addresourcetarget/<rtype>", methods=["POST"])
async def addresourcetarget(module, rtype):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    kwargs = dict(await request.form)
    kwargs.update(request.args)

    check_forbidden(kwargs["name"])

    def f():
        return addResourceTarget(module, rtype, kwargs["name"], kwargs, kwargs.get("dir", ""))

    return await quart.utils.run_sync(f)()


# This goes to a dispatcher that takes into account the type of resource and updates everything about the resource.
@quart_app.app.route("/modules/module/<module>/updateresource/<obj>", methods=["POST"])
async def resource_update_handler(module, obj):
    kwargs = await request.form
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    def f():
        return resourceUpdateTarget(module, obj, kwargs)

    return await quart.utils.run_sync(f)()


@quart_app.app.route("/deletemodule")
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
    modules.rmModule(kwargs["name"], f"Module Deleted by {pages.getAcessingUser()}")
    messagebus.post_message(
        "/system/notifications",
        f"User {pages.getAcessingUser()} Deleted module {kwargs['name']}",
    )

    return quart.redirect("/modules")
