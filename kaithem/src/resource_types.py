# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import html
import traceback
import weakref
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import beartype
import yaml
from jsonschema import validate

# Approximately type JSON, could be better
ResourceDictType = Mapping[str, Any]


class ResourceType:
    """Allows creating new resource types.
    Data keys starting with resource_ are reserved.

    ALL top level keys must be snake_case.
    In fact, when loading modules,
    things will be automatically converted,
    for legacy reason.

    Types with lower priority will load first
    .
    """

    def __init__(
        self, type: str, mdi_icon="", schema=None, priority=50.0, title=""
    ):
        """ "Schema may be a JSON schema, representing a dict,
        which must validate the resource, but should not include any
        key beginning with resource_ as those are internal and reserved.

        mdi must be an icon name from:
        https://pictogrammers.com/library/mdi/

        Lower priorities load resources first at startup.
        """
        self.type = type
        self.mdi_icon = mdi_icon
        self.createButton = None
        self.schema: dict | None = schema
        self.priority = priority
        self.title = title or type.capitalize()

    def scan_dir(self, dir: str) -> dict[str, ResourceDictType]:
        """Given a directory path, scan for any resources stored
        in some format other than the usual YAML.

        Will be called for every dir in module.

        Must not have side effects.
        """
        return {}

    def to_files(self, name: str, resource: ResourceDictType) -> dict[str, str]:
        """Given a resource, return files as name to content mapping.
        Returned filenames must not include the path, within the module,
        although the name given will be the full resource name.

        If resource is foo/bar/baz, fn should be baz.my_extension.

        You can make multiple files but not folders.  On delete this is
        also called to find what files need to be deleted.

        Must not have side effects.
        """
        return {f"{name.split('/')[-1]}.yaml": yaml.dump(resource)}

    def _validate(self, data: ResourceDictType):
        "Strip the resource_ keys before giving it to the validator"
        data = {i: data[i] for i in data if not i.startswith("resource_")}
        if self.schema:
            validate(data, self.schema)
        self.validate(data)

    @beartype.beartype
    def validate(self, data: ResourceDictType):
        """Raise an error if the provided data is bad.

        Will not be passed any internal resource_* keys,
        just the resource specific stuff.
        """

    def get_create_target(self, module: str, folder):
        return f"/modules/module/{module}/addresourcetarget/{self.type}?dir={quote(folder,safe='')}"

    def get_update_target(self, module: str, resource):
        return f"/modules/module/{quote(module)}/updateresource/{resource}"

    def _blurb(self, module: str, resource: str, data):
        try:
            return self.blurb(module, resource, data)
        except Exception:
            return f'<div class="scroll max-h-12rem">{html.escape(traceback.format_exc())}</div>'

    def blurb(self, module: str, resource: str, data) -> str:
        """Empty or a single overview div"""
        return ""

    def create_page(self, module: str, path):
        """
        Called when the user clicks the create button.

        Must be a page with a form pointing at the create target.
        The only required kwarg in the form is "name".
        """
        return f"""

        <form method=POST action="/modules/module/{module}/addresourcetarget/example?dir={quote(path, safe='')}">
        <input name="name">
        <input type="submit">
        </form>
        """

    def on_create_request(
        self, module: str, resource: str, kwargs
    ) -> ResourceDictType:
        """Must return a resource object given kwargs from createpage.
        Called on submitting create form
        """
        return {"resource_type": "example"}

    def edit_page(self, module: str, resource: str, data):
        """Given current resource data, return a manager page.
        It may submit to get_update_target()
        """
        return str(data)

    def on_update_request(
        self, module: str, resource: str, data: ResourceDictType, kwargs
    ):
        "Called with the kwargs from editpage.  Gets old resource obj, must return new"
        return data

    def on_load(self, module: str, resource: str, data: ResourceDictType):
        """Called when loaded from disk."""

    def on_finished_loading(self, module: str | None):
        """Called with module name when every resource has finished loading with onload(),
        and before any events or pages are loaded.

        Called during init with None when ALL modules are done loading.
        """

    def on_delete_module(self, module: str):
        """Called before the resource deleter callbacks"""

    def on_move(
        self, module: str, resource: str, to_module: str, to_resource: str, data
    ):
        """Called when object has been moved.  All additionaltypes must be movable."""

    def on_delete(self, module, resource: str, data):
        pass

    def on_update(self, module, resource: str, data):
        """Called when something has updated the data.  Usually the web UI but could be anything."""

    def flush_unsaved(self, module, resource):
        """Called when the resource should save any unsaved data it has back to the resource."""


additionalTypes: weakref.WeakValueDictionary[str, ResourceType] = (
    weakref.WeakValueDictionary()
)
