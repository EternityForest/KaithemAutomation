from kaithem.src.apps_page import App, add_app, remove_app

"""
This API lets you add apps to the apps page.

class App:
    def __init__(
        self,
        id,
        title,
        url,
        image="",
        module: str | None = None,
        resource: str | None = None,
    ):

add_app(app: App):
remove_app(app: App):

"""
__all__ = ["App", "add_app", "remove_app"]
