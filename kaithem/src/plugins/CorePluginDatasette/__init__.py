import os
from typing import Any

from datasette import hookimpl
from datasette.app import Datasette
from datasette.database import Database

from kaithem.api import web as webapi
from kaithem.api.modules import relative_file_resource_dir_for_resource
from kaithem.api.web import dialogs
from kaithem.src.modules_state import ResourceType, additionalTypes
from kaithem.src.resource_types import ResourceDictType, mutable_copy_resource

# Config listed by database name
db_cfg_by_module_resource = {}


class ConfiguredDB:
    def __init__(self, module: str, resource: str, data: ResourceDictType):
        self.db: Database | None = None
        self.id = (module, resource)
        self.read_perms = data["read_perms"]
        self.write_perms = data["write_perms"]
        self.file = data["database_file"]
        self.name = data["database_name"]


@hookimpl
def actor_from_request(datasette, request):
    async def inner():
        try:
            return {"id": webapi.user(request.scope)}
        except Exception:
            return None

    return inner


@hookimpl
async def permission_allowed(datasette, actor, action, resource):
    cfg = db_cfg_by_module_resource[datasette]

    read = {
        "view-database",
        "view-instance",
        "view-table",
        "view-query",
    }
    write = {
        "insert-row",
        "delete-row",
        "update-row",
    }

    if action in read:
        return webapi.has_permission(actor["id"], cfg.read_perms)

    if action in write:
        return webapi.has_permission(actor["id"], cfg.write_perms)
    else:
        return webapi.has_permission(actor["id"], "system.admin")


datasette_instance = Datasette(
    [],
    settings={
        "base_url": "/datasette/",
    },
)

datasette_application = datasette_instance.app()
webapi.add_asgi_app("/datasette", datasette_application)


class DatasetteResourceType(ResourceType):
    def blurb(self, module, resource, data):
        return f"""
        <div class="tool-bar">
            <a href="/datasette/{module}:{resource}">
            <span class="mdi mdi-database"></span>
            Datasette</a>
        </div>
        """

    def on_load(self, module: str, resource: str, data: ResourceDictType):
        if data["database_file"] in db_cfg_by_module_resource:
            raise Exception(f"Database already open: {data['database_file']}")

        for i in db_cfg_by_module_resource:
            if db_cfg_by_module_resource[i].name == data["database_name"]:
                raise Exception(
                    f"Database already open: {data['database_name']}"
                )
            if db_cfg_by_module_resource[i].file == data["database_file"]:
                raise Exception(
                    f"Database already open: {data['database_file']}"
                )

        db_cfg_by_module_resource[data["database_name"]] = ConfiguredDB(
            module, resource, data
        )

        abs_fn = os.path.join(
            relative_file_resource_dir_for_resource(module, resource),
            data["database_file"],
        )
        db = Database(datasette_instance, abs_fn, True)

        db_cfg_by_module_resource[data["database_name"]].db = db

        datasette_instance.add_database(db, data["database_name"])

    def on_delete(self, module, resource: str, data):
        to_rm = None
        for i in db_cfg_by_module_resource:
            if db_cfg_by_module_resource[i].id == (module, resource):
                to_rm = i
                break
        if to_rm:
            del db_cfg_by_module_resource[to_rm]

    def on_update(self, module: str, resource: str, data: ResourceDictType):
        self.on_delete(module, resource, data)
        self.on_load(module, resource, data)

    def on_create_request(self, module, resource, kwargs):
        d = {"resource_type": self.type}
        d.update(kwargs)
        d.pop("name")
        d.pop("Save", None)

        return d

    def on_update_request(
        self, module, resource, data: ResourceDictType, kwargs
    ):
        d: dict[str, Any] = mutable_copy_resource(data)
        d.update(kwargs)
        d.pop("name", None)
        d.pop("Save", None)
        return d

    def create_page(self, module, path):
        d = dialogs.SimpleDialog("New Logger")
        d.text_input("name", title="Logger Name")
        d.text_input(
            "database_name",
            title="Database Name in main Datasette listing",
        )

        d.text_input("database_file", title="Database File")

        d.text_input(
            "read_perms",
            title="Read Permissions",
            default="system.admin",
        )

        d.text_input(
            "write_perms",
            title="Write Permissions",
            default="system.admin",
        )
        d.submit_button("Save")
        return d.render(self.get_create_target(module, path))

    def edit_page(self, module, resource, data):
        d = dialogs.SimpleDialog("Editing Logger")

        d.text_input(
            "database_name",
            title="Database Name in main Datasette listing",
            default=data["database_name"],
        )

        d.text_input(
            "database_file",
            title="Database File",
            default=data["database_file"],
        )

        d.text_input(
            "read_perms",
            title="Read Permissions",
            default=data["read_perms"],
        )

        d.text_input(
            "write_perms",
            title="Write Permissions",
            default=data["write_perms"],
        )

        d.submit_button("Save")
        return d.render(self.get_update_target(module, resource))


drt = DatasetteResourceType("datasette", mdi_icon="database")
additionalTypes["datasette"] = drt
