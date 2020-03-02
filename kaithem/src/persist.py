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
import urllib.parse

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

from . import config,util
from pwd import getpwuid,getpwnam
import os, stat



selected_user= config.config['run-as-user'] if util.getUser()=='root' else util.getUser()
recoveryDir= os.path.join("/dev/shm/SculleryRFRecovery",selected_user)
if os.path.exists("/dev/shm"):
    if not os.path.exists("/dev/shm/SculleryRFRecovery"):
        os.mkdir("/dev/shm/SculleryRFRecovery")
    if not os.path.exists(recoveryDir):
        os.mkdir(recoveryDir)
        #Nobody else van put stuff in there!!!
        os.chmod(recoveryDir, stat.S_IREAD|stat.S_IWRITE|stat.S_IEXEC)
        p=getpwnam(selected_user)
        os.chown(recoveryDir, p.pw_uid,p.pw_gid)
    else:
        if not getpwuid(os.stat(recoveryDir).st_uid).pw_name==selected_user:
            messagebus.postMessage("/system/notifications/errors","Hacking Detected? "+recoveryDir+" not owned by this user")
            recoveryDir=None
else:
    recoveryDir=None

class SharedStateFile():
    def __init__(self,filename):
        #Save all changes immediately to /dev/shm, for crash recovery.
        if not os.path.exists("/dev/shm") or not recoveryDir:
            self.recoveryFile=None
        else:
            self.recoveryFile = os.path.join(recoveryDir,urllib.parse.quote(filename,safe=""))

        if os.path.exists(filename):
            try:
                self.data = load(filename)
            except:
                self.data = {}
                postMessage("/system/notifications/errors",filename+"\n"+traceback.format_exc())
        else:
            self.data = {}
        try:
            if os.path.exists(self.recoveryFile):
                self.data = load(self.recoveryFile)
                dirty[filename]=self
        except:
            print(traceback.format_exc())
        self.filename=filename
        self.legacy_registry_key_mappings={}
        self.lock=threading.RLock()
        
        allFiles[filename]=self
    
    def setupDefaults(self,defaults={}, legacy_registry_key_mappings={}):
        self.legacy_registry_key_mappings.update(legacy_registry_key_mappings)
        for i in legacy_registry_key_mappings:
            km = legacy_registry_key_mappings[i]
            if not i in self.data:
                self.data[i] = registry.get(km,defaults[i])
        
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

            if self.recoveryFile:
                save(self.data,self.recoveryFile)


    def delete(self,key):
        with self.lock:
            try:
                del[self.data[key]]
            except KeyError:
                pass
            dirty[self.filename]=self
            if self.recoveryFile:
                save(self.data,self.recoveryFile)

    def save(self):
        with self.lock:
            save(self.data, self.filename)
            try:
                del dirty[self.filename]
            except:
                pass

            if self.recoveryFile and os.path.exists(self.recoveryFile):
                try:
                    os.remove(self.recoveryFile)
                except:
                    pass



