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
    "kwargs":{
        "arg": ["int",default,min,max],
        "arg2": ['str','Default'],
        "arg3:  ["SomeOtherType", "SomeOtherData"]
    }
}

This allows GUIs to auto-generate a UI for visually creating pipelines.

If there is an unrecognized type, it is treated as a string.
"""


import simpleeval

simpleeval.MAX_POWER = 1024



import weakref,threading
def split_cmdline(s, separator, escape="\\",preserve_escapes=False):
    current_token = ""
    tokens = []
    literal = False
    q=False

    for i in s:
        if literal:
            current_token += i
            literal = False

        elif q:
            #I is the thing we quoted with
            if i==q:
                q=False
    
        elif i == separator:
            try:
                if not '.' in current_token:
                    current_token= int(current_token)
                else:
                    current_token=float(current_token)
            except:
                pass
            tokens+= [current_token]
            current_token = ""

        elif i == escape:
            literal = True
            if preserve_escapes:
                current_token += i

        elif i in '\'"':
            q=i

        else:
            current_token +=i

    if current_token:
        return tokens+[current_token]
    else:
        return tokens


import time,random
usrFunctions={
    "millis": time.monotonic,
    "random": random.random,
    "randint": random.randint,
}

class ChandlerScriptContext():
    def __init__(self,parentContext=None, gil=None):
        self.pipelines = []
        self.eventListeners = {}
        self.variables = {}
        self.actions= weakref.WeakValueDictionary()
        self.evaluator = simpleeval.SimpleEval(functions=usrFunctions)

        if not gil:
            self.gil = threading.RLock()
        else:
            gil = gil


    def runCommand(self,c):
        a = self.actions.get(c[0],None)
        if a:
            print(c)
            return a(*c[1:])
    
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
        if a.startswith("="):
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
            self.changedVariables[k]=n

    def parseBinding(self,b):
        """
        Parse a binding like foo: bar "baz" | foo2
        into:
        
        (foo (
                (bar baz)
                (foo2)
              )
        )
        Meaning:
            When the event foo happens, run this pipeline of
            actions until one does not return a value.

            The first action is bar, with the string baz as an arg,
            the second is foo2 with no args.

        """
        trigger, pipe = split_cmdline(b,":")
        pipe = split_cmdline(pipe,"|")

        p = []
        for i in pipe:
            z = split_cmdline(i, ' ')
            p.append([i.strip() for i in z if i.strip()])

        #p will be a list of dicts, each representing an action or expression
        return trigger.strip(), p 
    
    
    def parseCommandBindings(self,cmd):
        for i in cmd.split("\n"):
            if not i:
                continue
            x = self.parseBinding(i)
            

            if not x[0] in self.eventListeners:
                self.eventListeners[x[0]]=[]
            self.eventListeners[x[0]].append(x[1])
    
    def addBindings(self, b):
        for i in b:
            if not x[0] in self.eventListeners:
                self.eventListeners[x[0]]=[]
            self.eventListeners[x[0]].append(x[1])

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
#Note that the first arg of bat stats with an equals sign
#so it gets evaluated
c.parseCommandBindings("""window: baseball | bat "= 'glove' " | no running this one """)
c.event('window')

if not x==desired:
    raise RuntimeError("The ChandlerScript module isn't working as planned")

print(x)