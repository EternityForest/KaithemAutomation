# Resource Types

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Resource Types

> Auto-generated documentation for [resource_types](../../../api/resource_types.py) module.

#### Attributes

- `ResourceDictType` - Approximately type JSON, could be better: Mapping[str, Any]


- [Resource Types](#resource-types)
  - [ResourceType](#resourcetype)
    - [ResourceType()._validate](#resourcetype()_validate)
    - [ResourceType().blurb](#resourcetype()blurb)
    - [ResourceType().create_page](#resourcetype()create_page)
    - [ResourceType().edit_page](#resourcetype()edit_page)
    - [ResourceType().flush_unsaved](#resourcetype()flush_unsaved)
    - [ResourceType().get_create_target](#resourcetype()get_create_target)
    - [ResourceType().get_update_target](#resourcetype()get_update_target)
    - [ResourceType().on_create_request](#resourcetype()on_create_request)
    - [ResourceType().on_delete](#resourcetype()on_delete)
    - [ResourceType().on_delete_module](#resourcetype()on_delete_module)
    - [ResourceType().on_finished_loading](#resourcetype()on_finished_loading)
    - [ResourceType().on_load](#resourcetype()on_load)
    - [ResourceType().on_move](#resourcetype()on_move)
    - [ResourceType().on_unload](#resourcetype()on_unload)
    - [ResourceType().on_update](#resourcetype()on_update)
    - [ResourceType().on_update_request](#resourcetype()on_update_request)
    - [ResourceType().save_resource](#resourcetype()save_resource)
    - [ResourceType().scan_dir](#resourcetype()scan_dir)
    - [ResourceType().set_edit_page_redirect](#resourcetype()set_edit_page_redirect)
    - [ResourceType().to_files](#resourcetype()to_files)
    - [ResourceType().validate](#resourcetype()validate)
  - [ResourceTypeRuntimeObject](#resourcetyperuntimeobject)
    - [ResourceTypeRuntimeObject().close](#resourcetyperuntimeobject()close)
  - [mutable_copy_resource](#mutable_copy_resource)
  - [register_resource_type](#register_resource_type)
  - [resource_type_from_schema](#resource_type_from_schema)

## ResourceType

[Show source in resource_types.py:37](../../../api/resource_types.py#L37)

Allows creating new resource types.
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

#### Signature

```python
class ResourceType:
    def __init__(
        self,
        type: str,
        mdi_icon: str = "",
        schema: dict[str, Any] | None = None,
        priority: int | float = 50.0,
        title: str = "",
    ): ...
```

### ResourceType()._validate

[Show source in resource_types.py:124](../../../api/resource_types.py#L124)

Strip the resource_ keys before giving it to the validator

#### Signature

```python
def _validate(self, data: ResourceDictType): ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().blurb

[Show source in resource_types.py:151](../../../api/resource_types.py#L151)

Empty or a single overview div

#### Signature

```python
def blurb(self, module: str, resource: str, data: ResourceDictType) -> str: ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().create_page

[Show source in resource_types.py:155](../../../api/resource_types.py#L155)

Called when the user clicks the create button.

Must be a page with a form pointing at the create target.
The only required kwarg in the form is "name".

#### Signature

```python
def create_page(self, module: str, path) -> str: ...
```

### ResourceType().edit_page

[Show source in resource_types.py:179](../../../api/resource_types.py#L179)

Given current resource data, return a manager page.
It may submit a form to the URL at get_update_target()

#### Signature

```python
def edit_page(self, module: str, resource: str, data: ResourceDictType) -> str: ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().flush_unsaved

[Show source in resource_types.py:238](../../../api/resource_types.py#L238)

Called when the resource should save any unsaved data it has
back to the resource.  Will and must only ever be called under the modules_lock

#### Signature

```python
def flush_unsaved(self, module, resource): ...
```

### ResourceType().get_create_target

[Show source in resource_types.py:139](../../../api/resource_types.py#L139)

#### Signature

```python
def get_create_target(self, module: str, folder: str) -> str: ...
```

### ResourceType().get_update_target

[Show source in resource_types.py:142](../../../api/resource_types.py#L142)

#### Signature

```python
def get_update_target(self, module: str, resource: str) -> str: ...
```

### ResourceType().on_create_request

[Show source in resource_types.py:170](../../../api/resource_types.py#L170)

Must return a resource object given all the kwargs from the createpage.
Called on submitting create form.  This should not actually do anything
besides create the resource object.

#### Signature

```python
def on_create_request(
    self, module: str, resource: str, kwargs: dict[str, Any]
) -> ResourceDictType: ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().on_delete

[Show source in resource_types.py:225](../../../api/resource_types.py#L225)

Called when a resource is actually being deleted.
Will be called before on_unload

#### Signature

```python
def on_delete(self, module, resource: str, data: ResourceDictType): ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().on_delete_module

[Show source in resource_types.py:210](../../../api/resource_types.py#L210)

Called before the resource deleter callbacks

#### Signature

```python
def on_delete_module(self, module: str): ...
```

### ResourceType().on_finished_loading

[Show source in resource_types.py:202](../../../api/resource_types.py#L202)

Called with module name when every resource has finished loading with onload(),
and before any events or pages are loaded.

Called during init with None when ALL modules are done loading.  During first
init the individual modules don't get their own on_finished_loading calls.

#### Signature

```python
def on_finished_loading(self, module: str | None): ...
```

### ResourceType().on_load

[Show source in resource_types.py:197](../../../api/resource_types.py#L197)

Called when loaded from disk, or otherwise created for the first time.

#### Signature

```python
def on_load(self, module: str, resource: str, data: ResourceDictType): ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().on_move

[Show source in resource_types.py:213](../../../api/resource_types.py#L213)

Called when object has been moved.
All resource_types must be movable.

#### Signature

```python
def on_move(
    self, module: str, resource: str, to_module: str, to_resource: str, data
): ...
```

### ResourceType().on_unload

[Show source in resource_types.py:219](../../../api/resource_types.py#L219)

Called when a resource is unloaded.  It does not necessarliy mean it is being
permanently deleted.

#### Signature

```python
def on_unload(self, module, resource: str, data: ResourceDictType): ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().on_update

[Show source in resource_types.py:232](../../../api/resource_types.py#L232)

Called when something has updated the data on a resource that already exists.
Usually the web UI but could be anything.

#### Signature

```python
def on_update(self, module, resource: str, data: ResourceDictType): ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().on_update_request

[Show source in resource_types.py:187](../../../api/resource_types.py#L187)

Called with the kwargs from editpage.  Gets old resource obj, must return new

#### Signature

```python
def on_update_request(
    self, module: str, resource: str, data: ResourceDictType, kwargs: dict[str, Any]
) -> ResourceDictType: ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().save_resource

[Show source in resource_types.py:242](../../../api/resource_types.py#L242)

Call this if your implementation has it's own editor that can save
data back.

#### Signature

```python
def save_resource(self, module, resource, data): ...
```

### ResourceType().scan_dir

[Show source in resource_types.py:100](../../../api/resource_types.py#L100)

Given a directory path, scan for any resources stored
in some format other than the usual YAML.

Will be called for every dir in module.

Must not have side effects.

#### Signature

```python
def scan_dir(self, dir: str) -> dict[str, ResourceDictType]: ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().set_edit_page_redirect

[Show source in resource_types.py:90](../../../api/resource_types.py#L90)

Call this from an update handler to say that after submitting,
the system should redirect back to the edit page for further edits.

Only applies to the current request.

Call with a URL to redirect to somewhere else specific.

#### Signature

```python
def set_edit_page_redirect(self, url: str = "__repeat__"): ...
```

### ResourceType().to_files

[Show source in resource_types.py:110](../../../api/resource_types.py#L110)

Given a resource, return files as name to content mapping.
Returned filenames must not include the path, within the module,
although the name given will be the full resource name.

If resource is foo/bar/baz, fn should be baz.my_extension.

You can make multiple files but not folders.  On delete this is
also called to find what files need to be deleted.

Must not have side effects.

#### Signature

```python
def to_files(self, name: str, resource: ResourceDictType) -> dict[str, str]: ...
```

#### See also

- [ResourceDictType](#resourcedicttype)

### ResourceType().validate

[Show source in resource_types.py:131](../../../api/resource_types.py#L131)

Raise an error if the provided data is bad.

Will not be passed any internal resource_* keys,
just the resource specific stuff.

#### Signature

```python
@beartype.beartype
def validate(self, data: ResourceDictType): ...
```

#### See also

- [ResourceDictType](#resourcedicttype)



## ResourceTypeRuntimeObject

[Show source in resource_types.py:259](../../../api/resource_types.py#L259)

#### Signature

```python
class ResourceTypeRuntimeObject:
    def __init__(self, module: str, resource: str, data: dict[str, Any]): ...
```

### ResourceTypeRuntimeObject().close

[Show source in resource_types.py:263](../../../api/resource_types.py#L263)

#### Signature

```python
def close(self): ...
```



## mutable_copy_resource

[Show source in resource_types.py:29](../../../api/resource_types.py#L29)

Given an immutable resource, return a mutable copy

#### Signature

```python
def mutable_copy_resource(resource: ResourceDictType) -> dict[str, Any]: ...
```

#### See also

- [ResourceDictType](#resourcedicttype)



## register_resource_type

[Show source in resource_types.py:255](../../../api/resource_types.py#L255)

#### Signature

```python
def register_resource_type(resource_type: ResourceType): ...
```

#### See also

- [ResourceType](#resourcetype)



## resource_type_from_schema

[Show source in resource_types.py:272](../../../api/resource_types.py#L272)

Create a new resource type from a JSON schema, and an object
that represents the runtime state of the resource.

Whatever the schema defines
is passed to the runtime object constructor verbatim.

The class must have a close() method.

blurb(obj, module, resource) will be passed the runtime object
and must return some HTML for the module page.

#### Signature

```python
def resource_type_from_schema(
    resource_type: str,
    title: str,
    icon: str,
    schema: dict[str, Any] | Callable[[], dict[str, Any]],
    runtime_object_cls: Type[ResourceTypeRuntimeObjectTypeVar],
    default: dict[str, Any] = {},
    blurb: Callable[[ResourceTypeRuntimeObjectTypeVar, str, str], str] | str = "",
): ...
```

#### See also

- [ResourceTypeRuntimeObjectTypeVar](#resourcetyperuntimeobjecttypevar)