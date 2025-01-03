# Modules

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Modules

> Auto-generated documentation for [modules](../../../api/modules.py) module.

- [Modules](#modules)
  - [admin_url_for_file_resource](#admin_url_for_file_resource)
  - [delete_resource](#delete_resource)
  - [filename_for_file_resource](#filename_for_file_resource)
  - [filename_for_resource](#filename_for_resource)
  - [get_resource_data](#get_resource_data)
  - [insert_resource](#insert_resource)
  - [list_resources](#list_resources)
  - [resolve_file_resource](#resolve_file_resource)
  - [scan_file_resources](#scan_file_resources)
  - [update_resource](#update_resource)

## admin_url_for_file_resource

[Show source in modules.py:19](../../../api/modules.py#L19)

#### Signature

```python
def admin_url_for_file_resource(module: str, resource: str) -> str: ...
```



## delete_resource

[Show source in modules.py:59](../../../api/modules.py#L59)

#### Signature

```python
def delete_resource(module: str, resource: str): ...
```



## filename_for_file_resource

[Show source in modules.py:7](../../../api/modules.py#L7)

Given the module and resource for a file, return the actual file for a file resource, or
file data dir for directory resource

#### Signature

```python
def filename_for_file_resource(module: str, resource: str) -> str: ...
```



## filename_for_resource

[Show source in modules.py:14](../../../api/modules.py#L14)

DEPRECATED: use filename_for_file_resource instead

#### Signature

```python
def filename_for_resource(module: str, resource: str) -> str: ...
```



## get_resource_data

[Show source in modules.py:23](../../../api/modules.py#L23)

Get the dict data for a resource

#### Signature

```python
def get_resource_data(module: str, resource: str) -> ResourceDictType: ...
```



## insert_resource

[Show source in modules.py:28](../../../api/modules.py#L28)

Create a new resource, if it doesn't already exist,
and initializing it as appropriate for it's resource type

#### Signature

```python
def insert_resource(module: str, resource: str, resourceData: ResourceDictType): ...
```



## list_resources

[Show source in modules.py:63](../../../api/modules.py#L63)

#### Signature

```python
def list_resources(module: str) -> list[str]: ...
```



## resolve_file_resource

[Show source in modules.py:76](../../../api/modules.py#L76)

Given a name of a file resource, return the full path to it,
if it can be found in any module

#### Signature

```python
def resolve_file_resource(relative_path: str) -> str | None: ...
```



## scan_file_resources

[Show source in modules.py:68](../../../api/modules.py#L68)

Scan the resources in the filedata folder for the specified module.
Call if you directly change something, to update the UI.

#### Signature

```python
def scan_file_resources(module: str): ...
```



## update_resource

[Show source in modules.py:42](../../../api/modules.py#L42)

Update an existing resource

#### Signature

```python
def update_resource(module: str, resource: str, resourceData: ResourceDictType): ...
```