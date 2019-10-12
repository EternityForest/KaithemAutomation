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
actions, called bindings.

One binding fits on one line:

event: action1 argument1 argument2 | action2 "A quoted argument" $variable

Actions have a return value. Should one return None, the pipeline stops right there.

The pipeline also stops if an error is encountered.


Bindings live in a "Context Object". You can trigger an event in such an object with
ctx.event("event")

You can add an action by simply adding it as a function to the weak dict ctx.actions

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


Actions can have a manifest property applied to the function.

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

import weakref,threading


import time,random
usrFunctions={
    "millis": time.monotonic,
    "random": random.random,
    "randint": random.randint,
}

predefinedActions={
    'return':lambda x:x
}

class ChandlerScriptContext():
    def __init__(self,parentContext=None, gil=None,functions={}):
        self.pipelines = []
        self.eventListeners = {}
        self.variables = {}
        self.actions= weakref.WeakValueDictionary()

        #Vars that have changed since last time we
        #Cleared the list. Used for telling the GUI
        # client about the current set of variables 
        self.changedVariables={}

        def setter(k,v):
            if not isinstance(k,str):
                raise RuntimeError("Var name must be string")
            self.setVar(k,v)

        self.setter = setter
        self.actions['set']=setter

        for i in predefinedActions:
            self.actions[i]=predefinedActions[i]
        functions=functions.copy()
        functions.update(usrFunctions)
        
        self.evaluator = simpleeval.SimpleEval(functions=usrFunctions)

        if not gil:
            self.gil = threading.RLock()
        else:
            gil = gil


    def runCommand(self,c):
        a = self.actions.get(c[0],None)
        if a:
            return a(*[self.preprocessArgument(i) for i in c[1:]])
    
    def event(self,evt,ctx=None):
        with self.gil:
            if evt in self.eventListeners:
                for pipeline in self.eventListeners[evt]:
                    for command in pipeline:
                        x= self.runCommand(command)
                        if x==None:
                            break
                        self.variables["_"] = x

    def preprocessArgument(self, a):
        if isinstance(a,str) and a.startswith("="):
            return self.eval(a[1:])
        return a

    def eval(self,a):
        return self.evaluator.eval(a)

    
    def _nameLookup(self,n):
        if n in self.variables:
            return self.variables[n]

    def setVar(self,k,v):
        with self.gil:
            self.variables[k]=v
            self.changedVariables[k]=v

    
    def addBindings(self, b):
        """
            Take a list of bindings and add them to the context.
            A binding looks like:
            ['eventname',[['command','arg1'],['command2']]

            When events happen commands run till one returns None.
        """
        for i in b:
            if not i[0] in self.eventListeners:
                self.eventListeners[i[0]]=[]
            self.eventListeners[i[0]].append(i[1])

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


c.actions['baseball']=baseball
c.actions['bat']=bat
c.actions['no']=no
c.actions

b = [
    ['window', [ ['baseball'], ['bat', "='glove'"], ["no","this","shouldn't","run"] ]],
    ['test',[['set','foo','bar']]   ] 
]

c.addBindings(b)

#Bind event window to an action with three commands

#Top level list of b is a list of event name,actions pairs.
# 
# Actions is a list of actions. Every action is a list where the first
# Is th name of the command, and the rest are arguments.

#Note that the first arg of bat stats with an equals sign
#so it gets evaluated, just like a LibreOffice Calc cell.

c.event('window')
c.event('test')

if not x==desired:
    print(x)
    raise RuntimeError("The ChandlerScript module isn't working as planned")
if not c.variables['foo']=='bar':
    raise RuntimeError("The ChandlerScript module isn't working as planned")

print(x)