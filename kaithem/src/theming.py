# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import logging
import os
import weakref

from scullery import persist

from . import directories
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
    persist.unsavedFiles.pop(fn, "")


cssthemes = weakref.WeakValueDictionary()


class Theme:
    def __init__(self, name, css_url: str = "") -> None:
        if name in cssthemes:
            raise ValueError(f"Theme {name} already exists")
        self.css_url = css_url
        cssthemes[name] = self


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


def getCSSTheme():
    x = file["web"]["csstheme"] or config["theme_url"]

    try:
        if x in cssthemes:
            return cssthemes[x].css_url

        else:
            return x
    except Exception:
        return None
