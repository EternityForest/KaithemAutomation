#Copyright Daniel Dunn 2013-2015
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

import traceback,threading,sys,time,atexit,collections,os,base64,imp,types,weakref,dateutil,datetime,recurrent,re,pytz,gc
import dateutil.rrule
import dateutil.tz
from . import workers, kaithemobj,messagebus,util,modules_state,scheduling
from .config import config
from .scheduling import scheduler

#Use this lock whenever you access _events or __EventReferences in any way.
#Most of the time it should be held by the event manager that continually iterates it.
#To update the _events, event execution must temporarily pause
_event_list_lock = threading.RLock()
_events = []

#Let us now have a way to get at active event objects by means of their origin (resource, module) tuple.
__EventReferences = {}
EventReferences = __EventReferences

def manualRun(event):
    "Run an event manually"
    return EventReferences[event].manualRun()

def getPrintOutput(event):
    "Given a tuple of (module, resource),  return the doc string of an event if it exists, else return '' "
    try:
        return EventReferences[event].printoutput
    except:
        return ""

def getEventInfo(event):
    "Given a tuple of (module, resource),  return the doc string of an event if it exists, else return '' "
    return EventReferences[event].__doc__ if event in EventReferences and EventReferences[event].__doc__  else ""

def renameEvent(oldModule,oldResource,module,resource):
    "Move an event, similar to unix mv"
    with _event_list_lock:
        __EventReferences[module,resource] = __EventReferences[oldModule,oldResource]
        del  __EventReferences[oldModule,oldResource]
        __EventReferences[module,resource].resource = resource
        __EventReferences[module,resource].module = module

def getEventErrors(module,event):
    "Return a list of errors for a given event. Uses _event_list_lock"
    with _event_list_lock:
            try:
                return __EventReferences[module,event].errors
            except:
                return[['0','Event does not exist or was not properly initialized']]

def fastGetEventErrors(module,event):
    "This version might not always be accurate, but will never modify anything or return an error. Does not  use a lock."
    try:
        return __EventReferences[module,event].errors
    except:
        return[]

#Given two functions, execute the action when the trigger is true.
#Trigger takes no arguments and returns a boolean
def when(trigger,action,priority="interactive"):
    """
    Create a one time event that deletes itself after firing.

    Args:
        trigger(function): The event occurs when this goes true
        action(function): This function is called when the event fires
        priority(string): One of realtime, interactive, low, etc. determines how often to poll.
    """

    module = '<OneTimeEvents>'
    resource = trigger.__name__ + '>' + action.__name__ + ' ' + 'set at ' + str(time.time()) + 'by thread: '+str(threading.currentThread().ident)+' id='+str(base64.b64encode(os.urandom(16)))

    #We cannot remove the event from within itself because of the lock that
    #We do not want to make into an RLock for speed. So we do it in a different thread.
    def rm_slf():
        removeOneEvent(module,resource)

    def f():
        action()
        workers.do(rm_slf)

    e = PolledInternalSystemEvent(trigger,f,priority=priority,m=module,r=resource)
    e.module = module
    e.resource = resource
    __EventReferences[module,resource] = e
    e.register()

#Given two functions, execute the action after delay.
#Trigger takes no arguments and returns a boolean
def after(delay,action,priority="interactive"):
    #If the time is in the future, then we use the scheduler.
    if delay > 1.2:
        scheduling.scheduler.schedule(action, time.time()+delay)
        return


    module = '<OneTimeEvents>'
    resource = "after(" +str(delay) +")"+ '>' + action.__name__ + ' ' + 'set at ' + str(time.time()) +'by thread: '   +str(threading.currentThread().ident)+' id='+str(base64.b64encode(os.urandom(16)))
    start = time.time()
    def f():
        if time.time() > start+delay:
            return True
        return False

    #We cannot remove the event from within itself because of the lock that
    #We do not want to make into an RLock for speed. So we do it in a different thread.
    def rm_slf():
        removeOneEvent(module,resource)

    def g():
        action()
        workers.do(rm_slf)

    e = PolledInternalSystemEvent(f,g,priority=priority)

    e.module = module
    e.resource = resource
    __EventReferences[module,resource] = e
    e.register()


kaithemobj.kaithem.events.when = when
kaithemobj.kaithem.events.after = after

def getEventLastRan(module,event):
    with _event_list_lock:
            try:
                return __EventReferences[module,event].lastexecuted
            except Exception as e:
                return 0
def countEvents():
    #Why bother with the lock. The event count is not critical at all.
    return len(_events)

def STOP():
    global run
    run = False
t=0
def stim():
    global t
    t=time.time()
    print('000000000')

def ptim():
    print(time.time()-t)
#In a background thread, we use the worker pool to check all threads

run = True
#Acquire a lock on the list of _events(Because we can't really iterate safely without it)
#And put the check() fuction of each event object into the thread pool
def __manager():
    temp = 0;
    global averageFramesPerSecond
    lastFrame = 0
    averageFramesPerSecond = 0
    #Basically loops for the lief of the app
    while run:
        framedelay = 1.0/config['max-frame-rate']
        mindelay = config['delay-between-frames']
        #Get the time at the start of the loop
        temp = time.time()
        e = threading.Event()
        def f():
            e.set()
        with _event_list_lock:
            for i in _events:
                #BAD HACK ALERT
                #Instead of letting the event do the countdown.
                # we do it ourselves, because we don't want
                #To send anything through the slow queue we don't need to.
                #We rely on the object itself to reset the countdown though.

                #We also check the ratelimit ourselves here.
                #This should probably be moved into an event.precheck function.
                if i.countdown <1:
                    #If there is a ratelimit, we check the ratelimit here also.
                    if i.ratelimit:
                        if time.time()-i.lastexecuted > i.ratelimit:
                            workers.do(i.check)
                    else:
                        workers.do(i.check)
                else:
                    i.countdown -= 1

            #Don't spew another round of events until the last one finishes so we don't
            #fill up the queue. The way we do this, is that after we have finished queueing
            #up all the events to be polled, we insert a sentry.
            #Because this sentry comes after the queued up events, when the sentry runs,
            #We know that all of the events were taked out of the queue.
            #We do not know that they have all finished running, nor do we want to.
            #If one event takes several seconds to poll, it will not prevent the next round of
            #events. We depend on the event objects themselves to enforce the guarantee that only
            #one copy of the event can run at once.
        e.clear()
        workers.do(f)

        #Limit the polling cycles per second to avoid CPU hogging
        #Subtract the time the loop took from the delay
        #Allow config to impose a minimum delay
        time.sleep(max(framedelay-(time.time()-temp),mindelay))

        #On the of chance something odd happens, let's not wait forever.
        e.wait(5)
        #smoothing filter
        averageFramesPerSecond = (averageFramesPerSecond *0.98) +   ((1.0/(time.time()-lastFrame)) *0.02)
        lastFrame = time.time()

#Start the manager thread as a daemon
#Kaithem has a system wide worker pool so we don't need to reinvent that
t = threading.Thread(target = __manager, name="EventPollingManager")
#This thread never really does anything, it just delegates to the worker threads, so I'm
#fine with leaving it as a daemon.
t.daemon = True
t.start()




def parseTrigger(when):
    """
    Parse a trigger expression into a tokenized form
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
def Event(when = "False",do="pass",scope= None ,continual=False,ratelimit=0,setup = None,priority=2,**kwargs):
    trigger = parseTrigger(when)

    if scope == None:
        scope = make_eventscope()

    if trigger[0] == '!function':
        if len(when.split(';',1))>1:
            triggeraction = when.split(';',1)[1].strip()
        else:
            triggeraction = None
        if 'nolock' in trigger:
            l = False
        else:
            l = True

        return FunctionEvent(trigger[1].split(';')[0], triggeraction, l ,do,scope,continual,ratelimit,setup,priority,**kwargs)

    if trigger[0] == '!onmsg':
        return MessageEvent(when,do,scope,continual,ratelimit,setup,priority,**kwargs)

    elif trigger[0] == '!onchange':
        return ChangedEvalEvent(when,do,scope,continual,ratelimit,setup,priority,**kwargs)

    elif trigger[0] == '!edgetrigger':
        return PolledEvalEvent(when,do,scope,continual,ratelimit,setup,priority,**kwargs)

    elif trigger[0] == '!time':
        return RecurringEvent(' '.join(trigger[1:]),do,scope,continual,ratelimit,setup,priority,**kwargs)

    #Defensive programming, raise error on nonsense event type
    raise RuntimeError("Invalid trigger expression that begins with" + str(trigger[0]))


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
    """Base Class representing one event.
    scope must be a dict representing the scope in which both the trigger and action will be executed.
    When the trigger goes from fase to true, the action will occur.

    setupr,when and do are some representation of an action, the specifics of which are defined by derived classes.
    optional params:
    ratelimit: Do not do the action more often than every X seconds
    continual: Execute as often as possible while condition remains true

    """

    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = None,priority = 2,m=None,r=None):

        #Copy in the data from args
        self.scope = scope
        self._prevstate = False
        self.ratelimit = ratelimit
        self.continual = continual
        self.countdown = 0
        self.printoutput = ""
        fps= config['max-frame-rate']
        #symbolic prioity os a rd like high,realtime, etc
        #Actual priority is a number that causes polling to occur every nth frame
        #Legacy events have numeric priorities
        self.symbolicpriority = priority
        #realtime is always every frame even for legacy
        if self.symbolicpriority == 1:
            self.symbolicpriority == 'realtime'

        #try to look up the numeric priority from the symbolic
        try:
            self.priority = int(fps*config['priority-response'][priority])
        except KeyError:
            #Should that fail, attempt to use the priority directly
            try:
                self.priority = max(1,int(priority))
            #If even that fails, use interactive priority.
            except ValueError:
                self.priority = config['priority-response']['interactive']

        self.runTimes = []
        self.module = m if m else "<unknown>"
        self.resource = r if r else str(util.unique_number())
        self.pymodule = types.ModuleType(str("Event_"+self.module +"_"+self.resource))
        self.pymodule.__file__ = str("Event_"+self.module +"_"+self.resource)
        #This lock makes sure that only one copy of the event executes at once.
        self.lock = threading.Lock()
        #This keeps track of the last time the event was triggered  so we can rate limit
        self.lastexecuted = 0

        #A place to put errors
        self.errors = []

    def manualRun(self):
        #J.F. Sebastian of stackoverflow's post was helpful for this
        if not self.lock.acquire(False):
            time.sleep(0.1)
            if not self.lock.acquire(False):
                time.sleep(0.7)
                if not self.lock.acquire():
                    raise WouldBlockError("Could not acquire lock while event already running or polling. Trying again may work.")
        try:
            self._on_trigger()
        finally:
            self.lock.release()

    def cleanup(self):
        try:
            with self.lock:
                self.pymodule.__dict__.clear()
        except:
            raise

    def new_print(self,*args):
        #No, we cannot just do print(*args), because it breaks on python2
        if len(args)==1:
            print(args[0])
            self.printoutput+=str(args[0])+"\n"
        else:
            print(args)
            self.printoutput+=str(args)+"\n"
        self.printoutput = self.printoutput[-2500:]

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
                messagebus.postMessage('/system/events/ran',[self.module, self.resource])
            except Exception as e:
                self._handle_exception(e)

    def _handle_exception(self, e):
            if sys.version_info>(3,0):
                tb = traceback.format_exc(6, chain=True)
            else:
                tb = traceback.format_exc(6)
            #When an error happens, log it and save the time
            #Note that we are logging to the compiled event object
            self.errors.append([time.strftime(config['time-format']),tb])
            #Keep only the most recent errors
            self.errors = self.errors[-(config['errors-to-keep']):]
            #The mesagebus is largely untested and we don't want to kill the thread.
            try:
                messagebus.postMessage('/system/errors/events/'+
                                       self.module+'/'+
                                       self.resource,str(tb))
            except Exception as e:
                print (e)

            #Catch legacy number based priorities that are realtime
            if self.symbolicpriority == 1:
                backoff = config['error-backoff']['realtime']
            else:
                try:
                    backoff = config['error-backoff'][self.symbolicpriority]
                except KeyError:
                    backoff = config['error-backoff']['interactive']

            #Make sure backoff slows, not speeds
            #Figure out the normal poll time,backoff not less than that
            backoff = max(1/(config['max-frame-rate']/self.priority), backoff)

            #Calculate backoff time in terms of frames
            backoff = (averageFramesPerSecond*backoff)

            self.countdown = int(backoff)
            #If this is the first error since th module was last saved raise a notification
            if len(self.errors)==1:
                messagebus.postMessage('/system/notifications/errors',"Event \""+self.resource+"\" of module \""+self.module+ "\" may need attention")

    def register(self):
        #Some events are really just containers for a callback, so there is no need to poll them
        with _event_list_lock:
            if self.polled:
                if self not in _events:
                    _events.append(self)

    def unregister(self):
        with _event_list_lock:
            if self in _events:
                _events.remove(self)

    def check(self):
        """This is the function that the polling system calls to poll the event.
        It calls a _check() function which must be defined by a subclass."""
        #Should another thread already be polling this, We actually don't want to
        #just sit around and wait. That would mean one slow event could queue up many
        #copies of itself and cause odd performance issues.
        #so, if another thread is already handling this, just return and move on.
        if not self.lock.acquire(False):
            return

        try:
            #This is how we handle priority for now. The passing things between threads
            #Is what really takes time polling so the few instructions extra should be well worth it
            #Basically a countdown timer in frames that polls at zero and resets (P0 is as fast as possible)
            if self.countdown <= 0:
                self.countdown = self.priority
            else:
                self.countdown -= 1
                return

            try:
                self._check()
            except Exception as e:
                self._handle_exception(e)
        finally:
            self.lock.release()
class DummyModuleScope():
    pass

class CompileCodeStringsMixin():
    "This mixin lets a class take strings of code for its setup and action"
    def _init_setup_and_action(self,setup,action,params={}):
        #Compile the action and run the initializer
        if setup == None:
            setup = "pass"

        #initialize the module scope with the kaithem object and the module thing.
        initializer = compile(setup,"Event_"+self.module+'_'+self.resource,"exec")

        try:
            self.pymodule.__dict__['kaithem']=kaithemobj.kaithem
            self.pymodule.__dict__['module']=modules_state.scopes[self.module] if self.module in modules_state.scopes else DummyModuleScope()
            try:
                self.pymodule.__dict__['print']=self.new_print
            except:
                logging.exception("Failed to activate event print output functionality")
            self.pymodule.__dict__.update(params)
        except KeyError as e:
            raise e
        exec(initializer,self.pymodule.__dict__,self.pymodule.__dict__)

        body = "def _event_action():\n"
        for line in action.split('\n'):
            body+=("    "+line+'\n')
        body = compile(body,"Event_"+self.module+'_'+self.resource,'exec')
        exec(body,self.pymodule.__dict__)
        self.__doc__ = self.pymodule.__doc__
        #This is one of the weirder line of code I've ever writter
        #Apperently for some reason we have to manually tell it where to go for global variables.


    def _do_action(self):
        self.pymodule._event_action()

class DirectFunctionsMixin():
        def _init_setup_and_action(self,setup,action):
            self._do_action = action

class FunctionWrapper():
    "A wrapper class that acts like a mutable function so that function events can handoff seamlessly"
    def __init__(self, f = lambda : 0):
        self.f = f
        self.wait = False

    def __call__(self):
        if self.wait:
            started = time.time()
            while(time.time()-started<100 and not self.wait):
                time.sleep(0.05)
            if self.wait:
                raise RuntimeError("Event being modified and is taking more than 100 seconds")
        self.f()



#Note: this class does things itself instead of using that CompileCodeStringsMixin
#I'm not sure that was the best idea to use that actually....
class FunctionEvent(BaseEvent):
    def __init__(self,fname,trigaction,l,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self.polled = False
        self.pymodule.__dict__['kaithem']=kaithemobj.kaithem
        self.pymodule.__dict__['module'] =modules_state.scopes[self.module]
        self.active = True
        if 'dummy' in kwargs:
            dummy = kwargs['dummy']
        else:
            dummy = False
        self.fname = fname
        if not dummy:
            if l:
                def f():
                    with self.lock:
                        self._on_trigger()
            else:
                f = self._on_trigger
        else:
            def f():
                pass
        self.f = FunctionWrapper(f)
        self.xyz(do, trigaction, setup)

    def handoff(self, evt):
        """Handoff to new event. Calls to old function get routed to new function.
        Works even of you unregister old event."""
        self.f.f = evt.f.f

    #This was the fastest way to deal with weird exec in nested function with import star buisiness.
    def xyz(self,do, trigaction,setup):
        #compile the body
        body = "def kaithem_event_action():\n"
        for line in do.split('\n'):
            body+=("    "+line+'\n')

        body = compile(body,"Event_"+self.module+'_'+self.resource,'exec')

        exec(body , self.pymodule.__dict__)

        #this lets you do things like !function module.foo
        self.pymodule.__dict__["_kaithem_temp_event_function"] = self.f
        x = compile(self.fname+" = _kaithem_temp_event_function","Event_"+self.module+'_'+self.resource,'exec')
        exec(x,self.pymodule.__dict__)
        del self.pymodule.__dict__["_kaithem_temp_event_function"]

        if trigaction:
            trigaction = compile(trigaction,"Event_"+self.module+'_'+self.resource+'trigaction','exec')
            exec(trigaction,self.pymodule.__dict__)
        #initialize the module scope with the kaithem object and the module thing.
        initializer = compile(setup,"Event_"+self.module+'_'+self.resource+"setup","exec")
        exec(initializer,self.pymodule.__dict__,self.pymodule.__dict__)

    def register(self):
        self.active = True

    def unregister(self):
        self.active = False
        try:
            x = compile("del "+ self.fname,"Event_"+self.module+'_'+self.resource,'exec')
            exec(x,self.pymodule.__dict__)
        except Exception as e:
            print(e)

    #The only difference between this and the base class version is
    #That this version propagates exceptions
    def _on_trigger(self):
        #This function gets called when whatever the event's trigger condition is.
        #it provides common stuff to all trigger types like logging and rate limiting

        #Check the current time minus the last time against the rate limit
        #Don't execute more often than ratelimit
        if not self.active:
            raise RuntimeError("Cannot run deleted FunctionEvent")

        if (time.time() -self.lastexecuted >self.ratelimit):
            #Set the varible so we know when the last time the body actually ran
            self.lastexecuted = time.time()
            try:
                #Action could be any number of things, so this method must be implemented by
                #A derived class or inherited from a mixin.
                self._do_action()
                messagebus.postMessage('/system/events/ran',[self.module, self.resource])
            except Exception as e:
                if self.active:
                    self._handle_exception(e)
                raise


    def _do_action(self):
        self.pymodule.kaithem_event_action()

##Note: this class does things itself instead of using that CompileCodeStringsMixin
##I'm not sure that was the best idea to use that actually....
#class ManualEvent(BaseEvent):
    #def run(self):
        #for i in self.permissions:
            #pages.require(i)
        #pages.postOnly()
        #self.f()

        ##Return user to the module page. If name has a folder, return the user to it;s containing folder.
        #x = util.split_escape(self.resource,"/")
        #if len(x)>1:
            #raise cherrypy.HTTPRedirect("/modules/module/"+util.url(self.module)+'/resource/'+'/'.join([util.url(i) for i in x[:-1]])+"#resources")
        #else:
            #raise cherrypy.HTTPRedirect("/modules/module/"+util.url(self.module)+"#resources")#+'/resource/'+util.url(resource))

    #def __init__(self,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):
        #BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        #self.polled = False
        #self.pymodule.__dict__['kaithem']=kaithemobj.kaithem
        #self.pymodule.__dict__['module'] =modules_state.scopes[self.module]
        #def f():
            #with self.lock:
                #self._on_trigger()
        #self.f =f()

        ##compile the body
        #body = "def kaithem_event_action():\n"
        #for line in do.split('\n'):
            #body+=("    "+line+'\n')

        #body = compile(body,"Event_"+self.module+'_'+self.resource,'exec')
        #exec(body,self.pymodule.__dict__)

        ##this lets you do things like !function module.foo
        #self.pymodule.__dict__["_kaithem_temp_event_function"] = f
        #x = compile(fname+" = _kaithem_temp_event_function","Event_"+self.module+'_'+self.resource,'exec')
        #exec(x,self.pymodule.__dict__)
        #del self.pymodule.__dict__["_kaithem_temp_event_function"]

        ##initialize the module scope with the kaithem object and the module thing.
        #initializer = compile(setup,"Event_"+self.module+'_'+self.resource+"setup","exec")
        #exec(initializer,self.pymodule.__dict__,self.pymodule.__dict__)

    ##The only difference between this and the base class version is
    ##That this version propagates exceptions
    #def _on_trigger(self):
        ##This function gets called when whatever the event's trigger condition is.
        ##it provides common stuff to all trigger types like logging and rate limiting

        ##Check the current time minus the last time against the rate limit
        ##Don't execute more often than ratelimit
        #if not self.active:
            #raise RuntimeError("Cannot run deleted FunctionEvent")

        #if (time.time() -self.lastexecuted >self.ratelimit):
            ##Set the varible so we know when the last time the body actually ran
            #self.lastexecuted = time.time()
            #try:
                ##Action could be any number of things, so this method mut be implemented by
                ##A derived class or inherited from a mixin.
                #self._do_action()
                #messagebus.postMessage('/system/events/ran',[self.module, self.resource])
            #except Exception as e:
                #if self.active:
                    #self._handle_exception(e)
                #raise


    #def _do_action(self):
        #self.pymodule.kaithem_event_action()

class MessageEvent(BaseEvent,CompileCodeStringsMixin):
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):

        #This event type is not polled. Note that it doesn't even have a check() method.
        self.polled = False
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self.lastran = 0
        def action_wrapper(topic,message):
            #Since we aren't under the BaseEvent.check() lock, we need to get it ourselves.
            with self.lock:
                if self.ratelimit > time.time()-self.lastran:
                    return
                self.lastran = time.time()
                #These two lines were an old fix for a circular reference buf that made message events not go away.
                #It is still here just in case another circular reference bug pops up.
                if (self.module,self.resource) not in EventReferences:
                    return

                #setup environment
                self.pymodule.__dict__['__topic'] = topic
                self.pymodule.__dict__['__message'] = message
                #We delegate the actual execution of the body to the on_trigger
                self._on_trigger()


        #When the object is deleted so will this reference and the message bus's auto unsubscribe will handle it
        self.action_wrapper_because_we_need_to_keep_a_reference = action_wrapper

        #Handle whatever stupid whitespace someone puts in
        #What this does is to eliminate leading whitespace, split on first space,
        #Then get rid of any extra spaces in between the command and argument.
        t = when.strip().split(' ',1)[1].strip()
        #Subscribe our new function to the topic we want
        messagebus.subscribe(t,action_wrapper)
        self._init_setup_and_action(setup,do)

    #This is the real solution for the circular reference nonsense, until the messagebus has a real unsubscribe feature.
    def unregister(self):
        del self.action_wrapper_because_we_need_to_keep_a_reference

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
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self._init_setup_and_action(setup,do)

        x = compile("def _event_trigger():\n    return "+f,"Event_"+self.module+'_'+self.resource,'exec')
        exec(x,self.pymodule.__dict__)

        #This flag indicates that we have never had a reading
        self.at_least_one_reading = False
        self.polled = True

    def _check(self):
        #Evaluate the function that gives us the values we are looking for changes in
        self.latest = self.pymodule._event_trigger()
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
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self.polled = True

        #Sometimes an event is used for its setup action and never runs.
        #If the trigger is False, it will never trigger, so we don't poll it.
        if when == 'False':
            self.polled = False
        #Compile the trigger
        x = compile("def _event_trigger():\n    return "+when,"Event_"+self.module+'_'+self.resource,'exec')
        exec(x,self.pymodule.__dict__)

        self._init_setup_and_action(setup,do)

    def _check(self):
        """Check if the trigger is true and if so do the action."""
        #Eval the condition in the local event scope
        if self.pymodule._event_trigger():
            #Only execute once on false to true change unless continual was set
            if (self.continual or self._prevstate == False):
                self._prevstate = True
                self._on_trigger()
        else:
            #The eval was false, so the previous state was False
            self._prevstate = False


class PolledInternalSystemEvent(BaseEvent,DirectFunctionsMixin):
    def __init__(self,when,do,scope = None ,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self.polled = True
        #Compile the trigger
        self.trigger = when
        self._init_setup_and_action(setup,do)


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


class RecurringEvent(BaseEvent,CompileCodeStringsMixin):
    "This represents an event that happens on a schedule"
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):
        self.polled = False
        self.trigger = when
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self._init_setup_and_action(setup,do)
        #Bound methods aren't enough to stop GC
        #TODO, Maybe this method should be asyncified?
        self.handler= self._handler
        self.exact = self.get_exact()
        self.rr = scheduling.get_rrule(self.trigger)
        self.nextruntime = scheduling.get_next_run(self.trigger,rr=self.rr)
        if self.nextruntime == None:
            return
        self.next=scheduler.schedule(self.handler,self.nextruntime,False)

    def get_exact(self):
        r = re.match(r"exact( ([0-9]*\.?[0-9]))?" , self.trigger)
        if not r:
            return False
        if re.groups():
            return float(re.groups[1])
        else:
            return 3

    #Recalculate the next time at which the event should run, for cases in which the time was set incorrectly
    #And has now been changed. Not well tested, work in progress, might cause a missed event or something.
    def recalc_time(self):
        try:
            self.next.unregister()
        except AttributeError:
            pass
        self.nextruntime = scheduling.get_next_run(self.trigger, rr=self.rr)
        if self.nextruntime == None:
            return
        self.next=scheduler.schedule(self.handler,self.nextruntime,False)

    def _handler(self):
        if not 'allow_overlap' in self.trigger:
            if not self.lock.acquire(False):
                self.nextruntime = scheduling.get_next_run(self.trigger)
                self.next=scheduler.schedule(self.handler, self.nextruntime , False)
                return
        try:
            #If the scheduler misses it and we have exact configured, then we just don't do the
            #Actual action.
            def f():
                if not (self.exact and (time.time()  > (self.nextruntime + self.exact))):
                    self._on_trigger()
            workers.do(f)

        finally:
            try:
                self.lock.release()
            except Exception as e:
                print(e)
                pass
            nextrun = 0
            self.nextruntime = scheduling.get_next_run(self.trigger)
            if self.nextruntime == None:
                return

            if self.nextruntime:
                self.next=scheduler.schedule(self.handler, self.nextruntime, False)
                return
            print("Caught event trying to return None for get next run, time is:", time.time(), " expr is ", self.trigger, " last ran ", self.lastexecuted,"retrying")
            time.sleep(0.179)#A random number unlikely to sync up with anything

            if self.nextruntime:
                self.next=scheduler.schedule(self.handler, self.nextruntime, False)
                return
            print("""Caught event trying to return None for get next run
                (might be an event that only runs for a period that already expired), and retry 1 failed time is:""",
                  time.time(), " expr is ",
                  self.trigger, " last ran ",
                  self.lastexecuted,"retrying")
            time.sleep(1.353)#A random number unlikely to sync up with anything

            if self.nextruntime:
                self.next=scheduler.schedule(self.handler, self.nextruntime, False)
                return
            print("""Caught event trying to return None for get next run
                (might be an event that only runs for a period that already expired), and retry 1 failed time is:""",
                  time.time(), " expr is ",
                  self.trigger, " last ran ",
                  self.lastexecuted,"NOT retrying")


    def __del__(self):
        try:
            self.next.unregister()
        except AttributeError:
            pass

    def unregister(self):
        try:
            self.next.unregister()
        except AttributeError:
            pass


#If the system time has been set, we may want to recalculate all of the events.
#Work in progress
def recalc_schedule():
    with _event_list_lock:
        for i in _EventReferences:
            if isinstance(_EventReferences[i],RecurringEvent):
                _EventReferences[i].recalc_time()


#BORING BOOKEEPING BELOW


#Delete a event from the cache by module and resource
def removeOneEvent(module,resource):
    with _event_list_lock:
        if (module,resource) in __EventReferences:
            __EventReferences[module,resource].unregister()
            __EventReferences[module,resource].cleanup()
            del __EventReferences[module,resource]
    gc.collect()


#Delete all _events in a module from the cache
def removeModuleEvents(module):
    with _event_list_lock:
        for i in __EventReferences.copy():
            if i[0] == module:
                #delete both the event and the reference to it
                __EventReferences[i].unregister()
                __EventReferences[i].cleanup()
                del __EventReferences[i]

#Every event has it's own local scope that it uses, this creates the dict to represent it
def make_eventscope(module = None):
    if module:
        return {'module':modules_state.scopes[module],'kaithem':kaithemobj.kaithem}
    else:
        return {'module':None, 'kaithem':kaithemobj.kaithem}

#This piece of code will update the actual event object based on the event resource definition in the module
#Also can add a new event.
#Now if you already have an event object, like from a test compile, you can just use that.
def updateOneEvent(resource,module, o=None):
    #This is one of those places that uses two different locks(!)
    with modules_state.modulesLock:
        try:
            #Get either a reference to the old version or None
            if (module,resource) in EventReferences:
                old = EventReferences[module,resource]
            else:
                old = None

            #We want to destroy the old event before making a new one but we also want seamless handoff
            #So what we do is we tell the old one to block if anyone calls it until we are done
            if isinstance(old, FunctionEvent):
                EventReferences[module,resource].f.wait = True

            if old:
                #Unregister first, then clean up.
                old.unregister()
                #Now we clean it up and delete any references the user code might have had to things
                old.cleanup()
            #Really we should wait a bit longer but this is a compromise, we wait so any cleanup effects can propagate.
            #120ms is better than nothing I guess.
            time.sleep(0.120)
            if not o:
                #Now we make the event
                x = make_event_from_resource(module,resource)
            else:
                x = o

            #Special case for functionevents, we do a handoff. This means that any references to the old
            #event now call the new one.

            #If old one and new one are functionevents we can hand off, if only old, then we just unblock
            if isinstance(old, FunctionEvent):
                if isinstance(x, FunctionEvent):
                    __EventReferences[module,resource].handoff(x)
                #Unblock the old one no matter what or else it will have to block for the full timeout duration
                __EventReferences[module,resource].f.wait = False

            #Here is the other lock(!)
            with _event_list_lock: #Make sure nobody is iterating the eventlist
                #Add new event
                x.register()
                #Update index
                __EventReferences[module,resource] = x
        except:
            mak

#makes a dummy event for when there is an error loading and puts it in the right place
#The dummy does nothing but is in the right place
def makeDummyEvent(module,resource):
    #This is one of those places that uses two different locks(!)
    with modules_state.modulesLock:

        x = Event(m=module,r=resource)
        #Here is the other lock(!)
        with _event_list_lock: #Make sure nobody is iterating the eventlist
            if (module,resource) in __EventReferences:
                __EventReferences[module,resource].unregister()

            #Add new event
            x.register()
            #Update index
            __EventReferences[module,resource] = x

#look in the modules and compile all the event code
#if only is supplied, must be a set and will only look in those modules
def getEventsFromModules(only = None):
    global _events
    toLoad = []

    #Closures were acting weird. This class is to be like a non wierd closure.
    class needstobeloaded():
        def __init__(self,module,resource):
            self.module=module
            self.resource = resource

        def f(self):
            x = make_event_from_resource(self.module,self.resource)
            x.register()
            #Now we update the references
            globals()['__EventReferences'][self.module,self.resource] = x

    with modules_state.modulesLock:
        with _event_list_lock:
            for module in modules_state.ActiveModules:
                #now we loop over all the resources of the module to see which ones are _events
                if only == None or (module in only)  :
                    for resource in modules_state.ActiveModules[module]:
                        x = modules_state.ActiveModules[module][resource]
                        if x['resource-type']=='event':
                            #For every resource that is an event, we make an event object based on it
                            #And put it in the event referenced thing.
                            #However, we do this indirectly, for each event we create a function representing
                            #the actions to set it up
                            f = needstobeloaded(module, resource)
                            toLoad.append(f)
                            f.module =module
                            f.resource =resource

            toLoad =sorted(toLoad,key= lambda x: (x.module,x.module))
            nextRound = []
            #for each allowed loading attempt, we loop over
            #the events and try to set them up. If this fails,
            #add to the retry list and retry next round. This means they will be attempted again
            #up to the maximum number of tries. The important part is that we don't
            #retry immediately, but only after trying the remaining list of events.
            #This is because inter-event dependancies are the most common reason for failure.
            for baz in range(0,max(1,config['max-load-attempts'])):
                for i in toLoad:
                    try:
                        i.f()
                        messagebus.postMessage("/system/events/loaded",[i.module,i.resource])
                        time.sleep(0.005)
                    #If there is an error, add it t the list of things to be retried.
                    except Exception as e:
                        if sys.version_info > (3,0):
                            i.error = traceback.format_exc(6,chain = True)
                        else:
                            i.error = traceback.format_exc(6)
                        nextRound.append(i)
                        pass
                toLoad = nextRound
                nextRound =[]
            #Iterate over the failures after trying the max number of times to fix them
            #and make the dummy events and notifications
            for i in toLoad:
                makeDummyEvent(i.module,i.resource)
                #Add the reason for the error to the actual object so it shows up on the page.
                __EventReferences[i.module , i.resource].errors.append([time.strftime(config['time-format']),str(i.error)])
                messagebus.postMessage("/system/notifications/errors","Failed to load event resource: " + i.resource +" module: " + i.module + "\n" +str(i.error)+"\n"+"please edit and reload.")

def make_event_from_resource(module,resource,subst=None):
    """Returns an event object when given a module and resource name pointing to an event resource.
    Also, if subst is a dict, will use the dict given in subst instead of looking it up.

    The reason for this is so that you can try test compiling without having to actually change the resource.
    """
    if not subst:
        r = modules_state.ActiveModules[module][resource]
    else:
        r = subst

    #Add defaults for legacy events that do not have setup, rate limit, etc.
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

    if 'enable' in r:
        if not r['enable']:
            if not parseTrigger(r['trigger'][0]) == '!function':
                return Event(m=module,r=resource)
            else:
               return Event(r['trigger'],r['action'],make_eventscope(module),
              setup = setupcode,
              continual = continual,
              ratelimit=ratelimit,
              priority=priority,
              m=module,
              r=resource,dummy=True)

    x = Event(r['trigger'],r['action'],make_eventscope(module),
              setup = setupcode,
              continual = continual,
              ratelimit=ratelimit,
              priority=priority,
              m=module,
              r=resource)

    return x
