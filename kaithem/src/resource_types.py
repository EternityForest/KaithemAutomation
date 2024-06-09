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

    def __init__(self, type: str, mdi_icon="", schema=None, priority=50.0, title=""):
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

    def _validate(self, d: ResourceDictType):
        "Strip the resource_ keys before giving it to the validator"
        d = {i: d[i] for i in d if not i.startswith("resource_")}
        if self.schema:
            validate(d, self.schema)
        self.validate(d)

    @beartype.beartype
    def validate(self, d: ResourceDictType):
        """Raise an error if the provided data is bad.

        Will not be passed any internal resource_* keys,
        just the resource specific stuff.
        """

    def get_create_target(self, module, folder):
        return f"/modules/module/{module}/addresourcetarget/{self.type}?dir={quote(folder,safe='')}"

    def get_update_target(self, module, resource):
        return f"/modules/module/{quote(module)}/updateresource/{resource}"

    def _blurb(self, module, resource, object):
        try:
            return self.blurb(module, resource, object)
        except Exception:
            return f'<div class="scroll max-h-12rem">{html.escape(traceback.format_exc())}</div>'

    def blurb(self, module, resource, object):
        """Empty or a single overview div"""
        return ""

    def createpage(self, module, path):
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

    def oncreaterequest(self, module, name, kwargs) -> ResourceDictType:
        """Must return a resource object given kwargs from createpage.
        Called on submitting create form
        """
        return {"resource_type": "example"}

    def editpage(self, module, resource, resourceobj):
        """Given current resource data, return a manager page.
        It may submit to get_update_target()
        """
        return str(resourceobj)

    def onupdaterequest(self, module, resource, resourceobj, kwargs):
        "Called with the kwargs from editpage.  Gets old resource obj, must return new"
        return resourceobj

    def onload(self, module: str, resource: str, resourceobj: ResourceDictType):
        """Called when loaded from disk."""
        return True

    def onfinishedloading(self, module: str | None):
        """Called with module name when every resource has finished loading with onload(),
        and before any events or pages are loaded.

        Called during init with None when ALL modules are done loading.
        """

    def ondeletemodule(self, module: str):
        """Called before the resource deleter callbacks"""

    def onmove(self, module, resource, toModule, toResource, resourceobj):
        """Called when object has been moved.  All additionaltypes must be movable."""
        return True

    def ondelete(self, module, resource, resourceobj):
        return True

    def onupdate(self, module, resource, resourceobj):
        """Called when something has updated the data.  Usually the web UI but could be anything."""

    def flush_unsaved(self, module, resource):
        """Called when the resource should save any unsaved data it has back to the resource."""


additionalTypes: weakref.WeakValueDictionary[str, ResourceType] = weakref.WeakValueDictionary()
