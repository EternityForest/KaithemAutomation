import json

import quart
import quart.utils
from quart import request

from kaithem.src import modules_state, pages, quart_app, util


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


@quart_app.app.route(
    "/modules/module/<module>/obj/<path:path>", methods=["POST"]
)
async def obj_inspect(module, path=""):
    kwargs = await request.form
    path = path.split("/")
    # There might be a password or something important in the actual module object. Best to restrict who can access it.
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    def f():
        if not len(path) > 0:
            raise ValueError("No object specified")

        obj = objname = None

        if path[0] == "module":
            obj = modules_state.scopes[module]
            objname = f"Module Obj: {module}"

        if path[0] == "event":
            assert len(path) == 2
            from .plugins import CorePluginEventResources

            obj = CorePluginEventResources._events_by_module_resource[
                module, path[1]
            ].pymodule
            objname = f"Event: {path[1]}"

        # Inspector should prob be its own module since it does all this.
        if path[0] == "sys":
            import kaithem

            obj = kaithem
            objname = "PythonRoot"

        if path[0] == "sysmodule":
            import sys

            obj = sys
            objname = "sys"

        if "objname" in kwargs:
            objname = kwargs["objname"]

        if "objpath" not in kwargs:
            assert objname
            return pages.get_template("modules/modulescope.html").render(
                kwargs=kwargs, name=module, obj=obj, objname=objname
            )
        else:
            assert objname
            return pages.get_template("obj_insp.html").render(
                objpath=kwargs["objpath"],
                objname=objname,
                obj=followAttributes(obj, kwargs["objpath"]),
                getGC=kwargs.get("gcinfo", False),
            )

    return await quart.utils.run_sync(f)()
