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

#NOTICE: A LOT OF LOCKS ARE USED IN THIS FILE. WHEN TWO LOCKS ARE USED, ALWAYS GET __event_list_lock LAST
#IF WE ALWAYS USE THE SAME ORDER THE CHANCE OF DEADLOCKS IS REDUCED.



import threading,traceback,sys
import workers
import modules,threading,time
import kaithem,messagebus,util

#Use this lock whenever you acess __events or __EventReferences in any way.
#Most of the time it should be held by the event manager that continually iterates it.
#To update the __events, event execution must temporarily pause
__event_list_lock = threading.Lock() 

__events = []

#Let us now have a way to get at active event objects by means of their origin resource and module.
__EventReferences = {}

def getEventErrors(module,event):
    with __event_list_lock:
            return __EventReferences[module][event].errors

def getEventLastRan(module,event):
    with __event_list_lock:
            return __EventReferences[module][event].lastexecuted

#In a background thread, we use the worker pool to check all threads

run = True
#Acquire a lock on the list of __events(Because we can't really iterate safely without it)
#And put the check() fuction of each event object into the thread pool
def __manager():
    temp = 0;
    global averageFramesPerSecond
    averageFramesPerSecond = 0
    #Basically loops for the lief of the app
    while run:
        #Get the time at the start of the loop
        temp = time.time()
        #If by the time we get here the queue is still half full we have a problem so slow down and let other stuff work.
        if workers.waitingtasks() < 60:
            __event_list_lock.acquire()
            try:
                for i in __events:
                    workers.do(i.check)
            except:
                print("e")
            finally:
                __event_list_lock.release()
            #This should be user configurable
        #Limit the polling cycles per second to avoid CPU hogging
        time.sleep(0.01)
        #smoothing filter
        averageFramesPerSecond = (averageFramesPerSecond *0.98) +   ((1/(time.time()-temp)) *0.02) 
            
#Start the manager thread as a daemon
#Kaithem has a system wide worker pool so we don't need to reinvent that
t = threading.Thread(target = __manager)
t.daemon = True
t.start()


#Delete a event from the cache by module and resource
def removeOneEvent(module,resource):
    with __event_list_lock:
        if module in __EventReferences:
            if resource in __EventReferences[module]:
                if __EventReferences[module][resource] in __events:
                    #Remove old reference if there was one
                    __events.remove(__EventReferences[module][resource])
                    del __EventReferences[module][resource]
                    
#Delete all __events in a module from the cache
def removeModuleEvents(module):
    with __event_list_lock:
        #Handle the case in which the module has no events
        if module in __EventReferences:
            #Iterate over the event refereces for each module, look them up in the list, and get rid of them
            for i in __EventReferences[module]:
                if __EventReferences[module][i] in __events:
                    #Remove old reference if there was one
                    __events.remove(__EventReferences[module][i])
                    
            del __EventReferences[module]        
                
                
#Every event has it's own local scope that it uses, this creates the dict to represent it
def make__eventscope(module):
    with modules.modulesLock:
       return {'module':modules.scopes[module],'kaithem':kaithem.kaithem}

#This piece of code will update the actual event object based on the event resource definition in the module
#Also can add a new event
def updateOneEvent(resource,module):
    #This is one of those places that uses two different locks(!)
    with modules.modulesLock:
        #Get the event resource in question
        j = modules.ActiveModules[module][resource]

        if 'setup' in j:
            setupcode = j['setup']
        else:
           setupcode = "pass"

        #Make an event object
        x = Event(j['trigger'],j['action'],make__eventscope(module),setup = setupcode)
        #Somehow seems brittle to me.
        #What it does is to use the __EventReferences index to get at the old event object, 
        #remove it, add the new event, and update the index
        
        #Here is the other lock(!)
        with __event_list_lock: #Make sure nobody is iterating the eventlist
        
            #If there is already a dict at __eventreferences[module]
            if module in __EventReferences:
                #And if that dict contains the event we want to update
                if resource in __EventReferences[module]:
                    #And if there actually is an event in the events list that matches
                    if __EventReferences[module][resource] in __events:
                        #Than Remove old reference if there was one
                        __events.remove(__EventReferences[module][resource])
                        
            else:
                #If this is the first event in the module we need to make the module representation
                __EventReferences[module] = {}
                     
            #Add new event
            x.module = module;x.resource =resource
            __events.append(x)
            
            #Update index
            __EventReferences[module][resource] = x

#look in the modules and compile all the event code
def getEventsFromModules():
    global __events
    with modules.modulesLock:
        with __event_list_lock:
            #Set __events to an empty list we can build on
            __events = []
            for i in modules.ActiveModules.copy():
                #For each loaded and active module, we make a subdict in __EventReferences
                __EventReferences[i] = {} # make an empty place or __events in this module
                #now we loop over all the resources o the module to see which ones are __events 
                for m in modules.ActiveModules[i].copy():
                    j=modules.ActiveModules[i][m]
                    if j['resource-type']=='event':
                        if 'setup' in j:
                            setupcode = j['setup']
                        else:
                            setupcode = "pass"

                        #For every resource that is an event, we make an event object based o
                        x = Event(j['trigger'],j['action'],make__eventscope(i),setup = setupcode)
                        x.module = i;x.resource =m
                        __events.append(x)
                        #Now we update the references
                        __EventReferences[i][m] = x

class Event():
    """Class represeting one checkable event. when and do must be python code strings,
    scope must be a dict representing the scope in which both the trigger and action will be executed.
    When the trigger goes from fase to true, the action will occur.
    
    optional params:
    ratelimit: Do not do the action more often than every X seconds
    continual: Execute as often as possible while condition remains true
    
    """
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = "pass"):
        #Copy in the data from args
        self.scope = scope
        self._prevstate = False
        self.ratelimit = ratelimit
        self.continual = continual
        
        #BEGIN SOMEWHAT HACKISH CODE TO HANDLE TRIGGER EXPRESSIONS
        #This code handles the case wherin the user makes a trigger expresion
        #Basically, we set trigger to "False", making check() a no-op, and we create a function
        #and subscribe it to the message.
        if when.strip().startswith('!onmsg '):
            def action_wrapper(topic,message):
                #setup environment
                self.scope['__topic'] = topic
                self.scope['__message'] = message
                #We delegate the actual execution ofthe body to the on_trigger
                self._on_trigger()
                
            #When the object is deleted so will this reference and the message bus's auto unsubscribe will handle it
            self.action_wrapper_because_we_need_to_keep_a_reference = action_wrapper
            #Make the no-op trigger
            self.trigger = compile('False',"<trigger>","eval")
            #Handle whatever stupid whitespace someone puts in
            #What this does is to eliminate leading whitespace, split on first space,
            #Then get rid of any extra spaces in between the command and argument.
            t = when.strip().split(' ',1)[1].strip()
            #Subscribe our new function to the topic we want
            messagebus.subscribe(t,action_wrapper)
        
        #If the user tries to use the !onchanged trigger expression,
        #what we do is to make a function that does the actual checking and always returns false
        #This means it will be called every frame but the usual trigger method(which is edge triggered)
        #Is bypassed. Instead, we directly call self._on_trigger and return false
        elif when.strip().startswith('!onchange '):
            #Handle whatever stupid whitespace someone puts in
            #What this does is to eliminate leading whitespace, split on first space,
            #Then get rid of any extra spaces in between the command and argument.
            f = when.strip().split(' ',1)[1].strip()
            self.f= compile(f,"<trigger>","eval")
            self.at_least_one_reading = False
            def change_func():           
                self.latest = eval(self.f,self.scope,self.scope)
            
                if not self.at_least_one_reading:
                    self.old = self.latest
                    self.at_least_one_reading = True
                
                if self.old==self.latest:
                    
                    return False
                else:
                    self.old = self.latest
                    self.scope['__value'] = self.latest
                    self._on_trigger()
                    return False
            
            self.scope['__SYSTEM_CHANGE_CHECK'] = change_func
            #Make the custom trigger
            self.trigger = compile('__SYSTEM_CHANGE_CHECK()',"<trigger>","eval")
            
        else:
        #BACK TO HANDLING NORMAL EXPRESSIONS
            #Precompile non trigger expression code
            self.trigger = compile(when,"<trigger>","eval")
        #Compile the action and run the initializer
        self.action = compile(do,"<action>","exec")
        initializer = compile(setup,"<setup>","exec")
        exec(initializer,self.scope,self.scope)

        #This lock makes sure that only one copy of the event executes at once.
        self.lock = threading.Lock()
        
        #This keeps track of the last time the event was triggered  so we can rate limit
        self.lastexecuted = 0
        
        #A place to put errors
        self.errors = []
        
    def check(self):
        """Check if the trigger is true and if so do the action."""
        try:
            #We need to make sure the thread pool doesn't run two copies of an event
            self.lock.acquire()
            #Eval the condition in the local event scope
            if eval(self.trigger,self.scope,self.scope):
                #Only execute once on false to true change unless continual was set
                if (self.continual or self._prevstate == False):
                    #Set the flag saying that the last time it was checked, the condition evaled to True
                    self._prevstate = True
                    #The trigger went from false to true and therefore met the trigger condition
                    #So call the function
                    self._on_trigger()
            else:
                #The eval was false, so the previous state was False
                self._prevstate = False
        except Exception as e:
            self._handle_exception(e)
        finally:
            self.lock.release()
            
    def _on_trigger(self):
        #This function gets called when whatever the event's trigger condition is.
        #it provides common stuff to all trigger types like logging and rate limiting
        
        #Check the current time minus the last time against the rate limit
        #Don't execute more often than ratelimit
        if (time.time()-self.lastexecuted >self.ratelimit):
            #Set the varible so we know when the last time the body actually ran
            self.lastexecuted = time.time()
            try:
                exec(self.action,self.scope,self.scope)
            except Exception as e:
                self._handle_exception(e)

    def _handle_exception(self, e):
            #When an error happens, log it and save the time
            #Note that we are logging to the compiled event object
            self.errors.append([time.strftime('%A, %B %d, %Y at %H:%M:%S Server Local Time'),e])
            #Keep oly the most recent 25 errors
            self.errors = self.errors[-25:]
            
            #The mesagebus is largely untested and we don't want to kill the thread.
            try:
                messagebus.postMessage('system/errors/events/'+util.url(self.module)+'/'+util.url(self.resource),str(e))
            except Exception as e:
                print (e)
    
