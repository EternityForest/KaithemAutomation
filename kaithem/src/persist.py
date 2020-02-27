#Copyright Daniel Dunn 2013. 2015
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

from scullery.persist import *
from scullery.messagebus import subscribe,postMessage
from . import registry

import weakref,threading


dirty = weakref.WeakValueDictionary()

stateFileLock = threading.RLock()

allFiles = weakref.WeakValueDictionary()


def getStateFile(fn,defaults={},legacy={}):
    with stateFileLock:
        if fn in allFiles:
            s= allFiles[fn]
        else:
            s = SharedStateFile(fn)
    
        s.setupDefaults(defaults,legacy)
    return s

class SharedStateFile():
    def __init__(self,filename):
        if os.path.exists(filename):
            try:
                self.data = load(filename)
            except:
                self.data = {}
                postMessage("/system/notifications/errors",filename+"\n"+traceback.format_exc())
        else:
            self.data = {}
        self.filename=filename
        self.legacy_registry_key_mappings={}
        self.lock=threading.RLock()
        allFiles[filename]=self
    
    def setupDefaults(self,defaults={}, legacy_registry_key_mappings={}):
        self.legacy_registry_key_mappings.update(legacy_registry_key_mappings)
        for i in legacy_registry_key_mappings:
            km = legacy_registry_key_mappings[i]
            if not km in self.data:
                self.data[km] = registry.get(i,defaults[i])
        
        for i in defaults:
            if not i in self.data:
                self.data[i]=defaults[i]

        subscribe("/system/save", self.save)


    def get(self,key, default=None):
        with self.lock:
            return self.data.get(key, default)
    
    def set(self,key:str,value):
        with self.lock:
            json.dumps(value)
            if not isinstance(key,str):
                raise RuntimeError("Key must be str")
            self.data[key] = value

            if key in self.legacy_registry_key_mappings:
                registry.delete(self.legacy_registry_key_mappings[key])
            dirty[self.filename]=self


    def delete(self,key):
        with self.lock:
            try:
                del[self.data[key]]
            except KeyError:
                pass
            dirty[self.filename]=self

    def save(self):
        with self.lock:
            save(self.data, self.filename)
            try:
                del dirty[self.filename]
            except:
                pass



