# -*- coding: utf-8 -*-
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


"""This file implements ChandlerScript, a DSL for piplines of events triggered by 
commands, called bindings.

One binding fits on one line:

event: action1 argument1 argument2 | action2 "A quoted argument" $variable

commands have a return value. Should one return None, the pipeline stops right there.

The pipeline also stops if an error is encountered.


Bindings live in a "Context Object". You can trigger an event in such an object with
ctx.event("event")

You can add an action by simply adding it as a function to the weak dict ctx.commands

Arguments are preprocessed before being supplied as positionals. However, the dict based 
variant supplies args as keywords, so be aware.

Anything beginning with $ is considered a variable, it is expanded based on variables
in the context.

Anything that looks like it could be a number is automatically converted to a float or
int, unless it is quoted.

The return value of the previous function is always available as $chain

This means functions can potentially recieve any python data type.
All functions should be strongly typed for this reason, and should use 
the typeguard library to ensure this.


commands can have a manifest property applied to the function.

It must look like:
{
    "description":"Foo",
    "args":[
        ["arg1Name","int",default,min,max],
        ["arg2Name",'str','Default'],
        ["arg3,"SomeOtherType", "SomeOtherData"]
    ]
}

This allows GUIs to auto-generate a UI for visually creating pipelines.

If there is an unrecognized type, it is treated as a string.
"""


import simpleeval

simpleeval.MAX_POWER = 1024

import weakref,threading, inspect



class NamespaceGetter():
    "Takes a dict and a prefix. Responds to attr requests with dict[prefix+.+key]"
    def __init__(self, d, prefix):
        self.__attr_prefix = prefix
        self.__attr_dict = d

    def __getattr__(self, k):
        return self.__attr_dict[self.__attr_prefix+'.'+k]


def DummyObject():
    "Operations with this succeed, but return other"
    def __add__(self,other):
        return other
    def __sub__(self,other):
        return other
    def __mul__(self,other):
        return other
    def __floordiv__(self,other):
        return other
    def __truediv__(self,other):
        return other
    def __mod__(self,other):
        return other
    def __pow__(self,other):
        return other
    def __and__(self,other):
        return other
    def __xor__(self,other):
        return other
    def __or__(self,other):
        return other
    def __int__(self):
        return 0
    def __neg__(self):
        return other
    def __str__(self):
        return ""

def paramDefault(p):
    if isinstance(p,int):
        return '='+str(p)

    if isinstance(p,float):
        return '='+str(p)

    if isinstance(p, str):
        return str

    if isinstance(p, bool):
        return 1 if p else 0

    if p==None:
        return ''



def getFunctionInfo(f):
    p = inspect.signature(f).parameters
    d = {
        'doc': inspect.getdoc(f),
        'args': [[i, paramDefault(p[i].default)] for i in p]
    }

    return d
import time,random

from .kaithemobj import kaithem

def lorem():
    "Returns a randomly selected quote"
    return kaithem.misc.lorem()

import math

def safesqrt(x):
    if x>10**30:
        raise RuntimeError("Too High of number for sqrt")
    return math.sqrt(x)

globalUsrFunctions={
    "millis": time.monotonic,
    "random": random.random,
    "randint": random.randint,
    "max": max,
    "min": min,
    "log":math.log,
    "log10":math.log10,
    "sin":math.sin,
    "cos":math.cos,
    "sqrt":safesqrt
}

globalConstants={
    'e': math.e,
    'pi': math.pi
}

def rval(x):
    "Returns the parameter x, and continues the action"
    return x

def passAction():
    "Does nothing and returns True, continuing the action"
    return True

def maybe(chance=50):
    "Return a True with some percent chance, else stop the action"
    return True if  random.random()*100>chance else None

def continueIf(v):
    "Continue if the first parameter is True"
    return True if v else None

predefinedcommands={
    'return':rval,
    'pass': passAction,
    'maybe':maybe,
    'continueIf': continueIf
}


lock = threading.Lock()

import datetime

from .scheduling import scheduler
class ScheduleTimer():
    def __init__(self,selector,context):
        import recur
        self.eventName=selector
        self.context=weakref.ref(context)

        selector = selector.strip()
        if not selector:
            return
        if not selector[0]=='@':
            raise ValueError("Invalid")

        self.selector = recur.getConstraint(selector[1:])
        nextruntime = self.selector.after(datetime.datetime.now(),True)
        self.nextruntime=dt_to_ts(nextruntime,self.selector.tz)
        self.next=scheduler.schedule(self.handler, self.nextruntime, False)

    def handler(self,*a,**k):
        nextruntime = self.selector.after(datetime.datetime.now(),True)
        ctx = self.context()

        #We don't want to reschedule if the context no longer exists
        if not ctx:
            return
        try:
            ctx.event(self.eventName)
            ctx.onTimerChange(self.eventName,self.nextruntime)

            self.nextruntime=dt_to_ts(nextruntime,self.selector.tz)
            self.next=scheduler.schedule(self.handler, self.nextruntime, False)
        finally:
            del ctx
    
    def stop(self):
        try:
            self.next.unregister()
        except:
            pass

import pytz
def dt_to_ts(dt,tz=None):
    "Given a datetime in tz, return unix timestamp"
    if tz:
        utc = pytz.timezone('UTC')
        return ((tz.localize(dt.replace(tzinfo=None)) - datetime.datetime(1970,1,1,tzinfo=utc)) / datetime.timedelta(seconds=1))

    else:
        #Local Time
        ts = time.time()
        offset = (datetime.datetime.fromtimestamp(ts) - datetime.datetime.utcfromtimestamp(ts)).total_seconds()
        return ((dt - datetime.datetime(1970,1,1)) / datetime.timedelta(seconds=1))-offset

class ScriptActionKeeper():
    "This typecheck wrapper is courtesy of two hours spent debugging at 2am, and my desire to avoid repeating that"
    def __init__(self):
        self.scriptcommands = weakref.WeakValueDictionary()
        
    def __setitem__(self,key,value):
        if not isinstance(key,str):
            raise TypeError("Keys must be string function names")
        if not callable(value):
            raise TypeError("Script commands must be callable")
        
        p= inspect.signature(value).parameters
        for i in p:
            if (not p[i].default==p[i].empty) and p[i].default and  not isinstance(p[i].default,(str,int,bool)):
                raise ValueError("All default values must be int, string, or bool, not "+str(p[i].default))


        self.scriptcommands[key]=value

    
    def __getitem__(self,key):
        return self.scriptcommands[key]

    def __contains__(self,key):
        return key in self.scriptcommands

    def get(self,k,d):
        return self.scriptcommands.get(k,d)

class ChandlerScriptContext():
    def __init__(self,parentContext=None, gil=None,functions={},variables=None, constants=None):
        self.pipelines = []
        self.eventListeners = {}
        self.variables = variables if not variables is None else {}
        self.commands= ScriptActionKeeper()
        self.children = {}
        self.constants = constants if (not (constants is None)) else {}
        #Used for detecting loops
        self.eventRecursionDepth = 0

        #Used to allow objects named foo.bar to be accessed as actual attributes of a foo obj,
        #Even though we use a flat list of vars.
        self.namespaces = {}


        self.timeEvents={}
        self.poller=None
        selfid = id(self)
     

        if parentContext:
            def delf(*a,**K):
                del parentContext.children[selfid]
            with lock:
                parentContext.children[id(self)]=weakref.ref(self,delf)

        self.parentContext = parentContext

        #Vars that have changed since last time we
        #Cleared the list. Used for telling the GUI
        # client about the current set of variables 
        self.changedVariables={}

        def setter(k,v):
            if not isinstance(k,str):
                raise RuntimeError("Var name must be string")
            if k in globalConstants or k in self.constants:
                raise NameError("Key "+k+" is a constant")
            self.setVar(k,v)

        self.setter = setter
        self.commands['set']=setter

        for i in predefinedcommands:
            self.commands[i]=predefinedcommands[i]

        def defaultVar(name,default):
            try:
                return self._nameLookup(name)
            except NameError:
                return default
            
        functions=functions.copy()
        functions.update(globalUsrFunctions)
        functions['defaultVar'] = defaultVar

        self.evaluator = simpleeval.SimpleEval(functions=functions,names=self._nameLookup)

        if not gil:
            self.gil = threading.RLock()
        else:
            self.gil = gil

    def onTimerChange(self, timer, nextRunTime):
        pass

    def _runCommand(self,c):
        a = self.commands.get(c[0],None)
        if not a:
            p=self.parentContext
            if p:
                a=p.commands.get(c[0],None)
        if a:
            try:
                return a(*[self.preprocessArgument(i) for i in c[1:]])
            except:
                raise RuntimeError("Error running chandler command: "+str(c)[:1024])
        else:
            raise ValueError("No such command: "+c)
    
    def event(self,evt,ctx=None):
        with self.gil:
            #Reset to 0 when the outer returns
            if self.eventRecursionDepth==0:
                isOuter = True
            else:
                isOuter=False
            try:
                if self.eventRecursionDepth>8:
                    raise RecursionError("Cannot nest more than 8 events")
                self.eventRecursionDepth+=1

                if evt in self.eventListeners:
                    for pipeline in self.eventListeners[evt]:
                        for command in pipeline:
                            x= self._runCommand(command)
                            if x==None:
                                break
                            self.variables["_"] = x
            finally:
                if isOuter:
                    self.eventRecursionDepth=0

    def preprocessArgument(self, a):
        if isinstance(a,str):
            if a.startswith("="):
                return self.eval(a[1:])
            #Looks like a number, it is a number
            try:
                a=float(a)
            except:
                pass
            
        return a

    def eval(self,a):
        return self.evaluator.eval(a)

    def addNamespace(self,name):
        """If name is foo, Makes variables named 'foo.bar' 
           accessible via an actual foo obj. Kind of a hack to allow a flat list of vars"""

        self.namespaces[name] = NamespaceGetter(self.variables, name)

    def _nameLookup(self,n):
        if not isinstance(n,str):
            n = n.id
        if n in self.variables:
            return self.variables[n]
        if n in globalConstants:
            return globalConstants[n]
        if n in self.constants:
            return self.constants[n]

        if n in self.namespaces:
            return self.namespaces[n]

        raise NameError("No such name: "+n)

    def setVar(self,k,v):
        with self.gil:
            self.variables[k]=v
            self.changedVariables[k]=v
            self.onVarSet(k,v)

    
    def onVarSet(self,k,v):
        pass

    
    def addBindings(self, b):
        """
            Take a list of bindings and add them to the context.
            A binding looks like:
            ['eventname',[['command','arg1'],['command2']]

            When events happen commands run till one returns None.
        """
        with self.gil:
            for i in b:
                if not i[0] in self.eventListeners:
                    self.eventListeners[i[0]]=[]
                self.eventListeners[i[0]].append(i[1])

    def startTimers(self):
        with self.gil:
            for i in self.eventListeners:
                if i and i.strip()[0]=='@':
                    if not i in self.timeEvents:
                        self.timeEvents[i]= ScheduleTimer(i,self)
                        self.onTimerChange(i,self.timeEvents[i].nextruntime)
                if i=="script.poll":
                    if not self.poller:
                        self.poller = scheduler.scheduleRepeating(self.poll, 1/24.0)
    def poll(self):
        self.event('script.poll')

    def clearBindings(self):
        with self.gil:
            self.eventListeners={}
            for i in self.timeEvents:
                self.timeEvents[i].stop()
            self.timeEvents = {}

            if self.poller:
                self.poller.unregister()
                self.poller=None

##### SELFTEST ##########



c = ChandlerScriptContext()

x=[]
desired=["Playing Baseball","A bat goes with a glove"]

def baseball():
    x.append("Playing Baseball")
    return True

def bat(a):
    x.append("A bat goes with a "+a)
    return None

def no(*a,**k):
    raise RuntimeError("This shouldn't run, the prev command returning None stops the pipe")


c.commands['baseball']=baseball
c.commands['bat']=bat
c.commands['no']=no
c.commands

b = [
    ['window', [ ['baseball'], ['bat', "='glove'"], ["no","this","shouldn't","run"] ]],
    ['test',[['set','foo','bar']]   ] 
]

c.addBindings(b)

#Bind event window to an action with three commands

#Top level list of b is a list of event name,commands pairs.
# 
# commands is a list of commands. Every action is a list where the first
# Is th name of the command, and the rest are arguments.

#Note that the first arg of bat stats with an equals sign
#so it gets evaluated, just like a LibreOffice Calc cell.

c.event('window')
c.event('test')

if not x==desired:
    raise RuntimeError("The ChandlerScript module isn't working as planned")
if not c.variables['foo']=='bar':
    raise RuntimeError("The ChandlerScript module isn't working as planned")

print(x)