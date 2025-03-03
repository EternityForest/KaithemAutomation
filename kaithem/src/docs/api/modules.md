# Modules

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Modules

> Auto-generated documentation for [modules](../../../api/modules.py) module.

#### Attributes

- `modules_lock` - Almost every function in this file will raise an
  exception if this lock is not held.: modules_state.modulesLock


- [Modules](#modules)
  - [admin_url_for_file_resource](#admin_url_for_file_resource)
  - [delete_resource](#delete_resource)
  - [filename_for_file_resource](#filename_for_file_resource)
  - [filename_for_resource](#filename_for_resource)
  - [get_resource_data](#get_resource_data)
  - [insert_resource](#insert_resource)
  - [list_resources](#list_resources)
  - [resolve_file_resource](#resolve_file_resource)
  - [save_resource](#save_resource)
  - [scan_file_resources](#scan_file_resources)
  - [set_resource_error](#set_resource_error)
  - [update_resource](#update_resource)

## admin_url_for_file_resource

[Show source in modules.py:40](../../../api/modules.py#L40)

#### Signature

```python
def admin_url_for_file_resource(module: str, resource: str) -> str: ...
```



## delete_resource

[Show source in modules.py:101](../../../api/modules.py#L101)

Delete a resource, triggering any relevant effects for that resource type.
May only be called under the modules_lock.

#### Signature

```python
@modules_lock.required
def delete_resource(module: str, resource: str): ...
```



## filename_for_file_resource

[Show source in modules.py:28](../../../api/modules.py#L28)

Given the module and resource for a file, return the actual file for a file resource, or
file data dir for directory resource

#### Signature

```python
def filename_for_file_resource(module: str, resource: str) -> str: ...
```



## filename_for_resource

[Show source in modules.py:35](../../../api/modules.py#L35)

DEPRECATED: use filename_for_file_resource instead

#### Signature

```python
def filename_for_resource(module: str, resource: str) -> str: ...
```



## get_resource_data

[Show source in modules.py:57](../../../api/modules.py#L57)

Get the dict data for a resource. May only be called under the modules_lock.

#### Signature

```python
@modules_state.modulesLock.required
def get_resource_data(module: str, resource: str) -> dict[str, Any]: ...
```



## insert_resource

[Show source in modules.py:64](../../../api/modules.py#L64)

Create a new resource, if it doesn't already exist,
and initializing it as appropriate for it's resource type
May only be called under the modules_lock.

#### Signature

```python
@modules_lock.required
def insert_resource(module: str, resource: str, resourceData: ResourceDictType): ...
```



## list_resources

[Show source in modules.py:109](../../../api/modules.py#L109)

List the resources in a module.
May only be called under the modules_lock.

#### Signature

```python
@modules_lock.required
def list_resources(module: str) -> list[str]: ...
```



## resolve_file_resource

[Show source in modules.py:116](../../../api/modules.py#L116)

Given a name of a file resource or a folder in the file resources,
return the full path to it, if it can be found in any module.

May only be called under the modules_lock.

#### Signature

```python
@modules_lock.required
def resolve_file_resource(relative_path: str) -> str | None: ...
```



## save_resource

[Show source in modules.py:128](../../../api/modules.py#L128)

Save a resource without triggering any other events.
Use this in your flush_unsaved handler. May only be called under the modules_lock.

#### Signature

```python
@modules_lock.required
def save_resource(module: str, resource: str, resourceData: ResourceDictType): ...
```



## scan_file_resources

[Show source in modules.py:44](../../../api/modules.py#L44)

Scan the resources in the filedata folder for the specified module.
Call if you directly change something, to update the UI.  May not
take effect immediately

#### Signature

```python
def scan_file_resources(module: str): ...
```



## set_resource_error

[Show source in modules.py:20](../../../api/modules.py#L20)

Set an error notice for a resource.  Cleared when the resource is moved, updated or deleted,
or by setting the error to None.

#### Signature

```python
def set_resource_error(module: str, resource: str, error: str | None): ...
```



## update_resource

[Show source in modules.py:81](../../../api/modules.py#L81)

Update an existing resource, triggering any relevant effects for that resource type.
May only be called under the modules_lock.

#### Signature

```python
@modules_lock.required
def update_resource(module: str, resource: str, resourceData: ResourceDictType): ...
```