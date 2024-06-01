# Chandler

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Chandler

> Auto-generated documentation for [chandler](../../../api/chandler.py) module.

- [Chandler](#chandler)
  - [add_command](#add_command)
  - [shortcut](#shortcut)
  - [trigger_event](#trigger_event)

## add_command

[Show source in chandler.py:7](../../../api/chandler.py#L7)

Add a command which will be available in the
Logic Editor.  Params should be strings.  Defaults and
docstrings will be used.

#### Signature

```python
def add_command(name: str, f: Callable): ...
```



## shortcut

[Show source in chandler.py:20](../../../api/chandler.py#L20)

Trigger a shortcut code.  All matching cues will be jumped to.

#### Signature

```python
def shortcut(s: str): ...
```



## trigger_event

[Show source in chandler.py:15](../../../api/chandler.py#L15)

Trigger an event in all scenes

#### Signature

```python
def trigger_event(event: str, value: Any = None): ...
```