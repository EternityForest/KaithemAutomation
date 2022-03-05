from src.config import config
from src import registry
from src import directories
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
    # Legacy registry stuff.
    file['web'] = {}
    css = registry.get("/system.theming/csstheme", "")

    file['web']['csstheme'] = css

    try:
        persist.save(file, fn, private=True)
    except:
        logging.exception("Save fail")


def saveTheme(*a,**k):
    persist.save(file, fn, private=True)
    persist.unsavedFiles.pop(fn,"")

def setDirty():
    persist.unsavedFiles[fn]="Theme changed"


def getCSSTheme():
    return file['web']['csstheme'] or config['theme-url']

messagebus.subscribe("/system/save", saveTheme)