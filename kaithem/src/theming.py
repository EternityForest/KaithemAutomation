# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import time
import weakref

from scullery import persist

from kaithem.api import settings

from . import directories, quart_app, settings_overrides
from .config import config

fn = os.path.join(directories.vardir, "core.settings", "theming.toml")

if os.path.exists(fn):
    file = persist.load(fn)
else:
    file = {}

if "web" not in file:
    file["web"] = {}
    css = ""

    file["web"]["csstheme"] = css

    try:
        persist.save(file, fn, private=True)
    except Exception:
        logging.exception("Save fail")


def saveTheme(*a, **k):
    persist.save(file, fn, private=True)


cssthemes = weakref.WeakValueDictionary()


class Theme:
    def __init__(self, name, css_url: str = "") -> None:
        if name in cssthemes:
            raise ValueError(f"Theme {name} already exists")
        self.css_url = css_url
        cssthemes[name] = self

        settings_overrides.add_suggestion("core/css_theme", name)


scrapbook = Theme("scrapbook", "/static/css/scrapbook/scrapbook_green.css")
fugit = Theme("fugit", "/static/css/fugit/fugit.css")
simple_dark = Theme("simple_dark", "/static/css/kaithem_simple_dark.css")
simple_light = Theme("simple_light", "/static/css/barrel.css")
banderole = Theme("banderole", "/static/css/banderole/banderole.css")
nord = Theme("nord", "/static/css/nord.css")
blast = Theme("blast", "/static/css/blast.css")
lair = Theme("lair", "/static/css/lair.css")
steam = Theme("steam", "/static/css/steam.css")
show_black = Theme("show_black", "/static/css/show_black.css")
forest = Theme("forest", "/static/css/forest.css")


settings_overrides.set_description(
    "core/css_theme", "Barrel theme URL or any predefined theme name"
)

settings_overrides.set_description(
    "core/ui_font",
    "UI font name, defaults to AtkinsonHyperlegible.  Can be overridden by certain themes.",
)

settings_overrides.add_suggestion("core/ui_font", "AtkinsonHyperlegible")
settings_overrides.add_suggestion("core/ui_font", "Lora")
settings_overrides.add_suggestion("core/ui_font", "Lato")
settings_overrides.add_suggestion("core/ui_font", "AlegrayaSans")
settings_overrides.add_suggestion("core/ui_font", """sans""")
settings_overrides.add_suggestion("core/ui_font", """serif""")


def getCSSTheme():
    x = settings_overrides.get_val("core/css_theme") or config["theme_url"]

    try:
        if x in cssthemes:
            return cssthemes[x].css_url

        else:
            return x
    except Exception:
        return None


theme_ver: float = time.time()


def handleThemeChange(*a, **k):
    global theme_ver
    theme_ver = time.time()


settings.subscribe_to_changes("core/css_theme", handleThemeChange)
settings.subscribe_to_changes("core/body_font", handleThemeChange)


@quart_app.app.route("/dynamic.css/<version>", methods=["GET"])
async def dynamicCSS(version):
    rules = []

    rules.append(
        f"--main-font: {settings_overrides.get_val('core/ui_font') or 'AtkinsonHyperlegible'};"
    )

    rules2 = "\n".join(rules)

    x = f"""
:root{{
    {rules2}
}}
    """

    y = await quart_app.app.make_response(x)
    y.mimetype = "text/css"

    return y
