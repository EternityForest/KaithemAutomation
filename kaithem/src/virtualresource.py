#Copyright Daniel Dunn 2017
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

import threading,weakref


class VirtualResourceReference(weakref.ref):
    def __getitem__(self,name):
        if name == "resource-type":
            return "virtual-resource"
        else:
            raise KeyError(name)

class VirtualResource(object):
    def __init__(self):
        self.__interfaces = []
        self.__lock=threading.Lock()
        self.replacement =None

    def __repr__(self):
        return "<VirtualResource at "+str(id(self))+" of class"+str(self.__class__)+">"

    def __html_repr__(self):
        return "VirtualResource at "+str(id(self))+" of class"+str(self.__class__.__name__)+""

    def interface(self):
        if not self.replacement:

            with self.__lock:
                x= VirtualResourceInterface(self)
                self.__interfaces.append(weakref.ref(x))
                #Make a list of all interfaces that need removing
                torm = []
                for i in self.__interfaces:
                    if not i():
                        torm.append(i)

                #remove them
                for i in torm:
                    self.__interfaces.remove(i)
                return(x)
        else:
            return self.replacement.interface(self)

    def handoff(self,other):
        with self.__lock:
            #Someone thinks this is the current one and wants to replace it,
            #But actually this has already been replaced and some object is now current.
            #So that object is the one we actually want to replace
            x = self.replacement
            if x and (not x is other):
                return x.handoff(self)

            #Change all interfaces to this object to point to the new object.
            for i in self.__interfaces:
                try:
                    i()._resource_object = other
                except:
                    pass

            self.replacement = other

class VirtualResourceInterface(object):
    def __init__(self,resource):
        self._resource_object = resource
    def __repr__(self):
        return self._resource_object.__repr__()
    def __html_repr__(self):
        return self._resource_object.__html_repr__()
    def __call__(self,*args,**kwargs):
        return self._resource_object.__repr__()
    @property
    def __doc__(self):
        return self._resource_object.__doc__

    def __getattr__(self,attr):
        return getattr(self._resource_object, attr)

    def __setattr__(self,k,v):
        if not k == "_resource_object":
            setattr(self._resource_object, k,v)
        else:
            object.__setattr__(self,k,v)
