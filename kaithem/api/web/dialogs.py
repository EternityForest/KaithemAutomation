import html

import beartype

from kaithem.src import pages

_auto_fn = """
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
        text = u.value.replace("C:\\\\fakepath\\\\", "");
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

_ace_code = """
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


class SimpleDialog:
    """
    Class that generates a dialog.

    By default all inputs are disabled unless user has system_admin.
    Items are shown in the order added. The rendered result is a full page ready
    to serve to the user.
    """

    def __init__(self, title: str, method="POST") -> None:
        # List of title, inputhtml pairs
        self.items: list[tuple[str, str]] = []
        self.title = title
        self.datalists: dict[str, list[tuple[str, str]]] = {}
        self.method = method

        self.using_uploads = False
        self.using_ace = False

        self.extracode = ""

        # The what would be submitted with all the defaults.
        self.default_return_value: dict[str, str] = {}

    def name_to_title(self, s: str):
        """If title not provided, this will be
        called to create one fron the control's name
        """
        if "." not in s and "-" not in s:
            return s.capitalize()
        else:
            return s

    def is_disabled_by_default(self):
        """If an element does not specify whether it is disabled, this is called.
        You can subclass it, by default it checks system_admin.
        """
        return not pages.canUserDoThis("system_admin")

    def text(self, s: str):
        "Add some help text"
        self.items.append(("", f"<p>{s}</p>"))

    @beartype.beartype
    def text_input(
        self,
        name: str,
        *,
        title: str | None = None,
        default: str = "",
        disabled=None,
        suggestions: list[tuple[str, str]] | None = None,
        multiline=False,
    ):
        self.default_return_value[name] = default or ""

        "Add a text input. Datalist can be value, title pairs"
        if suggestions:
            if f"x-{id(suggestions)}" not in self.datalists:
                self.datalists[f"x-{id(suggestions)}"] = suggestions

        title = title or self.name_to_title(name)

        if disabled is None:
            disabled = self.is_disabled_by_default()

        disabled = " disabled" if disabled else ""

        if multiline:
            x = f"""<textarea name="{name}" {disabled} class="max-h-24rem"
            oninput='this.style.height = "";
            this.style.height = this.scrollHeight + "px"'>{html.escape(default)}</textarea>"""
            self.items.append((title, x))
        else:
            self.items.append(
                (
                    title,
                    f'<input name="{name}" list="x-{id(suggestions)}"  value="{html.escape(default)}" {disabled}>',
                )
            )

    def begin_section(self, title: str):
        self.items_main = self.items
        self.items = []

        self.section_title = title

    def end_section(self):
        s = f"<details><summary>{self.section_title}</summary>"
        s += '<div class="scroll h-12rem stacked-form">'
        for i in self.items:
            s += f"<label>{i[0]}\n{i[1]}</label>"
        s += "</div></details>"

        self.items_main.append(("", s))
        self.items = self.items_main

    @beartype.beartype
    def checkbox(
        self,
        name: str,
        *,
        title: str | None = None,
        default=False,
        disabled=None,
    ):
        "Add a checkbox"
        title = title or self.name_to_title(name)

        if default:
            self.default_return_value[name] = ""

        if disabled is None:
            disabled = self.is_disabled_by_default()

        disabled = " disabled" if disabled else ""
        checked = "checked" if default else ""

        self.items.append(
            (
                title,
                f'<input type="checkbox" name="{name}" {checked} {disabled}>',
            )
        )

    @beartype.beartype
    def file_input(
        self, name: str = "file", *, title: str | None = None, disabled=None
    ):
        "Add a file upload input. Name it 'file' and name an input 'filename'  to auto link them."
        title = title or self.name_to_title(name)

        if disabled is None:
            disabled = self.is_disabled_by_default()

        disabled = " disabled" if disabled else ""

        self.items.append(
            (title, f'<input type="file" name="{name}" {disabled}>')
        )

        if not self.using_uploads:
            self.extracode += _auto_fn + "\n"
            self.using_uploads = True

    @beartype.beartype
    def code_editor(
        self,
        name: str = "file",
        *,
        language: str,
        title: str | None = None,
        disabled=None,
        default="",
    ):
        "Add a file upload input. Name it 'file' and name an input 'filename'  to auto link them."
        title = title or self.name_to_title(name)

        if disabled is None:
            disabled = self.is_disabled_by_default()

        disabled = " disabled" if disabled else ""
        self.items.append(
            (
                title,
                f'<textarea data-editor="{language}" rows=25 class="w-full" name="{name}" {disabled}>{html.escape(default)}</textarea>',
            )
        )

        if not self.using_ace:
            self.using_ace = True
            self.extracode += _ace_code + "\n"

    @beartype.beartype
    def selection(
        self,
        name: str,
        *,
        options: list[str],
        default="",
        title: str | None = None,
        disabled=None,
    ):
        "Add a select element"
        title = title or self.name_to_title(name)
        self.default_return_value[name] = default or ""

        if disabled is None:
            disabled = self.is_disabled_by_default()

        disabled = " disabled" if disabled else ""

        options = options or []

        o = ""

        for i in options:
            o += f"<option{' selected' if i==default else ''}>{i}</option>\n"

        self.items.append(
            (
                title,
                f"""
                <select name="{name}">
                    {o}
                </select>
             """,
            )
        )

    @beartype.beartype
    def submit_button(
        self,
        name: str,
        *,
        title: str | None = None,
        value: str = "",
        disabled=None,
    ):
        "Add a submit button"
        if disabled is None:
            disabled = self.is_disabled_by_default()

        self.default_return_value[name] = value or ""

        title = title or "Submit"
        disabled = " disabled" if disabled else ""
        self.items.append(
            (
                "",
                f'<button  name="{name}" type="submit" {disabled}>{title}</button>',
            )
        )

    @beartype.beartype
    def render(
        self,
        target: str,
        hidden_inputs: dict[str, str | int | float] | None = None,
    ):
        "The form will target the given URL and have all the keys and values in hidden inputs"
        return pages.render_jinja_template(
            "dialogs/generic.j2.html",
            items=self.items,
            hidden_inputs=hidden_inputs or {},
            target=target,
            title=self.title,
            datalists=self.datalists,
            extracode=self.extracode,
            method=self.method,
        )
