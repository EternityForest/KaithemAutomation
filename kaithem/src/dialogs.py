import html

from . import pages


class Dialog:
    def __init__(self, title) -> None:
        # List of title, inputhtml pairs
        self.items: list[tuple[str, str]] = []
        self.title = title

    def text(self, s: str):
        self.items.append(("", f"<p>{s}</s>"))

    def text_input(
        self, name: str, *, title: str | None = None, default: str = "", disabled=False
    ):
        title = title or name
        disabled = " disabled" if disabled else ""
        self.items.append(
            (title, f'<input name="{name}" value="{html.escape(default)}" {disabled}"')
        )

    def submit_button(
        self, name: str, *, title: str | None = None, value: str = "", disabled=False
    ):
        title = title or "submit"
        disabled = " disabled" if disabled else ""
        self.items.append(
            (title, f'<button  name="{name}" type="submit" {disabled}>{title}</button>')
        )

    def render(self, target: str, hidden_inputs: dict | None = None):
        return pages.render_jinja_template(
            "dialogs/generic.j2.html",
            items=self.items,
            hidden_inputs=hidden_inputs,
            target=target,
            title=self.title,
        )
