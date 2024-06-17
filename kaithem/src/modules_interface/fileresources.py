import os

import quart
import quart.utils
import structlog
import vignette
from quart import request
from quart.ctx import copy_current_request_context

from .. import modules, pages, quart_app, util

syslog = structlog.get_logger("system")


@quart_app.app.route("/modules/module/<module>/getfileresource/<path:resource>")
async def getfileresource(module, resource):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    d = modules.getModuleDir(module)
    f = os.path.join(d, "__filedata__", resource)

    if os.path.isfile(f):
        return await quart.send_file(f)
    else:
        raise FileNotFoundError(f"File not found: {f}")


@quart_app.app.route("/modules/module/<module>/getfileresourcethumb/<path:resource>")
async def getfileresourcethumb(module, resource):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    d = modules.getModuleDir(module)
    f = os.path.join(d, "__filedata__", resource)
    t = vignette.get_thumbnail(f)

    if t and os.path.isfile(t):
        return await quart.send_file(t)
    else:
        return quart.Response('<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0"/>', mimetype="image/svg+xml")


@quart_app.app.route("/modules/module/<module>/addfileresource")
async def addfileresource(module):
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
        if path:
            dataname = f"{path}/{dataname}"

        dataname = os.path.join(folder, dataname)
        if os.path.exists(dataname):
            if "overwrite" not in kwargs:
                raise FileExistsError(f"File already exists: {dataname}")

        inputfile = file

        os.makedirs(os.path.dirname(dataname), exist_ok=True)

        syslog.info(f"User uploaded file resource to {dataname}")

        with open(dataname, "wb") as f:
            while True:
                d = inputfile.read(8192)
                if not d:
                    break
                f.write(d)

        if path:
            return quart.redirect(f"/modules/module/{util.url(module)}/resource/{util.url(path)}")
        else:
            return quart.redirect(f"/modules/module/{util.url(module)}")

    return await f()
