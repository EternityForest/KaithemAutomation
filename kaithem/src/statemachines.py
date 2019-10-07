#Copyright Daniel Dunn 2016
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



import time, weakref,types,threading
from typeguard import typechecked
from typing import Union, Callable


#Lets keep dependancies on things within kaithem to a minimum, as eventually this might be spun off to a standalone thing
from . import scheduling,virtualresource,unitsofmeasure,workers,util

#
# StateMachine API
#
# sm= StateMachine()
#
# Create an object representing one nondeterministic finite automaton
#
# sm.addState("stateName", [enter, exit])
#
# Add a state to the machine. Enter and exit may be functions to be called when the state enters or leaves. If the state
# already exists, it will be replaced
#
# sm.addRule("startState", "ExampleEvent", "destinationState")
#
# Add a rule to handle what should happen if event occurs while the machine is in state.
# The third parameter representing the destination state may also be a function. The function must take one parameter, the machine itself,
# and return either None for no Transiton or a string representing the new state. This lets you implement conditions and branchingself.
#
# sm.addTimer("state",60, "newstate")
#
# Add a timer to state that will cause it to Transiton to newstate after 60 seconds. You can set the time to None to delete any existing timers,
# and you can use a function for the destination state just like for a normal rule. States may only have one timerself.
#


illegalStateNameChars="~!@#$%^&*()-=+`<>?,./;':\"\\[]{}\n\r\t "


def unboundProxy(self,f):
    def f2(*args,**kwargs):
        f(*args,**kwargs)
    return f2

def makechecker(ref):
    def timer_check():
        m=ref()
        if m:
            m.checkTimer()
    return timer_check

def makepollchecker(ref):
    def timer_check():
        m=ref()
        if m:
            m.check()
    return timer_check


def runSubscriber(f,state):
    f(state)

class UpdateControl():
    pass


def startPollerThread(sm):
    sm = util.universal_weakref(sm)
    def f():
        while 1:
            x = sm()
            if not x:
                return
            if x.replacement:
                return
            x.poll()
        

class StateMachine(virtualresource.VirtualResource):
    def __init__(self,start="start",name="Untitled",description=""):
        self.states = {}
        self.state = start
        self.prevState = None
        self.enteredState = time.time()
        #Used to ensure that if one leaves and reenters a state just as a timer is firing it does not trigger anything.
        self._transiton_count = 0
        self.lock= threading.RLock()

        #Subscribers, as lists of function weakrefs indexed by what state entrance they are subscribed to to
        self.subscribers = {}
        self.description=description

        #Used for skipping ahead to quickly test timers and things like that.
        self.time_offset = 0

        #Controls what gets carried over during handoffs
        self.keepState = True
        self.keepSubscribers = True

        virtualresource.VirtualResource.__init__(self)

    def __call__(self,event):
        "Trigger an event, return the current state"
        self.event(event)
        return self.state

    def __repr__(self):
        return "<State machine at %d in state %s, entered %d ago>"%(id(self),self.state,time.time()-self.enteredState)

    def __html_repr__(self):
        return """<small>State machine object at %s<br></small>
            <b>State:</b> %s<br>
            <b>Entered</b> %s ago at %s<br>
            %s"""%(
        hex(id(self)),
        self.state,
        unitsofmeasure.formatTimeInterval(time.time()-self.enteredState,2),
        unitsofmeasure.strftime(self.enteredState),
        ('\n' if self.description else '')+self.description
        )

    def subscribe(self,f, state="__all__"):
        """
        Cause function f to be called when the machine enters the given state. If the state is __all__, causes
        f to be called whenever the state changes at all. Uses weak refs, so you must maintain a reference to f
        """
        with self.lock:
            #First clean up old subscribers. This is slow to do thi every time, but it should be infrequent.
            for i in self.subscribers:
                self.subscribers[i] = [ i for i in self.subscribers[state] if i() ]
            self.subscribers = {i:self.subscribers[i] for i in self.subscribers if self.subscribers[i]}


            if not state in self.subscribers:
                self.subscribers[state] = []
            self.subscribers[state].append(util.universal_weakref(f))

    @property
    def age(self):
        return time.time()-self.enteredState

    @property
    def stateage(self):
        with self.lock:
            return (self.state,time.time()-self.enteredState)

    def handoff(self,other):
        "pushes all subscribers to the new one"
        if other == self:
            return
        with self.lock:
            with other.lock:
                x = self.replacement
                if x and (not x is other):
                    return x.handoff(self)
                if other.keepSubscribers:
                    #export all the old subscribers
                    for i in self.subscribers:
                        #duplicate detection
                        if not i in other.subscribers:
                            other.subscribers[i]= []
                        other.subscribers[i].extend(self.subscribers[i])

                if other.keepState:
                    #Carry over the state and the time at which that state was entered.
                    other.state = self.state
                    other.prevState = self.prevState
                    other.enteredState = self.enteredState
                    other.time_offset = self.time_offset

                other.lock = self.lock

                virtualresource.VirtualResource.handoff(self,other)


    def checkTimer(self):
            with self.lock:
                if self.replacement:
                    self.replacement.checkTimer()
                    return

                if self.states[self.state].get('timer'):
                    if ((time.time()+self.time_offset)-self.enteredState) > self.states[self.state]['timer'][0]:

                        #Get the destination
                        x = self.states[self.state]['timer'][1]

                        #If it's a function, call it to get the actual destination.
                        if isinstance(x, str):
                            self._goto(x)
                        else:
                            x = x(self)
                            if x:
                                self._goto(x)
                    else:
                        self._configureTimer()

    def _configureTimer(self):
        "Sets up the timer. Needs to be called under lock"

        if hasattr(self,'schedulerobj'):
            self.schedulerobj.unregister()
            del self.schedulerobj

        #If for any reason we get here too early, let's just keep rescheduling
        if self.states[self.state].get('timer'):
            #If we haven't already passed the time of the timer
            if ((time.time()+self.time_offset)-self.enteredState)<self.states[self.state]['timer'][0]:
                f = makechecker(util.universal_weakref(self))
                self.schedulerobj = scheduling.scheduler.schedule(f, time.time()+0.08)
                self.schedulerobj.func_ref = f
            #If we have already passed that time, just do it now.
            #This is here for faster response when skipping ahead.
            else:
                workers.do(self.checkTimer)

    def seek(self, t, condition=None):
        """
        Seek ahead to a given position in the curren state's timeline, but only if the """
        with self.lock:
            if condition and (not condition==self.state):
                return
            pos = (time.time()-self.enteredState)
            self.time_offset = t-pos
            self._configureTimer()

    @typechecked
    def addState(self,name:str, rules = None, enter:Union[str,Callable,None]=None, exit:Union[str,Callable,None]=None):
        for i in illegalStateNameChars:
            if i in name:
                raise ValueError("Forbidden special character")
        with self.lock:
            self.states[name] = {"rules": rules or {}, 'enter':enter, 'exit':exit, 'conditions':[]}


    def setTimer(self,state:str, time:Union[float,int], dest:Union[str,Callable]):
        with self.lock:
            if dest:
                self.states[state]['timer'] = [time, dest]

    def removeState(self,name):
        with self.lock:
            del self.states[name]['rules'][start]

    @typechecked
    def addRule(self,start:str, event:Union[str,Callable], to:Union[str,Callable]):
        with self.lock:
            if isinstance(event, str):
                self.states[start]['rules'][event] = to
            elif callable(event):
                    self.states[start]['conditions'].append((event,to))
                    self._setupPolling()
              
    def delRule(self, start, event):
        with self.lock:
            if event in self.states[start]['rules']:
                del self.states[start]['rules'][event]
            elif event in self.states[start]['conditions']:
                del self.states[start]['rules'][event]
            else:
                raise KeyError("No such rule")


    def event(self,event):
        """Tell the machine that a specific event just occurred. If there is a matching Transiton rule for that event,
        then we do the current state's exit func, enter the new state, and do it's enter func"""
        with self.lock:
            if self.replacement:
                self.replacement.event(event)
                return self.state

            if not self.state in self.states:
                return self.state

            s = self.states[self.state]


            if event in s['rules']:
                x = s['rules'][event]
                #If the rule destination is a string, just use it. If it is not a string, then
                #It must be a function because those are the only two valid destination types.

                #If it's a function, call it to get the actual destination.
                if isinstance(x, str):
                    self._goto(x)
                else:
                    x = x(self)
                    if x:
                        self._goto(x)
            return self.event

    def check(self):
        "Check the function based condition rules"
        with self.lock:
            s = self.states.get(self.state,None)
            if s:
                #Check all the function rules, poll them all,
                #and should any happen to be true, we follow that rule
                #Like any other.
                for i in s['conditions']:
                    if i[0]():
                        self._goto(i[1])

    def jump(self, state, condition=None):
        self.goto(state, condition)

    def goto(self, state, condition=None):
        "Jump to a specified state. If condition is not None, only jump if it matches the current state else do nothing."
        with self.lock:
            if condition and not self.state == condition:
                return
            self._goto(state)

    def _setupPolling(self):
        "Start polling the function based events, if there are any to poll for"
        if hasattr(self,'pollingscheduledfunction'):
            self.pollingscheduledfunction.unregister()
            del self.pollingscheduledfunction


        if self.states[self.state].get('conditions'):
            self.pollingscheduledfunction = scheduling.scheduler.every(self.check, 1/24)


    def _goto(self, state):
        "Must be called under the lock"

        s = self.states[self.state]
        s2 = self.states[state]

        #Do the old state's exit function
        if s['exit']:
            s['exit']()

        self.prevState = self.state
        self.state=state
        #Record the time that we entered the new state
        self.enteredState = time.time()
        self._configureTimer()

        self.time_offset = 0

        if hasattr(self,'schedulerobj'):
            self.schedulerobj.unregister()
            del self.schedulerobj

        if self.states[self.state].get('timer'):
            f = makechecker(util.universal_weakref(self))
            self.schedulerobj = scheduling.scheduler.schedule(f, time.time()+self.states[self.state].get('timer')[0])
            self.schedulerobj.func_ref = f

        self._setupPolling()

        #Do the entrance function of the new state
        if s2['enter']:
            s2['enter']()



        #Handle the subscribers
        if state in self.subscribers:
            for i in self.subscribers[state]:
                x = i()
                if x:
                    runSubscriber(x,self.state)

        if "__all__" in self.subscribers:
            for i in self.subscribers["__all__"]:
                x = i()
                if x:
                    runSubscriber(x,self.state)

        #Increment the trans count. wrap at 2**64
        self._transiton_count = (self._transiton_count+1)%2**64
