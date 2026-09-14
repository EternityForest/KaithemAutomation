import json
import os

import quart
import quart.utils
import structlog
import vignette
import werkzeug
from quart import request
from quart.ctx import copy_current_request_context

from .. import modules, modules_state, pages, quart_app, util

syslog = structlog.get_logger("system")


@quart_app.app.route("/modules/scan-file-resources/<path:path>")
async def scanfileresources(path: str):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    # list all modules
    modules = modules_state.ActiveModules.keys()

    ret = []
    for module in modules:
        dir = modules_state.getModuleDir(module)
        if os.path.isdir(os.path.join(dir, "__filedata__", path)):
            for root, dirs, files in os.walk(
                os.path.join(dir, "__filedata__", path)
            ):
                for f in files:
                    ret.append(
                        {
                            "module": module,
                            "path": os.path.join(root, f),
                            "size": os.path.getsize(os.path.join(root, f)),
                        }
                    )
                for d in dirs:
                    ret.append(
                        {
                            "module": module,
                            "path": os.path.join(root, d),
                            "size": 0,
                            "is_dir": True,
                        }
                    )
    return json.dumps(ret)


@quart_app.app.route("/modules/module/<module>/list-file-resources/<path:path>")
async def listfileresourcesfolder(
    module: str, path: str
) -> werkzeug.wrappers.response.Response | list[dict[str, int | str | bool]]:
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    d = modules.getModuleDir(module)
    abs_dir = os.path.join(d, "__filedata__", path)
    if not os.path.isdir(abs_dir):
        raise FileNotFoundError(f"Directory not found: {abs_dir}")

    files: list[str] = []

    recursive = request.args.get("recursive", "false")
    if recursive == "true":
        for root, dirs, files in os.walk(abs_dir):
            for i in files:
                files.append(os.path.join(root, i))
    else:
        files = os.listdir(abs_dir)

    ret = []

    for i in files:
        abs = os.path.join(d, "__filedata__", path, i)
        if os.path.isdir(abs):
            i = i + "/"
        ret.append(
            {
                "name": i,
                "size": os.path.getsize(abs),
                "is_dir": os.path.isdir(abs),
            }
        )

    return json.dumps(ret)


@quart_app.app.route("/modules/module/<module>/getfileresource/<path:resource>")
async def getfileresource(module: str, resource: str):
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


icon_types = {
    "png",
    "jpg",
    "jpeg",
    "avif",
    "webp",
    "svg",
    "gif",
    "heic",
    "heif",
    "tiff",
    "bmp",
    "ico",
}


@quart_app.app.route(
    "/modules/module/<module>/getfileresourcethumb/<path:resource>"
)
async def getfileresourcethumb(module: str, resource: str):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    d = modules.getModuleDir(module)
    f = os.path.join(d, "__filedata__", resource)

    if f.split(".")[-1] in icon_types:
        if os.path.isfile(f):
            if os.path.getsize(f) < 1024 * 32:
                return await quart.send_file(f)

    try:
        t = vignette.get_thumbnail(f)
    except Exception:
        t = None

    if t and os.path.isfile(t):
        return await quart.send_file(t)
    else:
        return quart.Response(
            '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0"/>',
            mimetype="image/svg+xml",
        )


@quart_app.app.route("/modules/module/<module>/addfileresource")
async def addfileresource(module: str):
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    if "module_lock" in modules_state.get_module_metadata(module):
        raise PermissionError("Module is locked")
    path = request.args.get("dir", "")

    # path[1] tells what type of resource is being created and addResource
    # Dispatcher returns the appropriate crud screen
    return pages.get_template("modules/uploadfileresource.html").render(
        module=module, path=path
    )


@quart_app.app.route(
    "/modules/module/<module>/uploadfileresourcetarget", methods=["POST"]
)
async def uploadfileresourcetarget(module: str):
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
        if "module_lock" in modules_state.get_module_metadata(module):
            raise PermissionError("Module is locked")

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
            return quart.redirect(
                f"/modules/module/{util.url(module)}/resource/{util.url(path)}"
            )
        else:
            return quart.redirect(f"/modules/module/{util.url(module)}")

    return await f()
