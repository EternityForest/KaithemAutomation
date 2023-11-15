from .config import config
from . import directories
from scullery import persist
from scullery import messagebus

import os
import logging

fn = os.path.join(directories.vardir, "core.settings", "theming.toml")

if os.path.exists(fn):
    file = persist.load(fn)
else:
    file = {}

if not 'web' in file:
    file['web'] = {}
    css = ''

    file['web']['csstheme'] = css

    try:
        persist.save(file, fn, private=True)
    except Exception:
        logging.exception("Save fail")


def saveTheme(*a,**k):
    persist.save(file, fn, private=True)
    persist.unsavedFiles.pop(fn,"")



import weakref

cssthemes = weakref.WeakValueDictionary()

class Theme():
    def __init__(self,name,css_url:str= '') -> None:
        self.css_url = css_url
        cssthemes[name]=self

scrapbook = Theme("scrapbook", "/static/css/scrapbook/scrapbook_green.css")
fugit = Theme("fugit", "/static/css/fugit/fugit.css")
simple_dark = Theme("simple_dark", "/static/css/kaithem_simple_dark.css")
simple_light = Theme("simple_light", "/static/css/barrel.css")
banderole = Theme("banderole", "/static/css/banderole/banderole.css")
nord = Theme("nord", "/static/css/nord.css")
blast = Theme("blast", "/static/css/blast.css")
lair = Theme("lair", "/static/css/lair.css")
steam = Theme("steam", "/static/css/steam.css")


def getCSSTheme():
    x = file['web']['csstheme'] or config['theme-url']

    try:
        if x in cssthemes:
            return cssthemes[x].css_url

        else:
            return x
    except:
        return None

