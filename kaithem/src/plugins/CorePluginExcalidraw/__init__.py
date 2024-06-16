# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import os
from urllib.parse import quote_plus

import quart

from kaithem.api.modules import filename_for_resource
from kaithem.api.web import add_file_resource_link, add_module_plugin_link, quart_app, require
from kaithem.api.web.dialogs import SimpleDialog

t = os.path.join(os.path.dirname(__file__), "dist")


@quart_app.route("/plugin-excalidraw/dist/<path:path>", methods=["GET", "POST"])
async def excalidraw_dist(path: str = ""):
    require("system_admin")
    path = path
    return await quart.send_file(os.path.join(t, path))


@quart_app.route("/plugin-excalidraw/quick_save", methods=["POST"])
async def excalidraw_quick_save():
    require("system_admin")
    files = await quart.request.files
    kw = quart.request.args

    for i in files:
        fn = filename_for_resource(kw["module"], kw["resource"])

        os.makedirs(os.path.dirname(fn), exist_ok=True)

        with open(fn, "wb") as f:
            f.write(files[i].read())

    return "OK"


@quart_app.route("/plugin-excalidraw/module_plugin", methods=["GET", "POST"])
def excalidraw_plugin_link():
    require("system_admin")
    d = SimpleDialog("New Drawing", method="GET")
    dir = quart.request.args["dir"]
    if dir:
        dir = dir + "/"

    d.text_input("resource", default=dir + "new-drawing.excalidraw.png")
    d.text_input("module", default=quart.request.args["module"])
    d.submit_button("Create")
    return d.render("/plugin-excalidraw/dist/main.html")


add_module_plugin_link('<span class="mdi mdi-fountain-pen-tip"></span>Excalidraw', "/plugin-excalidraw/module_plugin")


def filter_excalidraw_resources(module: str, resource: str) -> tuple[str, str] | None:
    if resource.endswith(".excalidraw.png"):
        s = (
            f"/plugin-excalidraw/dist/main.html?module={quote_plus(module, safe='')}"
            + f"&resource={quote_plus(resource, safe='')}"
            + f"&load_file={quote_plus(filename_for_resource(module, resource), safe='')}"
        )

        return ('<span class="mdi mdi-fountain-pen-tip"></span>Edit Excalidraw', s)


add_file_resource_link(filter_excalidraw_resources)
