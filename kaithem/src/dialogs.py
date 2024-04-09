import html

from . import pages


class Dialog:
    "By default all inputs are disabled unless user has system_admin"

    def __init__(self, title) -> None:
        # List of title, inputhtml pairs
        self.items: list[tuple[str, str]] = []
        self.title = title

    def name_to_title(self, s: str):
        if "." not in s and "-" not in s:
            return s.capitalize()
        else:
            return s

    def is_disabled_by_default(self):
        return not pages.canUserDoThis("system_admin")

    def text(self, s: str):
        self.items.append(("", f"<p>{s}</p>"))

    def text_input(self, name: str, *, title: str | None = None, default: str = "", disabled=None):
        title = title or self.name_to_title(name)

        if disabled is None:
            disabled = self.is_disabled_by_default()

        disabled = " disabled" if disabled else ""
        self.items.append((title, f'<input name="{name}" value="{html.escape(default)}" {disabled}>'))

    def checkbox(self, name: str, *, title: str | None = None, default: str = "", disabled=None):
        title = title or self.name_to_title(name)

        if disabled is None:
            disabled = self.is_disabled_by_default()

        disabled = " disabled" if disabled else ""
        checked = "checked" if default else ""

        self.items.append((title, f'<input type="checkbox" name="{name}" {checked} {disabled}>'))

    def selection(self, name: str, *, options: list[str], title: str | None = None, disabled=None):
        title = title or self.name_to_title(name)

        if disabled is None:
            disabled = self.is_disabled_by_default()

        disabled = " disabled" if disabled else ""

        options = options or []

        o = ""

        for i in options:
            o += f"<option>{i}</option>\n"

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

    def submit_button(self, name: str, *, title: str | None = None, value: str = "", disabled=None):
        if disabled is None:
            disabled = self.is_disabled_by_default()

        title = title or "Submit"
        disabled = " disabled" if disabled else ""
        self.items.append(("", f'<button  name="{name}" type="submit" {disabled}>{title}</button>'))

    def render(self, target: str, hidden_inputs: dict | None = None):
        "The form will target the given URL and have all the keys and values in hidden inputs"
        return pages.render_jinja_template(
            "dialogs/generic.j2.html",
            items=self.items,
            hidden_inputs=hidden_inputs,
            target=target,
            title=self.title,
        )
