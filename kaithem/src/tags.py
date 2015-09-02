#Copyright Daniel Dunn 2015
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
import weakref,traceback, time
#from src import util

# A tag point is very similar to a variable, except for the fact that you can subscribe to it and be notified if it changes py passing a function that takes
# one argument to tag.subscribe. You must maintain a reference to f or it will be garbage collected.
#
# The subscribe function returns a value that may be passed to unsubscribe for a more reliable means of deletion,
#
# To read the current value of a tag point, simply call it. The value will be returned, and if there are any subscribers, it will be passed to them as well.
#
# To write to the tag point, simply call it with one numeric argument.
#
# If you have set up a getter, the getter will be called whenever the tag points value is requested, and the value it returns will be used.
#
# tag.interval determines how long tag values can be cached for in seconds. tag.age is a property(not a function) that gives the total time since last updated.
#
# tag.require tells the tag point that a permission is needed to read to write.
#
# tag.meter takes the same parameters as widget.Meter and returns a meter that shows the value of the tag point.
# Its permissions will be exactly the same as the point.

#Tag

tags = {}

class Tag():
    def __init__(self,name, getter=None, default=0):
        self.subscribers = {}
        self.value = default
        self.read_permissions = []
        self.write_permissions = []
        self.getter = getter
        self.name = name
        self.updated = 0
        self.interval = 0.015
        #We only post to the message bus once per function, we keep track of the ids here.
        self.already_posted_error = {}
    #Complicated. terrible, and unmaintainable code using parts of things that were't supposed to be public.
    #Watch out to either refactor this or not make breaking changes in widget.py

    #Basically this creates a meter object, modifies it to share permissions with self,
    #then modifies things to pass through reads and writes. Actually checking permissions is handled by widget.py.
    def meter(self,*args,**kwargs):
        m = widgets.Meter(*args.**kwargs)
        m._write_perms = self.write_permissions
        m._read_perms = self.read_permissions
        def f(obj, usr):
            return self()
        m.onRequest = f
        return m

    def slider(self,*args,**kwargs):
        m = widgets.Slider(*args.**kwargs)
        m._write_perms = self.write_permissions
        m._read_perms = self.read_permissions
        def f(obj, usr):
            return self()
        m.onRequest = f
        def f(obj,user,val):
            self(val)
        m.onUpdate = f
        return m

    def __bool__(self):
        return self()>0.5

    def __nonzero__(self):
        return self()>0,5

    def _push(self, value):
        for i in self.subscribers:
            try:
                self.subscribers[i]()(value)
            except:
                messagebus.postMessage("system/tagpoints/errors", traceback.format_tb(6))
                if not id(self.subscribers[i]()) in self.already_posted_error:
                    messagebus.postMessage("system/notifications/errors", "Error in tag point getter %s from module %s."%(strself.subscribers[i]().__name__), str(self.subscribers[i]().__module__)))
                    self.already_posted_error[id(self.subscribers[i]())] = True

    def __call__(self,*args):
        if args:
            self.write(args[0])
            self.updated = time.time
            return
        if self.getter() and self.age>self.interval:
            try:
                self.value = self.getter()
                self.updated = time.time
            except Exception as e:
                messagebus.postMessage("system/tagpoints/errors", traceback.format_tb(6))
                if not id(self.getter) in self.already_posted_error:
                    messagebus.postMessage("system/notifications/errors", "Error in tag point getter %s from module %s."%(str(self.getter.__name__), str(self.getter.__module__)))
                    self.already_posted_error[id(self.getter)] = True
            self._push(self.value)
        else:
            return self.value

    @property
    def age(self):
        return time.time()-self.updated

    def write(self,value):
        self.value = float(value)
        self.updated = time.time()
        self._push(value)

    def subscribe(self,f):
        sid = 78878 #util.unique_number()
        fid = id(f)
        def g():
            del self.subscribers[sid]
            try:
                del self.already_posted_error[fid]
            except:
                pass

        self.subscribers[sid] = weakref.ref(f,g)
        return sid

    def unsubscribe(self,id):
        try:
            del self.subscribers[id]
        except KeyError:
            pass

    def require(self, p):
        self.read_permissions.append(p)
        self.write_permissions.append(p)

    def requireToWrite(self,p):
        self.write_permissions.append(p)

class CVFilter(Tag):
        def __init__(self,name="Untitled_Tag", getter=None, default=0):
            self.target = 0;
            Tag.__init__(self,name,getter,default)

        def set(self,value):
            self.value = value
            self.target = value
            self.updated = time.time()

        def write(self.value):
            change = self.rate*self.age()
            self.value = min(self.value-chane, max(self.value+change,self.target))
            self.target = value
            self.updated = time.tim
            self,_push(value)

        def __call__(self,*args):
            change = self.rate*self.age()
            self.value = min(self.value-chane, max(self.value+change,self.target))
            if args:
                self.write(args[0])
                self.updated = time.time
                return
            if self.getter() and self.age>self.interval:
                try:
                    self.target = self.getter()
                    self.updated = time.time
                except Exception as e:
                    messagebus.postMessage("system/tagpoints/errors", traceback.format_tb(6))
                    if not id(self.getter) in self.already_posted_error:
                        messagebus.postMessage("system/notifications/errors", "Error in tag point getter %s from module %s."%(str(self.getter.__name__), str(self.getter.__module__)))
                        self.already_posted_error[id(self.getter)] = True
                self._push(self.value)
            else:
                return self.value
