# kaithem.api.web.dialogs

## Classes

| [`SimpleDialog`](#kaithem.api.web.dialogs.SimpleDialog)   | Class that generates a dialog.   |
|-----------------------------------------------------------|----------------------------------|

## Module Contents

### *class* kaithem.api.web.dialogs.SimpleDialog(title: str, method='POST')

Class that generates a dialog.

By default all inputs are disabled unless user has system_admin.
Items are shown in the order added. The rendered result is a full page ready
to serve to the user.

#### items *: list[tuple[str, str]]* *= []*

#### title

#### datalists *: dict[str, list[tuple[str, str]]]*

#### method *= 'POST'*

#### using_uploads *= False*

#### using_ace *= False*

#### extracode *= ''*

#### default_return_value *: dict[str, str]*

#### name_to_title(s: str)

If title not provided, this will be
called to create one fron the control’s name

#### is_disabled_by_default()

If an element does not specify whether it is disabled, this is called.
You can subclass it, by default it checks system_admin.

#### text(s: str)

Add some help text

#### link(s: str, url: str)

#### text_input(name: str, , title: str | None = None, default: str | int | float = '', disabled=None, suggestions: list[tuple[str, str]] | None = None, multiline=False)

#### begin_section(title: str)

#### end_section()

#### checkbox(name: str, , title: str | None = None, default=False, disabled=None)

Add a checkbox

#### file_input(name: str = 'file', , title: str | None = None, disabled=None)

Add a file upload input. Name it ‘file’ and name an input ‘filename’  to auto link them.

#### code_editor(name: str = 'file', , language: str, title: str | None = None, disabled=None, default='')

Add a file upload input. Name it ‘file’ and name an input ‘filename’  to auto link them.

#### selection(name: str, , options: list[str], default='', title: str | None = None, disabled=None)

Add a select element

#### submit_button(name: str, , title: str | None = None, value: str = '', disabled=None)

Add a submit button

#### json_editor(name: str, schema: dict[str, Any], default: dict[str, Any] = {})

#### render(target: str, hidden_inputs: dict[str, str | int | float] | None = None)

The form will target the given URL and have all the keys and values in hidden inputs
