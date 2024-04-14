# Dialogs

[Kaithemautomation Index](../README.md#kaithemautomation-index) / [Web](./index.md#web) / Dialogs

> Auto-generated documentation for [web.dialogs](../../../../api/web/dialogs.py) module.

- [Dialogs](#dialogs)
  - [SimpleDialog](#simpledialog)
    - [SimpleDialog().checkbox](#simpledialog()checkbox)
    - [SimpleDialog().is_disabled_by_default](#simpledialog()is_disabled_by_default)
    - [SimpleDialog().name_to_title](#simpledialog()name_to_title)
    - [SimpleDialog().render](#simpledialog()render)
    - [SimpleDialog().selection](#simpledialog()selection)
    - [SimpleDialog().submit_button](#simpledialog()submit_button)
    - [SimpleDialog().text](#simpledialog()text)
    - [SimpleDialog().text_input](#simpledialog()text_input)

## SimpleDialog

[Show source in dialogs.py:6](../../../../api/web/dialogs.py#L6)

Class that generates a dialog.

By default all inputs are disabled unless user has system_admin.
Items are shown in the order added. The rendered result is a full page ready
to serve to the user.

#### Signature

```python
class SimpleDialog:
    def __init__(self, title: str) -> None: ...
```

### SimpleDialog().checkbox

[Show source in dialogs.py:49](../../../../api/web/dialogs.py#L49)

Add a checkbox

#### Signature

```python
def checkbox(
    self, name: str, title: str | None = None, default=False, disabled=None
): ...
```

### SimpleDialog().is_disabled_by_default

[Show source in dialogs.py:29](../../../../api/web/dialogs.py#L29)

If an element does not specify whether it is disabled, this is called.
You can subclass it, by default it checks system_admin.

#### Signature

```python
def is_disabled_by_default(self): ...
```

### SimpleDialog().name_to_title

[Show source in dialogs.py:20](../../../../api/web/dialogs.py#L20)

If title not provided, this will be
called to create one fron the control's name

#### Signature

```python
def name_to_title(self, s: str): ...
```

### SimpleDialog().render

[Show source in dialogs.py:97](../../../../api/web/dialogs.py#L97)

The form will target the given URL and have all the keys and values in hidden inputs

#### Signature

```python
def render(self, target: str, hidden_inputs: dict | None = None): ...
```

### SimpleDialog().selection

[Show source in dialogs.py:61](../../../../api/web/dialogs.py#L61)

Add a select element

#### Signature

```python
def selection(
    self,
    name: str,
    options: list[str],
    default="",
    title: str | None = None,
    disabled=None,
): ...
```

### SimpleDialog().submit_button

[Show source in dialogs.py:88](../../../../api/web/dialogs.py#L88)

Add a submit button

#### Signature

```python
def submit_button(
    self, name: str, title: str | None = None, value: str = "", disabled=None
): ...
```

### SimpleDialog().text

[Show source in dialogs.py:35](../../../../api/web/dialogs.py#L35)

Add some help text

#### Signature

```python
def text(self, s: str): ...
```

### SimpleDialog().text_input

[Show source in dialogs.py:39](../../../../api/web/dialogs.py#L39)

Add a text input

#### Signature

```python
def text_input(
    self, name: str, title: str | None = None, default: str = "", disabled=None
): ...
```