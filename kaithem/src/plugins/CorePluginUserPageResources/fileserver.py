# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from urllib.parse import quote

# This file handles the display of user-created pages
import beartype
import structlog

from kaithem.api.web.dialogs import SimpleDialog
from kaithem.src import auth, modules_state
from kaithem.src.util import url

logger = structlog.get_logger(__name__)


by_module_resource = {}

lookup = None


class ServerObj:
    def __init__(self, m, r, obj):
        self.m = m
        self.r = r
        self.obj = obj

        self.xss = False
        self.methods = ("GET",)
        self.permissions = obj.get("require_permissions", [])
        self.folder = obj["folder"].replace(
            "$MODULE", modules_state.getModuleDir(m)
        )

    def close(self):
        pass


class FileServerType(modules_state.ResourceType):
    @beartype.beartype
    def blurb(self, m, r, value):
        return f'<a href="/pages/{url(m)}/{quote(r)}">Browse</a>'

    def on_load(
        self,
        module: str,
        resourcename: str,
        value: modules_state.ResourceDictType,
    ):
        by_module_resource[module, resourcename] = ServerObj(
            module, resourcename, value
        )
        if lookup:
            lookup.invalidate_cache()

    def on_move(self, module, resource, to_module, to_resource, resourceobj):
        x = by_module_resource.pop((module, resource), None)
        if x:
            by_module_resource[to_module, to_resource] = x

        if lookup:
            lookup.invalidate_cache()

    def on_update(self, module, resource, obj):
        self.on_load(module, resource, obj)

    def on_delete(self, module, name, value):
        by_module_resource[module, name].close()
        del by_module_resource[module, name]
        if lookup:
            lookup.invalidate_cache()

    def on_create_request(self, module, name, kwargs):
        resourceobj = {
            "resource_type": self.type,
            "folder": kwargs["folder"],
        }

        return resourceobj

    def on_update_request(self, module, resource, resourceobj, kwargs):
        resourceobj = {
            "resource_type": self.type,
            "folder": kwargs["folder"],
        }

        resourceobj["require_permissions"] = []
        for i in kwargs:
            # Since HTTP args don't have namespaces we prefix all the permission
            # checkboxes with permission
            if i[:10] == "Permission":
                if kwargs[i] in ("true", "on"):
                    resourceobj["require_permissions"].append(i[10:])

        return resourceobj

    def create_page(self, module, path):
        d = SimpleDialog(f"New File Server in {module}")

        d.text(
            "File servers can be accessed at /pages/modulename/resourcename/file/name."
        )
        d.text("This will map to FOLDER/file/name")
        d.text_input("name")

        d.text("""$MODULE represents the location the resource's module is stored.
                 By default, this is set to $MODULE/__filedata__/public, serving
               files in the public dir within the module.
               """)
        d.text_input("folder", default="$MODULE/__filedata__/public")

        d.submit_button("Create")
        return d.render(
            f"/modules/module/{url(module)}/addresourcetarget/{self.type}",
            hidden_inputs={"path": path},
        )

    def edit_page(self, module, resource, resource_data):
        if "require_permissions" in resource_data:
            requiredpermissions = resource_data["require_permissions"]
        else:
            requiredpermissions = []

        d = SimpleDialog(f"{module}: {resource}")

        d.text_input(
            "folder",
            default=resource_data.get("folder", "$MODULE/__filedata__/public"),
        )

        d.begin_section("Require Permissions")
        for i in sorted(auth.Permissions.keys()):
            d.checkbox(
                f"Permission{i}", title=i, default=i in requiredpermissions
            )
        d.end_section()

        d.submit_button("Create")

        return d.render(self.get_update_target(module, resource))


p = FileServerType("fileserver", mdi_icon="web")
modules_state.additionalTypes["fileserver"] = p
