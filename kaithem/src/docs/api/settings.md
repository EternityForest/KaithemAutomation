# Settings

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Settings

> Auto-generated documentation for [settings](../../../api/settings.py) module.

- [Settings](#settings)
  - [add_suggestion](#add_suggestion)
  - [add_val](#add_val)
  - [clear_suggestions](#clear_suggestions)
  - [get_val](#get_val)
  - [list_keys](#list_keys)
  - [set_description](#set_description)
  - [subscribe_to_changes](#subscribe_to_changes)

## add_suggestion

[Show source in settings.py:23](../../../api/settings.py#L23)

Add a suggestion for the given key

#### Signature

```python
def add_suggestion(key: str, value: str, description: str = ""): ...
```



## add_val

[Show source in settings.py:16](../../../api/settings.py#L16)

Add a config option.   If value is empty string, remove it instead.

#### Signature

```python
def add_val(key: str, value: str, source: str = "<code>", priority: float | int = 0): ...
```



## clear_suggestions

[Show source in settings.py:28](../../../api/settings.py#L28)

#### Signature

```python
def clear_suggestions(key: str): ...
```



## get_val

[Show source in settings.py:11](../../../api/settings.py#L11)

Returns the highest priority setting for the key

#### Signature

```python
def get_val(key: str) -> str: ...
```



## list_keys

[Show source in settings.py:6](../../../api/settings.py#L6)

List all known setting keys

#### Signature

```python
def list_keys() -> list[str]: ...
```



## set_description

[Show source in settings.py:32](../../../api/settings.py#L32)

#### Signature

```python
def set_description(key: str, description: str): ...
```



## subscribe_to_changes

[Show source in settings.py:36](../../../api/settings.py#L36)

#### Signature

```python
def subscribe_to_changes(key, callback): ...
```