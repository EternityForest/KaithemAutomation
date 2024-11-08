# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import datetime
import os
from urllib.parse import quote_plus

import quart
import quart.utils

from kaithem.api.modules import (
    admin_url_for_file_resource,
    filename_for_resource,
    scan_file_resources,
)
from kaithem.api.web import (
    add_file_resource_link,
    add_module_plugin_link,
    quart_app,
    require,
)
from kaithem.api.web.dialogs import SimpleDialog

t = os.path.join(os.path.dirname(__file__), "dist")


@quart_app.route("/excalidraw-plugin/dist/<path:path>", methods=["GET", "POST"])
async def excalidraw_dist(path: str = ""):
    require("system_admin")
    path = path
    return await quart.send_file(os.path.join(t, path))


@quart_app.route("/excalidraw-plugin/quick_save", methods=["POST"])
async def excalidraw_quick_save():
    require("system_admin")
    files = await quart.request.files
    kw = quart.request.args

    for i in files:
        fn = filename_for_resource(kw["module"], kw["resource"])

        os.makedirs(os.path.dirname(fn), exist_ok=True)

        with open(fn, "wb") as f:
            f.write(files[i].read())

    scan_file_resources(kw["module"])

    return "OK"


@quart_app.route("/excalidraw-plugin/edit", methods=["GET", "POST"])
async def excalidraw_edit():
    require("system_admin")
    kwargs = dict(await quart.request.form)
    kwargs.update(quart.request.args)

    def f():
        url = admin_url_for_file_resource(
            quart.request.args["module"], quart.request.args["resource"]
        )
        fn = filename_for_resource(
            quart.request.args["module"], quart.request.args["resource"]
        )
        if not os.path.isfile(fn):
            url = ""
        return quart.redirect(
            "/excalidraw-plugin/dist/main.html?resource="
            + quote_plus(quart.request.args["resource"], safe="")
            + "&module="
            + quote_plus(quart.request.args["module"], safe="")
            + "&callback="
            + quote_plus(quart.request.args.get("callback", ""), safe="")
            + "&load_file="
            + quote_plus(url, safe="")
            + "&ratio_guide="
            + quote_plus(quart.request.args.get("ratio_guide", ""), safe="")
        )

    return await quart.utils.run_sync(f)()


@quart_app.route("/excalidraw-plugin/module_plugin", methods=["GET", "POST"])
def excalidraw_plugin_link():
    require("system_admin")
    d = SimpleDialog("New Drawing", method="GET")
    dir = quart.request.args["dir"]
    if dir:
        dir = dir + "/"

    d.text(
        "Name must end with .excalidraw.png, and if the resource already exists, it will be overwritten"
    )
    d.text_input(
        "resource",
        default=dir
        + f"new_drawing_{datetime.datetime.now().isoformat()}.excalidraw.png",
    )
    d.text_input("module", default=quart.request.args["module"])
    d.submit_button("Create")
    return d.render("/excalidraw-plugin/edit")


add_module_plugin_link(
    '<span class="mdi mdi-fountain-pen-tip"></span>Excalidraw',
    "/excalidraw-plugin/module_plugin",
)


def filter_excalidraw_resources(
    module: str, resource: str
) -> tuple[str, str] | None:
    if resource.endswith(".excalidraw.png"):
        s = (
            f"/excalidraw-plugin/dist/main.html?module={quote_plus(module, safe='')}"
            + f"&resource={quote_plus(resource, safe='')}"
            + f"&load_file={quote_plus(admin_url_for_file_resource(module, resource), safe='')}"
        )

        return (
            '<span class="mdi mdi-fountain-pen-tip"></span>Edit Excalidraw',
            s,
        )


add_file_resource_link(filter_excalidraw_resources)
