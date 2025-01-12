# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later

import copy
import html
import threading
import traceback
from collections.abc import Callable, Mapping
from typing import Any, Final
from urllib.parse import quote

import beartype
import structlog
import yaml
from jsonschema import validate

logger = structlog.get_logger(__name__)

# Approximately type JSON, could be better
ResourceDictType = Mapping[str, Any]

_edit_page_redirect = threading.local()


def mutable_copy_resource(resource: ResourceDictType) -> dict[str, Any]:
    """Given an immutable resource, return a mutable copy"""
    return copy.deepcopy(resource)  # type: ignore


_save_callback: Callable[[str, str, ResourceDictType], None] | None = None


class ResourceType:
    """Allows creating new resource types.
    Data keys starting with resource_ are reserved.

    ALL top level keys must be snake_case.
    In fact, when loading modules,
    things will be automatically converted,
    for legacy reason.

    Types with lower priority will load first

    Schema is a JSON schema, representing a dict,
    and is optional.

    mdi must be an icon name from:
    https://pictogrammers.com/library/mdi/

    Create an instance of this or a subclass,
    then add it to resource_types.

    Once created, deleting them is not supported.
    """

    def __init__(
        self,
        type: str,
        mdi_icon: str = "",
        schema: dict[str, Any] | None = None,
        priority: int | float = 50.0,
        title: str = "",
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

    def __del__(self):
        if logger:
            logger.error(
                f"Deleting resource type {self.type}. Deleting resource types not supported."
            )

    def set_edit_page_redirect(self, url: str = "__repeat__"):
        """Call this from an update handler to say that after submitting,
        the system should redirect back to the edit page for further edits.

        Only applies to the current request.

        Call with a URL to redirect to somewhere else specific.
        """
        _edit_page_redirect.value = url

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

    def get_create_target(self, module: str, folder: str) -> str:
        return f"/modules/module/{module}/addresourcetarget/{self.type}?dir={quote(folder,safe='')}"

    def get_update_target(self, module: str, resource: str) -> str:
        return f"/modules/module/{quote(module)}/updateresource/{resource}"

    def _blurb(self, module: str, resource: str, data: ResourceDictType) -> str:
        try:
            return self.blurb(module, resource, data)
        except Exception:
            return f'<div class="scroll max-h-12rem">{html.escape(traceback.format_exc())}</div>'

    def blurb(self, module: str, resource: str, data: ResourceDictType) -> str:
        """Empty or a single overview div"""
        return ""

    def create_page(self, module: str, path) -> str:
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
        self, module: str, resource: str, kwargs: dict[str, Any]
    ) -> ResourceDictType:  # pragma: no cover
        """Must return a resource object given all the kwargs from the createpage.
        Called on submitting create form.  This should not actually do anything
        besides create the resource object.
        """
        return {"resource_type": "example"}

    def edit_page(
        self, module: str, resource: str, data: ResourceDictType
    ) -> str:  # pragma: no cover
        """Given current resource data, return a manager page.
        It may submit a form to the URL at get_update_target()
        """
        return str(data)

    def on_update_request(
        self,
        module: str,
        resource: str,
        data: ResourceDictType,
        kwargs: dict[str, Any],
    ) -> ResourceDictType:  # pragma: no cover
        "Called with the kwargs from editpage.  Gets old resource obj, must return new"
        return data

    def on_load(
        self, module: str, resource: str, data: ResourceDictType
    ):  # pragma: no cover
        """Called when loaded from disk, or otherwise created for the first time."""

    def on_finished_loading(self, module: str | None):  # pragma: no cover
        """Called with module name when every resource has finished loading with onload(),
        and before any events or pages are loaded.

        Called during init with None when ALL modules are done loading.  During first
        init the individual modules don't get their own on_finished_loading calls.
        """

    def on_delete_module(self, module: str):  # pragma: no cover
        """Called before the resource deleter callbacks"""

    def on_move(
        self, module: str, resource: str, to_module: str, to_resource: str, data
    ):  # pragma: no cover
        """Called when object has been moved.
        All resource_types must be movable."""

    def on_unload(
        self, module, resource: str, data: ResourceDictType
    ):  # pragma: no cover
        """Called when a resource is unloaded.  It does not necessarliy mean it is being
        permanently deleted."""

    def on_delete(
        self, module, resource: str, data: ResourceDictType
    ):  # pragma: no cover
        """Called when a resource is actually being deleted.
        Will be called before on_unload
        """

    def on_update(
        self, module, resource: str, data: ResourceDictType
    ):  # pragma: no cover
        """Called when something has updated the data on a resource that already exists.
        Usually the web UI but could be anything."""

    def flush_unsaved(self, module, resource):  # pragma: no cover
        """Called when the resource should save any unsaved data it has
        back to the resource.  Will and must only ever be called under the modules_lock"""

    def save_resource(self, module, resource, data):
        """Call this if your implementation has it's own editor that can save
        data back.
        """
        if not _save_callback:
            # Should not be possible to trigger this.
            raise RuntimeError("Save callback not set up")  # pragma: no cover
        _save_callback(module, resource, data)


resource_types: Final[dict[str, ResourceType]] = {}


def register_resource_type(resource_type: ResourceType):
    resource_types[resource_type.type] = resource_type
