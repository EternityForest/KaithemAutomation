# Chandler

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Chandler

> Auto-generated documentation for [chandler](../../../api/chandler.py) module.

- [Chandler](#chandler)
  - [add_command](#add_command)
  - [shortcut](#shortcut)
  - [trigger_event](#trigger_event)

## add_command

[Show source in chandler.py:6](../../../api/chandler.py#L6)

Add a command which will be available in the
Logic Editor.  Params should be strings.  Defaults and
docstrings will be used.

#### Signature

```python
def add_command(name: str, f: Callable): ...
```



## shortcut

[Show source in chandler.py:19](../../../api/chandler.py#L19)

Trigger a shortcut code.  All matching cues will be jumped to.

#### Signature

```python
def shortcut(s: str): ...
```



## trigger_event

[Show source in chandler.py:14](../../../api/chandler.py#L14)

Trigger an event in all scenes

#### Signature

```python
def trigger_event(event: str, value: Any = None): ...
```