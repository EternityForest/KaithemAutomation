#!/usr/bin/env python3

from distutils.core import setup

kwargs = {
    "name":         "python-mpv",
    "author":       "Lars Gustäbel",
    "author_email": "lars@gustaebel.de",
    "url":          "http://github.com/gustaebel/python-mpv/",
    "description":  "control mpv from Python using JSON IPC",
    "license":      "MIT",
    "py_modules":   ["mpv"],
}

setup(**kwargs)

