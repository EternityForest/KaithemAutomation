from __future__ import annotations

import weakref

from kaithem.api.web import nav_bar_plugins, require

from . import pages
from .modules_state import get_resource_label_image_url
from .quart_app import app


def nbr():
    return '<a href="/apps"><i class="mdi mdi-apps"></i>Apps</a>'


nav_bar_plugins["Apps"] = nbr

all_apps: weakref.WeakValueDictionary[str, App] = weakref.WeakValueDictionary()


@app.route("/apps")
def apps_page():
    require("view_status")
    require("enumerate_endpoints")

    return pages.render_jinja_template("apps.j2.html", apps=all_apps)


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
        """Represents an app to be shown on the apps page"""
        id = (
            id.lower()
            .replace(" ", "_")
            .replace("-", "_")
            .replace(".", "_")
            .replace("/", "_")
        )
        id = id.replace(":", "_").replace("(", "_").replace(")", "_")
        if id in all_apps:
            raise ValueError(f"App id {id} is not unique")
        self.id = id
        self.title = title
        self.url = url
        self.icon = image
        self.footer = ""
        self.html_color = ""

        self.links: list[tuple[str, str]] = []

        self.module = module
        self.resource = resource

        if self.module and self.resource:
            self.icon = get_resource_label_image_url(self.module, self.resource)

    def render(self):
        return pages.render_jinja_template(
            "jinjatemplates/app_icon.j2.html", app=self
        )

    def get_image(self):
        if self.module and self.resource:
            return (
                get_resource_label_image_url(self.module, self.resource)
                or self.icon
            )
        return self.icon


def add_app(app):
    if app.id in all_apps:
        if all_apps[app.id] is not app:
            raise ValueError("App id is not unique")
    all_apps[app.id] = app


def remove_app(app):
    try:
        del all_apps[app.id]
    except KeyError:
        pass
