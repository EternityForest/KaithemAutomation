#Copyright Daniel Dunn 2013
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

#This file is just for keeping track of state info that would otherwise cause circular issues.

from threading import RLock
from src import util


class BaseHeirarchyDict(dict):
    def __init__(self):
        self.flat = {}

    def __setitem__(self, key, val):
        self.flat[key]=HeirarchyDict(val)

    def copy(self):
        return self.flat.copy()
    def keys(self):
        return self.flat.keys()
    def items(self):
        return self.flat.items()
    def values(self):
        return self.flat.values()

    def __delitem__(self,key):
        del self.flat[key]


    def __iter__(self,):
        return self.flat.__iter__()

    def __contains__(self, key):
        return self.flat.__contains__(key)

    def __getitem__(self,key):
        return self.flat[key]

class HeirarchyDict(dict):
    """
    Dict that is designed for heirarchial keys of the form x/y/z, supporting \ escapes.
    Values must be dicts that have a resource type item.
    If you delete a directory, things that directory contains won't be deleted.

    Flat will not contain any dicts unless you explicitly put them there.
    It also won't automatically make enclosing dicts.

    Basially all this is is a helper to make it faster to search the heirarchy in a dict and that's about it.

    However, it will disallow you from putting things into a nonexistant directory.

    To navigate it heirarchially, look in the obj.root. It will be a dict. all the contents will either be values
    aka resource dicts or heirarchydict instances to represent folders.
    """
    def __init__(self,d={}):
        self.root = {}
        self.flat = {}
        for i in sorted(d,key= lambda x:len(x)):
            self[i]=d[i]

    def _put_item_in(self, key, val,realkey):
        self.flat[realkey]=val
        key2 = util.split_escape(key,"/","\\")
        l =self.root
        m=self
        for i in key2[:-1]:
            if not i in l:
                return
            if isinstance(l[i], HeirarchyDict):
                l = l[i].root
                m=l[i]
            else:
                return
        if val.get('resource-type') == "directory":
            m._put_item_in(key2[-1],HeirarchyDict(),realkey)
        else:
            m._put_item_in(key2[-1],val,realkey)

    def __setitem__(self, key, val):
        self.flat[key]=val
        key2 = util.split_escape(key,"/","\\")
        l =self.root
        m=self
        for i in key2[:-1]:
            if not i in l:
                return
            if isinstance(l[i], HeirarchyDict):
                l = l[i].root
                m=l[i]
            else:
                return

        if val.get('resource-type') == "directory":
            m._put_item_in(key2[-1],HeirarchyDict(),key)
        else:
            m._put_item_in(key2[-1],val,key)

    def getDir(self,key):
        if isinstance(key,(list,tuple)):
            key2=key
        else:
            key2 = util.split_escape(key,"/","\\")
        print (key2)
        l =self.root
        for i in key2:
            l = l[i].root
        return l
    def copy(self):
        return self.flat.copy()
    def keys(self):
        return self.flat.keys()
    def items(self):
        return self.flat.items()
    def values(self):
        return self.flat.values()

    def __delitem__(self,key):
        del self.flat[key]
        key = split_escape(key,"/","\\")
        l =self.root

        for i in key[:-1]:
            if i in l:
                l = l[i].root
            else:
                return

        del l[key[-1]]

    def __iter__(self,):
        return self.flat.__iter__()

    def __contains__(self, key):
        return self.flat.__contains__(key)

    def __getitem__(self,key):
        return self.flat[key]

#Lets just store the entire list of modules as a huge dict for now at least
ActiveModules = {}



"this lock protects the activemodules thing. Any changes at all should go through this."
modulesLock = RLock()

#Define a place to keep the module private scope obects.
#Every module has a object of class object that is used so user code can share state between resources in
#a module
scopes ={}
