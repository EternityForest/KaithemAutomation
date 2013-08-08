#Copyright Daniel Black 2013
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

#NOTICE: A LOT OF LOCKS ARE USED IN THIS FILE. WHEN TWO LOCKS ARE USED, ALWAYS GET _event_list_lock LAST
#IF WE ALWAYS USE THE SAME ORDER THE CHANCE OF DEADLOCKS IS REDUCED.

import traceback,threading,sys,time,atexit
from . import workers, kaithemobj,messagebus,util,modules_state

from .config import config

#Use this lock whenever you acess _events or __EventReferences in any way.
#Most of the time it should be held by the event manager that continually iterates it.
#To update the _events, event execution must temporarily pause
_event_list_lock = threading.Lock() 
_events = []

#Let us now have a way to get at active event objects by means of their origin resource and module.
__EventReferences = {}

def getEventErrors(module,event):
    with _event_list_lock:
            return __EventReferences[module,event].errors

def getEventLastRan(module,event):
    with _event_list_lock:
            return __EventReferences[module,event].lastexecuted
        
def countEvents():
    #Why bother with the lock. The event count is not critical at all.
    return len(_events)

def STOP():
    global run
    run = False
    


#In a background thread, we use the worker pool to check all threads

run = True
#Acquire a lock on the list of _events(Because we can't really iterate safely without it)
#And put the check() fuction of each event object into the thread pool
def __manager():
    temp = 0;
    framedelay = 1.0/config['max-frame-rate']
    mindelay = config['delay-between-frames']
    global averageFramesPerSecond
    averageFramesPerSecond = 0
    #Basically loops for the lief of the app
    while run:
        #Get the time at the start of the loop
        temp = time.time()
        with _event_list_lock:
            for i in _events:
                workers.do(i.check)
                
            #Don't spew another round of events until the last one finishes so we don't fill up the queue
            e = threading.Event()
            def f():
                e.set()
            workers.do(f)
            #On the of chance something odd happens, let's not wait forever.
            e.wait(15)
            
        #Limit the polling cycles per second to avoid CPU hogging
        #Subtract the time the loop took from the delay
        #Allow config to impose a minimum delay
        time.sleep(max(framedelay-(time.time()-temp),mindelay))
        #smoothing filter
        averageFramesPerSecond = (averageFramesPerSecond *0.98) +   ((1/(time.time()-temp)) *0.02)
            
#Start the manager thread as a daemon
#Kaithem has a system wide worker pool so we don't need to reinvent that
t = threading.Thread(target = __manager, name="EventPollingManager")
#This thread never really does anything, it just delegates to the worker threads, so I'm
#fine with leaving it as a daemon.
t.daemon = True
t.start()

def make_event_from_resource(module,resource):
    "Returns an event object when given a module and resource name pointing to an event resource."
    r = modules_state.ActiveModules[module][resource]
    
    if 'setup' in r:
        setupcode = r['setup']
    else:
        setupcode = "pass"
        
    if 'rate-limit' in r:
        ratelimit = r['rate-limit']
    else:
        ratelimit = 0
        
    if 'continual' in r:
        continual = r['continual']
    else:
        continual = False
        
    if 'priority' in r:
        priority = r['priority']
    else:
        priority = 1
        
    x = Event(r['trigger'],r['action'],make_eventscope(module),
              setup = setupcode,
              continual = continual,
              ratelimit=ratelimit,
              priority=priority)
    
    x.module = module
    x.resource =resource
    return x


def parseTrigger(when):
    """
    Parse a trigger expression into a tokeized form
    """
    output = []
    
    #Split on spaces, but take into account multipla spaces by ignoring empty strings.
    for i in when.strip().split(' '):
        if not i == '':
            output.append(i)
            
    #Take into account normal python expression triggers and return a similar format
    if output[0].startswith('!'):
        return output
    else:
        return(['!edgetrigger',when])
    
        

#Factory function that examines the type of trigger and chooses a class to handle it.
def Event(when,do,scope,continual=False,ratelimit=0,setup = None,priority=2):
    trigger = parseTrigger(when)
    
    if trigger[0] == '!onmsg':
        return MessageEvent(when,do,scope,continual,ratelimit,setup,priority)
    
    elif trigger[0] == '!onchange':
        return ChangedEvalEvent(when,do,scope,continual,ratelimit,setup,priority)
    
    elif trigger[0] == '!edgetrigger':
        return PolledEvalEvent(when,do,scope,continual,ratelimit,setup,priority)


#A brief rundown on how these classes work. You have the BaseEvent, which handles registering and unregistering
#From polling lists, exeptions, and locking.

#Derived classes must do three things:
#Set self.polled to True if this event needs polling, or False if it is not(interrups, callbacks,etc)
#Define a _check() function that does polling and calls _on_trigger() if the event condition is true
#Do something with the setup variable if applicable
#define a _do_action() method that actually carries out the appropriate action
#call the init of the base class properly.

#The BaseEvent wraps the _check function in such a way that only one event will be polled at a time
#And errors in _check will be logged.

class BaseEvent():
    """Base Class represeting one event.
    scope must be a dict representing the scope in which both the trigger and action will be executed.
    When the trigger goes from fase to true, the action will occur.
    
    setupr,when and do are some representation of an action, the specifics of which are defined by derived classes.
    optional params:
    ratelimit: Do not do the action more often than every X seconds
    continual: Execute as often as possible while condition remains true
    
    """
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = None,priority = 2):
        #Copy in the data from args
        self.scope = scope
        self._prevstate = False
        self.ratelimit = ratelimit
        self.continual = continual
        self.countdown = 0
        self.priority = priority
        self.runTimes = []
        
        #Tese are only used for debug messages, but still someone should set them after they make the object
        self.module = "UNKNOWN"
        self.resource = "UNKNOWN"

        #This lock makes sure that only one copy of the event executes at once.
        self.lock = threading.Lock()
        
        #This keeps track of the last time the event was triggered  so we can rate limit
        self.lastexecuted = 0
        
        #A place to put errors
        self.errors = []
            
    def _on_trigger(self):
        #This function gets called when whatever the event's trigger condition is.
        #it provides common stuff to all trigger types like logging and rate limiting
        
        #Check the current time minus the last time against the rate limit
        #Don't execute more often than ratelimit

        if (time.time() -self.lastexecuted >self.ratelimit):
            #Set the varible so we know when the last time the body actually ran
            self.lastexecuted = time.time()
            try:
                #Action could be any number of things, so this method mut be implemented by
                #A derived class or inherited from a mixin.
                self._do_action()
            except Exception as e:
                self._handle_exception(e)

    def _handle_exception(self, e):
            
            tb = traceback.format_exc()
            #When an error happens, log it and save the time
            #Note that we are logging to the compiled event object
            self.errors.append([time.strftime(config['time-format']),tb]) 
            #Keep only the most recent errors
            self.errors = self.errors[-(config['errors-to-keep']):] 
            #The mesagebus is largely untested and we don't want to kill the thread.
            try:
                messagebus.postMessage('system/errors/events/'+
                                       self.module+'/'+
                                       self.resource,str(tb))
            except Exception as e:
                print (e)
            
            #If this is the first error since th module was last saved raise a notification
            if len(self.errors)==1:
                messagebus.postMessage('/system/notifications',"Event "+self.resource+" of module "+self.module+                " may need attention")
    
    def register(self):
        #Some events are really just containers for a callback, so there is no need to poll them
        if self.polled:
            if self not in _events:
                _events.append(self)
                
    def unregister(self):
        if self in _events:
            _events.remove(self)
    
    def check(self):
        #This is the function that the polling system calls to poll the event.
        #It calls a _check() function which must be defined by a subclass.
        
        #This is how we handle priority for now. The passing things between threads
        #Is what really takes time polling so the few instructions extra should be well worth it
        #Basically a countdon timer in frames that polls at zero and resets (P0 is as fast as possible)
        with self.lock:
            if self.countdown == 0:
                self.countdown = self.priority
            else:
                self.countdown -= 1
                return
            
            try:
                self._check()
            except Exception as e:
                self._handle_exception(e)

class CompileCodeStringsMixin():
    "This mixin lets a class take strings of code for its setup and action"
    def _init_setup_and_action(self,setup,action):
        #Compile the action and run the initializer
        self.action = compile(action,"<action>","exec")
        if setup == None:
            setup = "pass"
        initializer = compile(setup,"<setup>","exec")
        exec(initializer,self.scope,self.scope)
    
    def _do_action(self):
        exec(self.action,self.scope,self.scope)

class DirectFunctionsMixin():
        def _init_setup_and_action(self,setup,action):
            self._do_action = action

class MessageEvent(BaseEvent,CompileCodeStringsMixin):
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):
        
        #This event type is not polled. Note that it doesn't even have a check() method.
        self.polled = False
        def action_wrapper(topic,message):
            #Since we aren't under the BaseEvent.check() lock, we need to get it ourselves.
            with self.lock:
                #setup environment
                self.scope['__topic'] = topic
                self.scope['__message'] = message
                #We delegate the actual execution ofthe body to the on_trigger
                self._on_trigger()
            
        #When the object is deleted so will this reference and the message bus's auto unsubscribe will handle it
        self.action_wrapper_because_we_need_to_keep_a_reference = action_wrapper
        
        #Handle whatever stupid whitespace someone puts in
        #What this does is to eliminate leading whitespace, split on first space,
        #Then get rid of any extra spaces in between the command and argument.
        t = when.strip().split(' ',1)[1].strip()
        #Subscribe our new function to the topic we want
        messagebus.subscribe(t,action_wrapper)
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self._init_setup_and_action(setup,do)
        
class ChangedEvalEvent(BaseEvent,CompileCodeStringsMixin):      
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):
                #If the user tries to use the !onchanged trigger expression,
        #what we do is to make a function that does the actual checking and always returns false
        #This means it will be called every frame but the usual trigger method(which is edge triggered)
        #Is bypassed. Instead, we directly call self._on_trigger and return false
        
        #Handle whatever stupid whitespace someone puts in
        #What this does is to eliminate leading whitespace, split on first space,
        #Then get rid of any extra spaces in between the command and argument.
        f = when.strip().split(' ',1)[1].strip()
        
        #Compile the expression that will be checked for changes
        self.f= compile(f,"<inputvalue>","eval")
        
        #This flag indicates that we have never had a reading
        self.at_least_one_reading = False
        self.polled = True
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self._init_setup_and_action(setup,do)
        
    def _check(self):
        #Evaluate the function that gives us the values we are looking for changes in
        self.latest = eval(self.f,self.scope,self.scope)
        #If this is the very first reading,
        if not self.at_least_one_reading:
            #make a fake previous reading the same as the last one
            self.old = self.latest
            self.at_least_one_reading = True
        
        #If the most recent reading differs from the last one
        if not self.old==self.latest:
            #Update the value of the last reading for next time
            self.old = self.latest
            #Set it up so user code will have access to the value
            self.scope['__value'] = self.latest
            self._on_trigger()

class PolledEvalEvent(BaseEvent,CompileCodeStringsMixin):
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):
        self.polled = True
        #Compile the trigger
        self.trigger = compile(when,"<trigger>","eval")
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self._init_setup_and_action(setup,do)
    def _check(self):
        """Check if the trigger is true and if so do the action."""            
        #Eval the condition in the local event scope
        if eval(self.trigger,self.scope,self.scope):
            #Only execute once on false to true change unless continual was set
            if (self.continual or self._prevstate == False):
                self._prevstate = True
                self._on_trigger()
        else:
            #The eval was false, so the previous state was False
            self._prevstate = False

class PolledInternalSystemEvent(BaseEvent,DirectFunctionsMixin):
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):
        self.polled = True
        #Compile the trigger
        self.trigger = when
        self._init_setup_and_action(setup,do)
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        
    def _check(self):
        """Check if the trigger is true and if so do the action."""            
        #Eval the condition in the local event scope
        if self.trigger():
            #Only execute once on false to true change unless continual was set
            if (self.continual or self._prevstate == False):
                self._prevstate = True
                self._on_trigger()
        else:
            #The eval was false, so the previous state was False
            self._prevstate = False

#BORING BOOKEEPING BELOW


#Delete a event from the cache by module and resource
def removeOneEvent(module,resource):
    with _event_list_lock:
        if (module,resource) in __EventReferences:
            __EventReferences[module,resource].unregister()
            del __EventReferences[module,resource]
                    
#Delete all _events in a module from the cache
def removeModuleEvents(module):
    with _event_list_lock:
        for i in __EventReferences.copy():
            if i[0] == module:
                #delete both the event and the reference to it
                __EventReferences[i].unregister()
                del __EventReferences[i]
        
#Every event has it's own local scope that it uses, this creates the dict to represent it
def make_eventscope(module):
    with modules_state.modulesLock:
       return {'module':modules_state.scopes[module],'kaithem':kaithemobj.kaithem}

#This piece of code will update the actual event object based on the event resource definition in the module
#Also can add a new event
def updateOneEvent(resource,module):
    #This is one of those places that uses two different locks(!)
    with modules_state.modulesLock:
        
        x = make_event_from_resource(module,resource)
        #Here is the other lock(!)
        with _event_list_lock: #Make sure nobody is iterating the eventlist
            if (module,resource) in __EventReferences:
                __EventReferences[module,resource].unregister()
                
            #Add new event
            x.register()
            #Update index
            __EventReferences[module,resource] = x

#look in the modules and compile all the event code
def getEventsFromModules():
    global _events
    with modules_state.modulesLock:
        with _event_list_lock:
            #Set _events to an empty list we can build on
            _events = []
            for i in modules_state.ActiveModules:
                #now we loop over all the resources of the module to see which ones are _events 
                for m in modules_state.ActiveModules[i]:
                    j=modules_state.ActiveModules[i][m]
                    if j['resource-type']=='event':
                        #For every resource that is an event, we make an event object based o
                        x = make_event_from_resource(i,m)
                        x.register()
                        _events.append(x)
                        #Now we update the references
                        __EventReferences[i,m] = x
