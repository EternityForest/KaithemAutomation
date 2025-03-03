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

## add_suggestion

[Show source in settings.py:21](../../../api/settings.py#L21)

Add a suggestion for the given key

#### Signature

```python
def add_suggestion(key: str, value: str, description: str = ""): ...
```



## add_val

[Show source in settings.py:14](../../../api/settings.py#L14)

Add a config option.   If value is empty string, remove it instead.

#### Signature

```python
def add_val(key: str, value: str, source: str = "<code>", priority: float | int = 0): ...
```



## clear_suggestions

[Show source in settings.py:26](../../../api/settings.py#L26)

#### Signature

```python
def clear_suggestions(key: str): ...
```



## get_val

[Show source in settings.py:9](../../../api/settings.py#L9)

Returns the highest priority setting for the key

#### Signature

```python
def get_val(key: str) -> str: ...
```



## list_keys

[Show source in settings.py:4](../../../api/settings.py#L4)

List all known setting keys

#### Signature

```python
def list_keys() -> list[str]: ...
```



## set_description

[Show source in settings.py:30](../../../api/settings.py#L30)

#### Signature

```python
def set_description(key: str, description: str): ...
```