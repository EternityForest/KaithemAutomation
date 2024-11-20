# Dialogs

[Kaithemautomation Index](../README.md#kaithemautomation-index) / [Web](./index.md#web) / Dialogs

> Auto-generated documentation for [web.dialogs](../../../../api/web/dialogs.py) module.

- [Dialogs](#dialogs)
  - [SimpleDialog](#simpledialog)
    - [SimpleDialog().begin_section](#simpledialog()begin_section)
    - [SimpleDialog().checkbox](#simpledialog()checkbox)
    - [SimpleDialog().code_editor](#simpledialog()code_editor)
    - [SimpleDialog().end_section](#simpledialog()end_section)
    - [SimpleDialog().file_input](#simpledialog()file_input)
    - [SimpleDialog().is_disabled_by_default](#simpledialog()is_disabled_by_default)
    - [SimpleDialog().name_to_title](#simpledialog()name_to_title)
    - [SimpleDialog().render](#simpledialog()render)
    - [SimpleDialog().selection](#simpledialog()selection)
    - [SimpleDialog().submit_button](#simpledialog()submit_button)
    - [SimpleDialog().text](#simpledialog()text)
    - [SimpleDialog().text_input](#simpledialog()text_input)

## SimpleDialog

[Show source in dialogs.py:81](../../../../api/web/dialogs.py#L81)

Class that generates a dialog.

By default all inputs are disabled unless user has system_admin.
Items are shown in the order added. The rendered result is a full page ready
to serve to the user.

#### Signature

```python
class SimpleDialog:
    def __init__(self, title: str, method="POST") -> None: ...
```

### SimpleDialog().begin_section

[Show source in dialogs.py:162](../../../../api/web/dialogs.py#L162)

#### Signature

```python
def begin_section(self, title: str): ...
```

### SimpleDialog().checkbox

[Show source in dialogs.py:178](../../../../api/web/dialogs.py#L178)

Add a checkbox

#### Signature

```python
@beartype.beartype
def checkbox(
    self, name: str, title: str | None = None, default=False, disabled=None
): ...
```

### SimpleDialog().code_editor

[Show source in dialogs.py:226](../../../../api/web/dialogs.py#L226)

Add a file upload input. Name it 'file' and name an input 'filename'  to auto link them.

#### Signature

```python
@beartype.beartype
def code_editor(
    self,
    name: str = "file",
    language: str,
    title: str | None = None,
    disabled=None,
    default="",
): ...
```

### SimpleDialog().end_section

[Show source in dialogs.py:168](../../../../api/web/dialogs.py#L168)

#### Signature

```python
def end_section(self): ...
```

### SimpleDialog().file_input

[Show source in dialogs.py:206](../../../../api/web/dialogs.py#L206)

Add a file upload input. Name it 'file' and name an input 'filename'  to auto link them.

#### Signature

```python
@beartype.beartype
def file_input(self, name: str = "file", title: str | None = None, disabled=None): ...
```

### SimpleDialog().is_disabled_by_default

[Show source in dialogs.py:114](../../../../api/web/dialogs.py#L114)

If an element does not specify whether it is disabled, this is called.
You can subclass it, by default it checks system_admin.

#### Signature

```python
def is_disabled_by_default(self): ...
```

### SimpleDialog().name_to_title

[Show source in dialogs.py:105](../../../../api/web/dialogs.py#L105)

If title not provided, this will be
called to create one fron the control's name

#### Signature

```python
def name_to_title(self, s: str): ...
```

### SimpleDialog().render

[Show source in dialogs.py:315](../../../../api/web/dialogs.py#L315)

The form will target the given URL and have all the keys and values in hidden inputs

#### Signature

```python
@beartype.beartype
def render(
    self, target: str, hidden_inputs: dict[str, str | int | float] | None = None
): ...
```

### SimpleDialog().selection

[Show source in dialogs.py:254](../../../../api/web/dialogs.py#L254)

Add a select element

#### Signature

```python
@beartype.beartype
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

[Show source in dialogs.py:291](../../../../api/web/dialogs.py#L291)

Add a submit button

#### Signature

```python
@beartype.beartype
def submit_button(
    self, name: str, title: str | None = None, value: str = "", disabled=None
): ...
```

### SimpleDialog().text

[Show source in dialogs.py:120](../../../../api/web/dialogs.py#L120)

Add some help text

#### Signature

```python
def text(self, s: str): ...
```

### SimpleDialog().text_input

[Show source in dialogs.py:124](../../../../api/web/dialogs.py#L124)

#### Signature

```python
@beartype.beartype
def text_input(
    self,
    name: str,
    title: str | None = None,
    default: str = "",
    disabled=None,
    suggestions: list[tuple[str, str]] | None = None,
    multiline=False,
): ...
```