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

    Flat will not contain any heirarchydicts.

    Basially all this is is a helper to make it faster to search the heirarchy in a dict and that's about it.

    To navigate it heirarchially, look in the obj.root. It will be a dict. all the contents will either be values
    aka resource dicts or heirarchydict instances to represent folders.

    Each dict.flat has all the directory contents, but subdirectories are represented by the directory resource,
    And you call getDir to get the HeirarchyDict that corresponds to that directory.

    For example, a contains directory b which has resource c.

    You iterate a and see a resource with type directory called b. you call a.getDir("b") and get b. That one has the resource c.
    """
    def __init__(self,d={}):
        #This stores subdirectory references
        self.root = {}
        #This stores actual items, but indexed by full path.
        self.flat = {}
        for i in sorted(d,key= lambda x:len(x)):
            print(i, self.root.keys())
            self[i]=d[i]

    def _put_item_in(self, key, val,realkey,subst=None):
        #Given key, which is a path elative to this dict,
        #/=And realkey, which is the full key, traverse the chain
        #Of heriarchy dicts until you get to the last one, and insert value there.

        #If val is a heirarchy
        key2 = util.split_escape(key,"/","\\")
        l =self.root
        m=self
        #Traverse all but last path component
        for i in key2[:-1]:
            if not i in l:
                return
            if isinstance(l[i], HeirarchyDict):
                l = l[i].root
                m=l[i]
            else:
                return


        #Do the actual insert.
        m.flat[realkey] = val
        if val.get('resource-type') == "directory":
            m.root[key2[-1]] = HeirarchyDict()
        else:
            m.root[key2[-1]] = val

    def __setitem__(self, key, val):
        #This will likely only ever be used at the base of the thing. So here the key is the same as the realkey
        key2 = util.split_escape(key,"/","\\")
        self.flat[key]=value
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

def in_folder(r,f):
    if not r.startswith(f):
        return False
    #Get the path as a list
    r = util.split_escape(r,'/','\\')
    #Get the path of the folder
    f = util.split_escape(f,'/','\\')
    #make sure the resource path is one longer than module
    if not len(r)==len(f)+1:
        return False
    return True

@util.lrucache(100)
def ls_folder(m,d):
    o = []
    x = ActiveModules[m]
    for i in x:
        if in_folder(i,d):
            o.append(i)
    return o

"this lock protects the activemodules thing. Any changes at all should go through this."
modulesLock = RLock()

#Define a place to keep the module private scope obects.
#Every module has a object of class object that is used so user code can share state between resources in
#a module
scopes ={}
