# Copyright Daniel Dunn 2013. 2015
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

from typing import Optional
import stat
import os
import json
from pwd import getpwuid, getpwnam
from scullery.persist import *
from scullery.messagebus import subscribe, post_message

import weakref
import threading
import logging
import traceback
import urllib.parse

dirty = weakref.WeakValueDictionary()

dirty_state_files = dirty

stateFileLock = threading.RLock()

import os
import pwd


selected_user = pwd.getpwuid( os.geteuid() ).pw_name



class SharedStateFile():
    """
        This is a dict that is backed by a file
    """

    def __init__(self, filename, save_topic="/system/save"):
        if os.path.exists(filename):
            try:
                self.data = load(filename)
            except Exception:
                self.data = {}
                post_message("/system/notifications/errors",
                            filename+"\n"+traceback.format_exc())
        else:
            self.data = {}

        self.filename = filename
        self.lock = threading.RLock()
        self.noFileForEmpty = False
        self.private=True
        allFiles[filename] = self
        if save_topic:
            subscribe(save_topic, self.save)

    def setupDefaults(self, defaults={}):
        for i in defaults:
            if not i in self.data:
                self.set(i, defaults[i])

    def get(self, key, default=None):
        with self.lock:
            return self.data.get(key, default)

    def __contains__(self, key):
        if key in self.data:
            return True

    def getAllData(self):
        with self.lock:
            return self.data.copy()

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)

    def __delitem__(self, key):
        self.pop(key)

    def set(self, key: str, value):
        with self.lock:
            json.dumps(value)
            if not isinstance(key, str):
                raise RuntimeError("Key must be str")
            
            if  key in self.data and self.data[key]==value:
                return
            self.data[key] = value
            self.save()

    def clear(self):
        with self.lock:
            self.data.clear()
            self.save()

    def pop(self, key, default=None):
        with self.lock:
            self.data.pop(key, default)
            self.save()

    def delete(self, key):
        with self.lock:
            try:
                del self.data[key]
            except KeyError:
                pass
            self.save()

    def save(self):
        with self.lock:
            # NoFileForEmpty mode deleted
            if self.noFileForEmpty and (not self.data):
                self.tryDeleteFile()
            else:
                save(self.data, self.filename,private=self.private)

    def tryDeleteFile(self):
        if os.path.exists(self.filename):
            try:
                os.remove(self.filename)
            except:
                logging.exception("wat")

#Py3.8 doesn't like this line.  Use the better typing once 3.9 is in all the big distros
#allFiles: weakref.WeakValueDictionary[str,SharedStateFile] = weakref.WeakValueDictionary()

allFiles = weakref.WeakValueDictionary()

def getStateFile(fn, defaults={}, deleteEmptyFiles=None) -> SharedStateFile:
    with stateFileLock:
        if fn in allFiles:
            s = allFiles[fn]
        else:
            s = SharedStateFile(fn)

        s.setupDefaults(defaults)
        if not (deleteEmptyFiles is None):
            s.noFileForEmpty = deleteEmptyFiles
    return s


def loadAllStateFiles(f):
    """For every yaml file, load it as a statefile named after the relative path to f,
        Also checking recovery dirs for files that never made it,
        return that dict.

        if f is /foo/bar, foo/bar/test.yaml  becomes '/test.yaml' in the output dict.

    """
    d = {}
    loadRecursiveFrom(f, d)
    return d


def loadRecursiveFrom(f, d, remapToDirForSave=None):
    remapToDirForSave = remapToDirForSave or f
    if os.path.isdir(f):
        for root, dirs, files in os.walk(f):
            relroot = root[len(f):]
            if relroot and not relroot.startswith("/"):
                relroot = '/'+relroot
            for i in files:
                if i.endswith(".yaml"):
                    x = '???????????????????'
                    try:
                        x = relroot+"/"+i[:-5]

                        # So we need to be able to load files from the recovery dir
                        # that don't exist in the real filesystem yet, but still when we save
                        # things we need to save them back to the real FS
                        fn = os.path.join(root, i)
                        fn = os.path.join(remapToDirForSave,
                                          os.path.relpath(fn, f))
                        data = getStateFile(fn)
                        data.noFileForEmpty = True
                        d[x] = data
                    except:
                        from . import messagebus
                        messagebus.post_message(
                            "/system/notifications/errors", "Failed to load data file"+x)
