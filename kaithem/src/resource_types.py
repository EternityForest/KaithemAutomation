import weakref
from urllib.parse import quote

import beartype
import yaml
from jsonschema import validate

# Approximately type JSON, could be better
ResourceDictType = dict[str, str | list | int | float | bool | None | dict[str, dict | list | int | float | str | bool | None]]


class ResourceType:
    """Allows creating new resource types.
    Data keys starting with resource- are reserved.

    Types with lower priority will load first.
    """

    def __init__(self, type: str, mdi_icon="", schema=None, priority=50.0):
        """ "Schema may be a JSON schema, representing a dict,
        which must validate the resource, but should not include any
        key beginning with resource- as those are internal and reserved.

        mdi must be an icon name from:
        https://pictogrammers.com/library/mdi/

        Lower priorities load resources first at startup.
        """
        self.type = type
        self.mdi_icon = mdi_icon
        self.createButton = None
        self.schema: dict | None = schema
        self.priority = priority

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
        return {f"{name}.yaml": yaml.dump(resource)}

    def _validate(self, d: ResourceDictType):
        "Strip the resource- keys before giving it to the validator"
        d = {i: d[i] for i in d if not i.startswith("resource-")}
        self.validate(d)

    @beartype.beartype
    def validate(self, d: ResourceDictType):
        """Raise an error if the provided data is bad.
        By default uses the type's schema if one was provided, or else does
        nothing.

        Will not be passed any internal resource-* keys,
        just the resource specific stuff.
        """
        d = {i: d[i] for i in d if not i.startswith("resource-")}

        if self.schema:
            validate(d, self.schema)

    def get_create_target(self, module, folder):
        return f"/modules/module/{module}/addresourcetarget/{self.type}/{quote(folder,safe='')}"

    def get_update_target(self, module, resource):
        return f"/modules/module/{quote(module)}/updateresource/{quote(resource,safe='')}"

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

        <form method=POST action="/modules/module/{module}/addresourcetarget/example/{path}">
        <input name="name">
        <input type="submit">
        </form>
        """

    def oncreaterequest(self, module, name, kwargs) -> ResourceDictType:
        """Must return a resource object given kwargs from createpage.
        Called on submitting create form
        """
        return {"resource-type": "example"}

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

    def ondelete(self, module, resource, obj):
        return True

    def onupdate(self, module, resource, obj):
        """Called when something has updated the data.  Usually the web UI but could be anything."""


additionalTypes: weakref.WeakValueDictionary[str, ResourceType] = weakref.WeakValueDictionary()
