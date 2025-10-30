# kaithem.api.web.dialogs

## Attributes

| [`_auto_fn`](#kaithem.api.web.dialogs._auto_fn)   |    |
|---------------------------------------------------|----|
| [`_ace_code`](#kaithem.api.web.dialogs._ace_code) |    |

## Classes

| [`SimpleDialog`](#kaithem.api.web.dialogs.SimpleDialog)   | Class that generates a dialog.   |
|-----------------------------------------------------------|----------------------------------|

## Functions

| [`_suggestionize`](#kaithem.api.web.dialogs._suggestionize)(d[, path, datalists])   |    |
|-------------------------------------------------------------------------------------|----|

## Module Contents

### kaithem.api.web.dialogs.\_auto_fn *= Multiline-String*

<details><summary>Show Value</summary>
```python
"""
<script>
lastMsg = ''
let u = document.getElementsByName("file")[0];
let filename = document.getElementsByName("filename")[0];
// display file name if file has been selected
if(filename){
u.onchange = function() {
    let input = this.files[0];
    let text;
    if (input) {
        //process input
        text = u.value.replace("C:\\fakepath\\", "");
    } else {
        text = "";
    }

    if (filename.value==lastMsg)
    {
        filename.value = text;
        lastMsg = text;
    }
    else{
        lastMsg= "hgfdxdfghjkluytfdxcvbnhjkuytgfcv bnmkliouhg"
    }
};
};
</script>
"""
```

</details>

### kaithem.api.web.dialogs.\_ace_code *= Multiline-String*

<details><summary>Show Value</summary>
```python
"""
<script src="/static/js/thirdparty/src-min-noconflict/ace.js"></script>
<script src="/static/js/thirdparty/jquery3.js"></script>

<script>
    // Hook up ACE editor to all textareas with data-editor attribute
    $(function () {
        $('textarea[data-editor]').each(function () {
            var textarea = $(this);
            var mode = textarea.data('editor');
            var editDiv = $('<div>', {
                position: 'absolute',
                width: textarea.width(),
                'flex-basis': textarea.height(),
                height: textarea.height(),
                'class': textarea.attr('class')
            }).insertBefore(textarea);
            textarea.css('display', 'none');
            var editor = ace.edit(editDiv[0]);
            editor.renderer.setShowGutter(true);
            editor.getSession().setValue(textarea.val());
            editor.getSession().setMode("ace/mode/" + mode);
            // editor.setTheme("ace/theme/idle_fingers");
            editor.setOptions({
             fontFamily: "CodingFont",
            fontSize: "12pt"
            });

            editor.getSession().on('change', function() {
                wasChanged=true;
            })
            if(textarea.disabled){
                editor.setReadOnly(true)
            }
            // copy back to textarea on form submit...
            textarea.closest('form').submit(function () {
                textarea.val(editor.getSession().getValue());
            })
        });
    });
</script>
"""
```

</details>

### kaithem.api.web.dialogs.\_suggestionize(d: dict[str, Any], path='', datalists=None)

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
called to create one fron the control's name

#### is_disabled_by_default()

If an element does not specify whether it is disabled, this is called.
You can subclass it, by default it checks system_admin.

#### text(s: str)

Add some help text

#### link(s: str, url: str)

#### text_input(name: str, \*, title: str | None = None, default: str | int | float = '', disabled=None, suggestions: list[tuple[str, str]] | None = None, multiline=False)

#### begin_section(title: str)

#### end_section()

#### checkbox(name: str, \*, title: str | None = None, default=False, disabled=None)

Add a checkbox

#### file_input(name: str = 'file', \*, title: str | None = None, disabled=None)

Add a file upload input. Name it 'file' and name an input 'filename'  to auto link them.

#### code_editor(name: str = 'file', \*, language: str, title: str | None = None, disabled=None, default='')

Add a file upload input. Name it 'file' and name an input 'filename'  to auto link them.

#### selection(name: str, \*, options: list[str], default='', title: str | None = None, disabled=None)

Add a select element

#### submit_button(name: str, \*, title: str | None = None, value: str = '', disabled=None)

Add a submit button

#### json_editor(name: str, schema: dict[str, Any], default: dict[str, Any] = {})

#### render(target: str, hidden_inputs: dict[str, str | int | float] | None = None)

The form will target the given URL and have all the keys and values in hidden inputs
