# kaithem.api.web.dialogs

## Classes

| [`SimpleDialog`](#kaithem.api.web.dialogs.SimpleDialog)   | Class that generates a dialog.   |
|-----------------------------------------------------------|----------------------------------|

## Module Contents

### *class* kaithem.api.web.dialogs.SimpleDialog(title: [str](../../../src/pages/index.md#kaithem.src.pages.str), method='POST')

Class that generates a dialog.

By default all inputs are disabled unless user has system_admin.
Items are shown in the order added. The rendered result is a full page ready
to serve to the user.

#### items *: [list](../../../src/pages/index.md#kaithem.src.pages.list)[tuple[[str](../../../src/pages/index.md#kaithem.src.pages.str), [str](../../../src/pages/index.md#kaithem.src.pages.str)]]* *= []*

#### title

#### datalists *: dict[[str](../../../src/pages/index.md#kaithem.src.pages.str), [list](../../../src/pages/index.md#kaithem.src.pages.list)[tuple[[str](../../../src/pages/index.md#kaithem.src.pages.str), [str](../../../src/pages/index.md#kaithem.src.pages.str)]]]*

#### method *= 'POST'*

#### using_uploads *= False*

#### using_ace *= False*

#### extracode *= ''*

#### default_return_value *: dict[[str](../../../src/pages/index.md#kaithem.src.pages.str), [str](../../../src/pages/index.md#kaithem.src.pages.str)]*

#### name_to_title(s: [str](../../../src/pages/index.md#kaithem.src.pages.str))

If title not provided, this will be
called to create one fron the control’s name

#### is_disabled_by_default()

If an element does not specify whether it is disabled, this is called.
You can subclass it, by default it checks system_admin.

#### text(s: [str](../../../src/pages/index.md#kaithem.src.pages.str))

Add some help text

#### link(s: [str](../../../src/pages/index.md#kaithem.src.pages.str), url: [str](../../../src/pages/index.md#kaithem.src.pages.str))

#### text_input(name: [str](../../../src/pages/index.md#kaithem.src.pages.str), , title: [str](../../../src/pages/index.md#kaithem.src.pages.str) | None = None, default: [str](../../../src/pages/index.md#kaithem.src.pages.str) | [int](../../../src/chandler/groups/index.md#kaithem.src.chandler.groups.int) | [float](../../../src/chandler/groups/index.md#kaithem.src.chandler.groups.float) = '', disabled=None, suggestions: [list](../../../src/pages/index.md#kaithem.src.pages.list)[tuple[[str](../../../src/pages/index.md#kaithem.src.pages.str), [str](../../../src/pages/index.md#kaithem.src.pages.str)]] | None = None, multiline=False)

#### begin_section(title: [str](../../../src/pages/index.md#kaithem.src.pages.str))

#### end_section()

#### checkbox(name: [str](../../../src/pages/index.md#kaithem.src.pages.str), , title: [str](../../../src/pages/index.md#kaithem.src.pages.str) | None = None, default=False, disabled=None)

Add a checkbox

#### file_input(name: [str](../../../src/pages/index.md#kaithem.src.pages.str) = 'file', , title: [str](../../../src/pages/index.md#kaithem.src.pages.str) | None = None, disabled=None)

Add a file upload input. Name it ‘file’ and name an input ‘filename’  to auto link them.

#### code_editor(name: [str](../../../src/pages/index.md#kaithem.src.pages.str) = 'file', , language: [str](../../../src/pages/index.md#kaithem.src.pages.str), title: [str](../../../src/pages/index.md#kaithem.src.pages.str) | None = None, disabled=None, default='')

Add a file upload input. Name it ‘file’ and name an input ‘filename’  to auto link them.

#### selection(name: [str](../../../src/pages/index.md#kaithem.src.pages.str), , options: [list](../../../src/pages/index.md#kaithem.src.pages.list)[[str](../../../src/pages/index.md#kaithem.src.pages.str)], default='', title: [str](../../../src/pages/index.md#kaithem.src.pages.str) | None = None, disabled=None)

Add a select element

#### submit_button(name: [str](../../../src/pages/index.md#kaithem.src.pages.str), , title: [str](../../../src/pages/index.md#kaithem.src.pages.str) | None = None, value: [str](../../../src/pages/index.md#kaithem.src.pages.str) = '', disabled=None)

Add a submit button

#### json_editor(name: [str](../../../src/pages/index.md#kaithem.src.pages.str), schema: dict[[str](../../../src/pages/index.md#kaithem.src.pages.str), Any], default: dict[[str](../../../src/pages/index.md#kaithem.src.pages.str), Any] = {})

#### render(target: [str](../../../src/pages/index.md#kaithem.src.pages.str), hidden_inputs: dict[[str](../../../src/pages/index.md#kaithem.src.pages.str), [str](../../../src/pages/index.md#kaithem.src.pages.str) | [int](../../../src/chandler/groups/index.md#kaithem.src.chandler.groups.int) | [float](../../../src/chandler/groups/index.md#kaithem.src.chandler.groups.float)] | None = None)

The form will target the given URL and have all the keys and values in hidden inputs
