# Settings

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Settings

> Auto-generated documentation for [settings](../../../api/settings.py) module.

- [Settings](#settings)
  - [add_val](#add_val)
  - [get_val](#get_val)
  - [list_keys](#list_keys)

## add_val

[Show source in settings.py:13](../../../api/settings.py#L13)

#### Signature

```python
def add_val(key: str, value: str, source: str = "<code>", priority: float | int = 0): ...
```



## get_val

[Show source in settings.py:8](../../../api/settings.py#L8)

Returns the highest priority setting for the key

#### Signature

```python
def get_val(key: str) -> str: ...
```



## list_keys

[Show source in settings.py:4](../../../api/settings.py#L4)

#### Signature

```python
def list_keys() -> list[str]: ...
```