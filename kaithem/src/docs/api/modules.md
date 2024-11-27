# Modules

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Modules

> Auto-generated documentation for [modules](../../../api/modules.py) module.

- [Modules](#modules)
  - [admin_url_for_file_resource](#admin_url_for_file_resource)
  - [delete_resource](#delete_resource)
  - [filename_for_resource](#filename_for_resource)
  - [get_resource_data](#get_resource_data)
  - [insert_resource](#insert_resource)
  - [list_resources](#list_resources)
  - [scan_file_resources](#scan_file_resources)
  - [update_resource](#update_resource)

## admin_url_for_file_resource

[Show source in modules.py:14](../../../api/modules.py#L14)

#### Signature

```python
def admin_url_for_file_resource(module: str, resource: str) -> str: ...
```



## delete_resource

[Show source in modules.py:54](../../../api/modules.py#L54)

#### Signature

```python
def delete_resource(module: str, resource: str): ...
```



## filename_for_resource

[Show source in modules.py:7](../../../api/modules.py#L7)

Given the module and resource, return the actual file for a file resource, or
file data dir for directory resource

#### Signature

```python
def filename_for_resource(module: str, resource: str) -> str: ...
```



## get_resource_data

[Show source in modules.py:18](../../../api/modules.py#L18)

Get the dict data for a resource

#### Signature

```python
def get_resource_data(module: str, resource: str) -> ResourceDictType: ...
```



## insert_resource

[Show source in modules.py:23](../../../api/modules.py#L23)

Create a new resource, if it doesn't already exist,
and initializing it as appropriate for it's resource type

#### Signature

```python
def insert_resource(module: str, resource: str, resourceData: ResourceDictType): ...
```



## list_resources

[Show source in modules.py:58](../../../api/modules.py#L58)

#### Signature

```python
def list_resources(module: str) -> list[str]: ...
```



## scan_file_resources

[Show source in modules.py:63](../../../api/modules.py#L63)

Scan the resources in the filedata folder for the specified module.
Call if you directly change something, to update the UI.

#### Signature

```python
def scan_file_resources(module: str): ...
```



## update_resource

[Show source in modules.py:37](../../../api/modules.py#L37)

Update an existing resource

#### Signature

```python
def update_resource(module: str, resource: str, resourceData: ResourceDictType): ...
```