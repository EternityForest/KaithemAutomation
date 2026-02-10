# kaithem.api.resource_types

## Attributes

| [`logger`](#kaithem.api.resource_types.logger)                                                     |    |
|----------------------------------------------------------------------------------------------------|----|
| [`ResourceDictType`](#kaithem.api.resource_types.ResourceDictType)                                 |    |
| [`resource_types`](#kaithem.api.resource_types.resource_types)                                     |    |
| [`ResourceTypeRuntimeObjectTypeVar`](#kaithem.api.resource_types.ResourceTypeRuntimeObjectTypeVar) |    |

## Classes

| [`ResourceType`](#kaithem.api.resource_types.ResourceType)                           | Allows creating new resource types.   |
|--------------------------------------------------------------------------------------|---------------------------------------|
| [`ResourceTypeRuntimeObject`](#kaithem.api.resource_types.ResourceTypeRuntimeObject) |                                       |

## Functions

| [`mutable_copy_resource`](#kaithem.api.resource_types.mutable_copy_resource)(→ dict[str, Any])                        | Given an immutable resource, return a mutable copy           |
|-----------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------|
| [`register_resource_type`](#kaithem.api.resource_types.register_resource_type)(resource_type)                         |                                                              |
| [`resource_type_from_schema`](#kaithem.api.resource_types.resource_type_from_schema)(resource_type, title, icon, ...) | Create a new resource type from a JSON schema, and an object |

## Module Contents

### kaithem.api.resource_types.logger

### kaithem.api.resource_types.ResourceDictType

### kaithem.api.resource_types.mutable_copy_resource(resource: ResourceDictType) → dict[str, Any]

Given an immutable resource, return a mutable copy

### *class* kaithem.api.resource_types.ResourceType(type: str, mdi_icon: str = '', schema: dict[str, Any] | None = None, priority: int | float = 50.0, title: str = '')

Allows creating new resource types.
Data keys starting with “resource” are reserved.

ALL top level keys must be snake_case.
In fact, when loading modules,
things will be automatically converted,
for legacy reason.

Types with lower priority will load first

Schema is a JSON schema, representing a dict,
and is optional.

mdi must be an icon name from:
[https://pictogrammers.com/library/mdi/](https://pictogrammers.com/library/mdi/)

Create an instance of this or a subclass,
then add it to resource_types.

Once created, deleting them is not supported.

#### type

#### mdi_icon *= ''*

#### createButton *= None*

#### schema *: dict | None* *= None*

#### priority *= 50.0*

#### title

#### \_\_del_\_()

#### set_edit_page_redirect(url: str = '_\_repeat_\_')

Call this from an update handler to say that after submitting,
the system should redirect back to the edit page for further edits.

Only applies to the current request.

Call with a URL to redirect to somewhere else specific.

#### scan_dir(dir: str) → dict[str, ResourceDictType]

Given a directory path, scan for any resources stored
in some format other than the usual YAML.

Will be called for every dir in module.

Must not have side effects.

#### to_files(name: str, resource: ResourceDictType) → dict[str, str]

Given a resource, return files as name to content mapping.
Returned filenames must not include the path, within the module,
although the name given will be the full resource name.

If resource is foo/bar/baz, fn should be baz.my_extension.

You can make multiple files but not folders.  On delete this is
also called to find what files need to be deleted.

Must not have side effects.

#### validate(data: ResourceDictType)

Raise an error if the provided data is bad.

Will not be passed any internal resource_\* keys,
just the resource specific stuff.

#### get_create_target(module: str, folder: str) → str

#### get_update_target(module: str, resource: str) → str

#### blurb(module: str, resource: str, data: ResourceDictType) → str

Empty or a single overview div

#### create_page(module: str, path) → str

Called when the user clicks the create button.

Must be a page with a form pointing at the create target.
The only required kwarg in the form is “name”.

#### on_create_request(module: str, resource: str, kwargs: dict[str, Any]) → ResourceDictType

Must return a resource object given all the kwargs from the createpage.
Called on submitting create form.  This should not actually do anything
besides create the resource object.

#### edit_page(module: str, resource: str, data: ResourceDictType) → str

Given current resource data, return a manager page.
It may submit a form to the URL at get_update_target()

#### on_update_request(module: str, resource: str, data: ResourceDictType, kwargs: dict[str, Any]) → ResourceDictType

Called with the kwargs from editpage.  Gets old resource obj, must return new

#### on_load(module: str, resource: str, data: ResourceDictType)

Called when loaded from disk, or otherwise created for the first time.

#### on_finished_loading(module: str | None)

Called with module name when every resource has finished loading with onload(),
and before any events or pages are loaded.

Called during init with None when ALL modules are done loading.  During first
init the individual modules don’t get their own on_finished_loading calls.

#### on_delete_module(module: str)

Called before the resource deleter callbacks

#### on_move(module: str, resource: str, to_module: str, to_resource: str, data)

Called when object has been moved.
All resource_types must be movable.

#### on_unload(module, resource: str, data: ResourceDictType)

Called when a resource is unloaded.  It does not necessarliy mean it is being
permanently deleted.

#### on_delete(module, resource: str, data: ResourceDictType)

Called when a resource is actually being deleted.
Will be called before on_unload

#### on_update(module, resource: str, data: ResourceDictType)

Called when something has updated the data on a resource that already exists.
Usually the web UI but could be anything.

#### flush_unsaved(module, resource)

Called when the resource should save any unsaved data it has
back to the resource.  Will and must only ever be called under the modules_lock

#### save_resource(module, resource, data)

Call this if your implementation has it’s own editor that can save
data back.

### kaithem.api.resource_types.resource_types *: Final[dict[str, [ResourceType](#kaithem.api.resource_types.ResourceType)]]*

### kaithem.api.resource_types.register_resource_type(resource_type: [ResourceType](#kaithem.api.resource_types.ResourceType))

### *class* kaithem.api.resource_types.ResourceTypeRuntimeObject(module: str, resource: str, data: dict[str, Any])

#### close()

### kaithem.api.resource_types.ResourceTypeRuntimeObjectTypeVar

### kaithem.api.resource_types.resource_type_from_schema(resource_type: str, title: str, icon: str, schema: dict[str, Any] | collections.abc.Callable[[], dict[str, Any]], runtime_object_cls: type[ResourceTypeRuntimeObjectTypeVar], default: dict[str, Any] = {}, blurb: collections.abc.Callable[[ResourceTypeRuntimeObjectTypeVar, str, str], str] | str = '')

Create a new resource type from a JSON schema, and an object
: that represents the runtime state of the resource.

Whatever the schema defines
is passed to the runtime object constructor verbatim.

The class must have a close() method.

blurb(obj, module, resource) will be passed the runtime object
and must return some HTML for the module page.
