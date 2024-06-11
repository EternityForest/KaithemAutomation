# Modules

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Modules

> Auto-generated documentation for [modules](../../../api/modules.py) module.

- [Modules](#modules)
  - [delete_resource](#delete_resource)
  - [filename_for_resource](#filename_for_resource)
  - [get_resource_data](#get_resource_data)
  - [insert_resource](#insert_resource)
  - [list_resources](#list_resources)
  - [update_resource](#update_resource)

## delete_resource

[Show source in modules.py:43](../../../api/modules.py#L43)

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

[Show source in modules.py:16](../../../api/modules.py#L16)

Get the dict data for a resource

#### Signature

```python
def get_resource_data(module: str, resource: str) -> ResourceDictType: ...
```



## insert_resource

[Show source in modules.py:21](../../../api/modules.py#L21)

Create a new resource, if it doesn't already exist,
and initializing it as appropriate for it's resource type

#### Signature

```python
def insert_resource(module: str, resource: str, resourceData: ResourceDictType): ...
```



## list_resources

[Show source in modules.py:47](../../../api/modules.py#L47)

#### Signature

```python
def list_resources(module: str) -> list[str]: ...
```



## update_resource

[Show source in modules.py:33](../../../api/modules.py#L33)

Update an existing resource

#### Signature

```python
def update_resource(module: str, resource: str, resourceData: ResourceDictType): ...
```