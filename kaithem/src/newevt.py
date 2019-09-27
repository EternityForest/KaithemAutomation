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

import traceback,threading,sys,time,cherrypy,collections,os,base64,imp,types,weakref,dateutil,datetime,recur,recur,re,pytz,gc,random,logging
import dateutil.rrule
import dateutil.tz
from . import workers, kaithemobj,messagebus,util,modules_state,scheduling
from .config import config
from .scheduling import scheduler
ctime =time.time
do = workers.do

#Ratelimiter for calling gc.collect automatically when we get OSErrors
_lastGC=0

#Use this lock whenever you access _events or __EventReferences in any way.
#Most of the time it should be held by the event manager that continually iterates it.
#To update the _events, event execution must temporarily pause
_event_list_lock = threading.RLock()
_events = []

#Let us now have a way to get at active event objects by means of their origin (resource, module) tuple.
__EventReferences = {}
EventReferences = __EventReferences

logger = logging.getLogger("system_event_errors")
syslogger = logging.getLogger("system.events")


eventsByModuleName=weakref.WeakValueDictionary()

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
        return[['0','Try refreshing page?']]

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

    #This is a hacky flag to let us turn the thing off immediately
    enable = [True]

    #We cannot remove the event from within itself because of the lock that
    #We do not want to make into an RLock for speed. So we do it in a different thread.
    def rm_slf():
        removeOneEvent(module,resource)

    def f():
        if not enable:
            return
        action()
        enable.pop()
        workers.do(rm_slf)

    e = PolledInternalSystemEvent(lambda: False if not enable else trigger(),f,priority=priority,m=module,r=resource)
    e.module = module
    e.resource = resource
    __EventReferences[module,resource] = e
    e.register()

#Given two functions, execute the action after delay.
#Trigger takes no arguments and returns a boolean
def after(delay,action,priority="interactive"):
    #If the time is in the future, then we use the scheduler.
    scheduling.scheduler.schedule(action, time.time()+delay)
    return



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

#Used for interpreter shutdown
run = [True]
def STOP():
    global run
    run.pop()
    print("Threads should be stopping")

cherrypy.engine.subscribe("stop",STOP)


t=0
def stim():
    global t
    t=time.time()
    print('000000000')

def ptim():
    print(time.time()-t)
#In a background thread, we use the worker pool to check all threads


#Yeah yeah, the name isn't the best
class EventEvent(scheduling.UnsynchronizedRepeatingEvent):
    def __init__(self,function,interval,priority="realtime", phase = 0,module=None,resource=None):
        scheduling.BaseEvent.__init__(self)
        self.f = function
        self.interval = float(interval)
        self.scheduled = False
        self.errored = False
        self.lock = threading.Lock()
        self.lastrun = None
        self.phaseoffset = (phase%1)*interval
        self.module=module
        self.resource=resource

    def __repr__(self):
        return "<newevt.EventEvent object for event at "+str((self.module,self.resource))+ "with id "+ str(id(self))+">"

    def run(self):
        do(self._run)

    def _run(self):
        #We must have been pulled out of the event queue or we wouldn't be running
        #So we can reschedule ourself.
        self.scheduled = False
        if self.stop:
            return
        if self.lock.acquire(False):
            self.lastrun = ctime()
            try:
                self.f()
                self._schedule()
            except Exception as e:
                print(e)
                raise
            finally:
                self.lock.release()


insert_phase = 0

def beginPolling(ev):
    #Note that we spread out the intervals by 0.15% to make them not all bunch up at once constantly.
    global insert_phase
    ev.schedulerobj =EventEvent(ev.check,
    config['priority-response'].get(ev.symbolicpriority,0.08)+(insert_phase*0.03)-0.015,
        ev.symbolicpriority)
    try:
        ev.schedulerobj.module = ev.module
        ev.schedulerobj.resource = ev.resource
    except:
        pass
    #Basically we want to spread them out in the phase space from 0 to 1 in a deterministic ish way.
    #There might be a better algorithm of better constant to use, but this one should be decent.
    #The phase of this wave determines the frequency offset applied
    insert_phase += 0.555555
    insert_phase = insert_phase % 1
    ev.schedulerobj.register()
    ev.schedulerobj.schedule()


def endPolling(ev):
    ev.schedulerobj.unregister()


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
def Event(when = "False",do="pass",scope= None ,continual=False,ratelimit=0,setup = None,priority=1,**kwargs):
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

        if 'async' in trigger:
            a= False
        else:
            a = True

        return FunctionEvent(trigger[1].split(';')[0], triggeraction, l ,do,scope,continual,ratelimit,setup,priority,run_async=a,**kwargs)


    elif trigger[0] == '!onmsg':
        return MessageEvent(when,do,scope,continual,ratelimit,setup,priority,**kwargs)

    elif trigger[0] == '!onchange':
        return ChangedEvalEvent(when,do,scope,continual,ratelimit,setup,priority,**kwargs)

    elif trigger[0] == '!edgetrigger':
        if priority=='realtime':
            return ThreadPolledEvalEvent(when,do,scope,continual,ratelimit,setup,priority,**kwargs)
        else:
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

class PersistentData():
    "Used to persist small amounts of data that remain when an event is re-saved"
    pass


fps= config['max-frame-rate']
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
        self.persistant_data = PersistentData()
        self.scope = scope
        self._prevstate = False
        self.ratelimit = ratelimit
        self.continual = continual
        self.countdown = 0
        self.printoutput = ""
        self.active = False
        #Although we usually disable events by removing them from polling/subscriptions
        #This seems like duplicated effort with the new stop flag in the scheduling though.
        #Might be worth a closer look, or might be better to be defensive and have two stop flags.
        self.disable = False
        #symbolic prioity os a rd like high,realtime, etc
        #Actual priority is a number that causes polling to occur every nth frame
        #Legacy events have numeric priorities
        self.symbolicpriority = priority
        #realtime is always every frame even for legacy
        if self.symbolicpriority == 1:
            self.symbolicpriority == 'realtime'

        #try to look up the numeric priority from the symbolic
        try:
            self.poll_interval = config['priority-response'][priority]
        except KeyError:
            #Should that fail, attempt to use the priority directly
            try:
                self.poll_interval  = fps/int(priority)
            #If even that fails, use interactive priority.
            except ValueError:
                self.poll_interval  = config['priority-response']['interactive']
        self.runTimes = []
        self.module = m if m else "<unknown>"
        self.resource = r if r else str(util.unique_number())
        self.pymodule = types.ModuleType(str("Event_"+self.module +"_"+self.resource))
        self.pymodule.__file__ = str("Event_"+self.module +"_"+self.resource)
        self.pymoduleName="Event_"+self.module+'_'+self.resource

        eventsByModuleName[self.pymoduleName]=self
        #This lock makes sure that only one copy of the event executes at once.
        self.lock = threading.Lock()

        #This is a lock used for making modifications to the event itself,
        #Like registering and unregistering.
        #We use a separate lock so the event can start and stop itself, without having
        #To use an RLock for the main lock.
        self.register_lock = threading.Lock()

        #This keeps track of the last time the event was triggered  so we can rate limit
        self.lastexecuted = 0
        #Keep track of the last time the event finished running. Used to detect if it's still
        #going and how long it took
        self.lastcompleted = 0

        self.history = []
        self.backoff_until = 0

        #A place to put errors
        self.errors = []
    def __repr__(self):
        try:
            return "<"+type(self).__name__ +"object at"+hex(id(self))+" for module,resource "+repr((self.module,self.resource))+">"
        except:
            return "<error in repr for event object at "+hex(id(self))+">"

    def manualRun(self):
        #J.F. Sebastian of stackoverflow's post was helpful for this
        if not self.lock.acquire(False):
            time.sleep(0.1)
            if not self.lock.acquire(False):
                time.sleep(0.7)
                if not self.lock.acquire(False):
                    raise WouldBlockError("Could not acquire lock while event already running or polling. Trying again may work.")
        try:
            self._on_trigger()
        finally:
            self.lock.release()

    def cleanup(self):

        try:
            with self.lock:
                try:
                    if '__del__' in self.pymodule.__dict__:
                        self.pymodule.__dict__.__del__()
                        del self.pymodule.__dict__.__del__
                except:
                    logger.exception("Error in delete function")

                self.pymodule.__dict__.clear()
                del self.pymodule
        except:
            raise

    def new_print(self,*args,**kwargs):
        #No, we cannot just do print(*args), because it breaks on python2
        if 'local' in kwargs and kwargs['local']:
            local = True
        else:
            local=False
        if len(args)==1:
            if not local:
                print(args[0])
            self.printoutput+=str(args[0])+"\n"
        else:
            if not local:
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
                self.lastcompleted = time.time()
                self.history.append((self.lastexecuted,self.lastcompleted))
                if len(self.history)>250:
                    self.history.pop(0)
                #messagebus.postMessage('/system/events/ran',[self.module, self.resource])
            except Exception as e:
                #This is not a child of system
                logger.exception("Error running event "+self.resource+" of "+ self.module)
                self._handle_exception(e)


    def _handle_exception(self, e=None, tb=None):
            global _lastGC
            if tb==None:
                if sys.version_info>(3,0):
                    tb = traceback.format_exc(chain=True)
                else:
                    tb = traceback.format_exc()
            #When an error happens, log it and save the time
            #Note that we are logging to the compiled event object
            self.errors.append([time.strftime(config['time-format']),tb])
            #Keep only the most recent errors
            self.errors = self.errors[-(config['errors-to-keep']):]
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

            #Randomize backoff intervals in case there's an error that can
            #Be fixed by changing the order of events
            self.backoff_until=time.time()+(backoff*((random.random()/10) +0.95))

            #Try to fix the error by garbage collecting
            #If there's too many open files
            if isinstance(e,OSError):
                 if time.time()-_lastGC>240:
                    _lastGC = time.time()
                    gc.collect()

            #If this is the first error since th module was last saved raise a notification
            if len(self.errors)==1:
                syslogger.exception("Error running event "+self.resource+" of "+ self.module)
                messagebus.postMessage('/system/notifications/errors',"Event \""+self.resource+"\" of module \""+self.module+ "\" may need attention")
            
    def register(self):
        #Note: The whole self.disabled thing is really laregly a hack to get instant response
        #To things if an event is based on some external thing with a callback that takes time to unregister.
        self.disable = False
        with self.register_lock:
            #Some events are really just containers for a callback, so there is no need to poll them
            if self.polled:
                #Ensure we don't have 2 objects going.
                #This is defensive, we still delete schedulerobj when unregistering
                if hasattr(self,"schedulerobj"):
                    endPolling(self)
                self._prevstate = False
                beginPolling(self)

    def unpause(self):
        self.register()

    def pause(self):
        self.disable = True
        with self.register_lock:
            if hasattr(self,"schedulerobj"):
                endPolling(self)
                del self.schedulerobj

    def unregister(self):
        logging.debug("Unregistering event "+repr(self))
        self.disable = True
        with self.register_lock:
            if hasattr(self,"schedulerobj"):
                endPolling(self)
                del self.schedulerobj


    def check(self):
        """This is the function that the polling system calls to poll the event.
        It calls a _check() function which must be defined by a subclass."""
        #Should another thread already be polling this, We actually don't want to
        #just sit around and wait. That would mean one slow event could queue up many
        #copies of itself and cause odd performance issues.
        #so, if another thread is already handling this, just return and move on.

        #Easy way of doing error backoffs
        if self.disable:
            return
        if time.time()<self.backoff_until:
            return
        if not self.lock.acquire(False):
            return

        try:
            try:
                self._check()
            except Exception as e:
                logger.exception("Error in event "+self.resource+" of "+ self.module)
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
        exec(initializer,self.pymodule.__dict__)

        body = "def _event_action():\n"
        for line in action.split('\n'):
            body+=("    "+line+'\n')
        body = compile(body,"Event_"+self.module+'_'+self.resource,'exec')
        exec(body,self.pymodule.__dict__)
        self.__doc__ = self.pymodule.__doc__
        #This is one of the weirder line of code I've ever writter
        #Apperently for some reason we have to manually tell it where to go for global variables.


    def _do_action(self):
        if hasattr(self.pymodule,"_event_action"):
            self.pymodule._event_action()
        else:
            raise RuntimeError(self.resource+" has no _event_action.")


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
    def __init__(self,fname,trigaction,l,do,scope,continual=False,ratelimit=0,setup = "pass",run_async=False,*args,**kwargs):
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
            #The l parameter tells us if we should use a lock to call the function.
            if l:
                def f(*args,**kwargs):
                    with self.lock:
                        self._on_trigger(*args,**kwargs)
            else:
                f = self._on_trigger
        else:
            def f():
                pass

        if run_async:
            def g(*args,**kwargs):
                def h():
                    f(*args,**kwargs)
                workers.do(h)
            self.f = FunctionWrapper(g)

        else:
            #FunctionWrappers are mutable functions that call their f property
            self.f = FunctionWrapper(f)
        self.xyz(do, trigaction, setup)


    def handoff(self, evt):
        """Handoff to new event. Calls to old function get routed to new function.
        Works even of you unregister old event."""
        self.f.f = evt.f.f

    #This was the fastest way to deal with weird exec in nested function with import star buisiness.
    def xyz(self,do, trigaction,setup):
        #compile the body
        body = "def kaithem_event_action(*):\n"
        for line in do.split('\n'):
            body+=("    "+line+'\n')

        body = compile(body,"Event_"+self.module+'_'+self.resource,'exec')

        exec(body , self.pymodule.__dict__)

        #this lets you do things like !function module.foo
        #Basically we use self.fname as a target and assign the function to that
        self.pymodule.__dict__["_kaithem_temp_event_function"] = self.f
        x = compile(self.fname+" = _kaithem_temp_event_function","Event_"+self.module+'_'+self.resource,'exec')
        exec(x,self.pymodule.__dict__)
        del self.pymodule.__dict__["_kaithem_temp_event_function"]

        #Trigger actions let us do stuff immediately with the function, like subscribe it
        #to a weakref callback or something.
        if trigaction:
            trigaction = compile(trigaction,"Event_"+self.module+'_'+self.resource+'trigaction','exec')
            exec(trigaction,self.pymodule.__dict__)
        #initialize the module scope with the kaithem object and the module thing.
        initializer = compile(setup,"Event_"+self.module+'_'+self.resource+"setup","exec")
        exec(initializer,self.pymodule.__dict__)

    def register(self):
        with self.register_lock:
            x = compile(self.fname+" = _kaithem_temp_event_function","Event_"+self.module+'_'+self.resource,'exec')
            exec(x,self.pymodule.__dict__)
            self.disable = False
            self.active = True

    def unregister(self):
        logging.debug("Unregistering event "+repr(self))
        with self.register_lock:
            self.disable = True
            self.active = False
            #Use a try accept block because that function could have wound up anywhere,
            #Including having been already deleted.
            try:
                x = compile("del "+ self.fname,"Event_"+self.module+'_'+self.resource,'exec')
                exec(x,self.pymodule.__dict__)
            except Exception as e:
                logger.exception("Error unregistering event "+self.resource+" of "+ self.module)

    #The only difference between this and the base class version is
    #That this version propagates exceptions
    def _on_trigger(self,*args,**kwargs):
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
                self._do_action(*args,**kwargs)
                self.lastcompleted = time.time()
                #messagebus.postMessage('/system/events/ran',[self.module, self.resource])
            except Exception as e:
                logger.exception("Error in event "+self.resource+" of "+ self.module)
                if self.active:
                    self._handle_exception(e)
                raise


    def _do_action(self,*args,**kwargs):
        return self.pymodule.kaithem_event_action(*args,**kwargs)

class MessageEvent(BaseEvent,CompileCodeStringsMixin):
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):

        #This event type is not polled. Note that it doesn't even have a check() method.
        self.polled = False
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self.lastran = 0

        #Handle whatever stupid whitespace someone puts in
        #What this does is to eliminate leading whitespace, split on first space,
        #Then get rid of any extra spaces in between the command and argument.
        t = when.strip().split(' ',1)[1].strip()
        self.topic = t

        #No idea why this is done last, actually, but I'm not changing it if it works without looking into it first.
        self._init_setup_and_action(setup,do)

    def register(self):
        if hasattr(self,"action_wrapper_because_we_need_to_keep_a_reference"):
            return
        def action_wrapper(topic,message):
            #Since we aren't under the BaseEvent.check() lock, we need to get it ourselves.
            if self.disable:
                return
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


        #When the object is deleted so will this reference and the message bus's auto unsubscribe will handle it,
        #even if we don't do an unregister call, which we should.
        self.action_wrapper_because_we_need_to_keep_a_reference = action_wrapper
        #Subscribe our new function to the topic we want
        messagebus.subscribe(self.topic,action_wrapper)
        self.disable = False

    #This is the solution for the circular reference nonsense, until the messagebus has a real unsubscribe feature.
    def unregister(self):
        logging.debug("Unregistering event "+repr(self))
        if hasattr(self,"action_wrapper_because_we_need_to_keep_a_reference"):
            del self.action_wrapper_because_we_need_to_keep_a_reference
        self.disable = True

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

        if self.disable:
            return
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
        self.ev_trig =  self.pymodule._event_trigger

    def _check(self):
        """Check if the trigger is true and if so do the action."""
        #Eval the condition in the local event scope
        if self.disable:
            return
        if self.ev_trig():
            #Only execute once on false to true change unless continual was set
            if (self.continual or self._prevstate == False):
                self._prevstate = True
                self._on_trigger()
        else:
            #The eval was false, so the previous state was False
            self._prevstate = False

class ThreadPolledEvalEvent(BaseEvent,CompileCodeStringsMixin):
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self.runthread = True
        self.lock = threading.RLock()
        self.pauseflag = threading.Event()
        self.pauseflag.set()

        def f():
            d = config['priority-response'].get(self.symbolicpriority,1/60.0)
            #Run is the global run flag used to shutdown
            while(run and self.runthread):
                #The sleep comes before the check of the condition because
                #we want the fastest response when turning the event back on.
                time.sleep(d)

                #We want to wait if paused. There may be performance
                #Issues on python2 using this lock,
                #But otherwise a paused event would just wait
                #and not be deleted.
                while not self.pauseflag.wait(5.0):
                    if not (run and self.runthread):
                        return
                with self.lock:
                    try:
                        self.check()
                    except Exception as e:
                        if not (run and self.runthread):
                            return
                        logger.exception("Error in event "+self.resource+" of "+ self.module)
                        self._handle_exception(e)
                        time.sleep(config['error-backoff'].get(self.symbolicpriority,5))
        self.loop = f

        #Sometimes an event is used for its setup action and never runs.
        #If the trigger is False, it will never trigger, so we don't poll it.
        if when == 'False':
            self.polled = False
        else:
            self.polled = True
        #Compile the trigger
        x = compile("def _event_trigger():\n    return "+when,self.pymoduleName,'exec')
        exec(x,self.pymodule.__dict__)

        self._init_setup_and_action(setup,do)


    #Because of the not so perfect register/unregister mechanism here
    #We have a separate pause and unpause feature.
    def pause(self):
        self.pauseflag.clear()

    def unpause(self):
        self.pauseflag.set()

    def register(self):
        #Our entire thing runs under self.lock, so that keeps us from accidentally starting 2 threads
        #However, the self.runthread = True run regardless of the lock. A previous call to unregister could have set it False,
        #But the thread might not notice for maybe minutes or seconds.
        #In that case, if a register() call happens in that time, we want to prevent the thread stopping in the first place.

        #Note that this is not 100% threadsafe. Calling register() 0.1ms after unregister()
        #could still result in a stopped thread in theory.

        #This is because the process of stopping may take a bit of time. Calls to register() during the stopping time
        #Will 99.9% of the time prevent the stopping from happening, but 0.001% of the time might do nothing.
        #No matter what, calling them in any order from any number of threads should not deadlock.
        if not self.polled:
            return
        self.unpause()

        self.runthread = True
        if self.lock.acquire(False):
            try:
                self.thread = threading.Thread(target=self.loop,name="Event_"+self.module+'_'+self.resource)
                self.thread.start()
            finally:
                self.lock.release()
        else:
            #Try again. This is to catch it in the "stopping" state.

            time.sleep(0.001)
            if self.lock.acquire(False):
                try:
                    self.thread = threading.Thread(target=self.loop,name="Event_"+self.module+'_'+self.resource)

                    self.thread.start()
                finally:
                    self.lock.release()
        self.disable = False

    def unregister(self):
        with self.lock:
            logging.debug("Unregistering event "+repr(self))
            self.runthread = False
            self.disable = True
            self.pauseflag.clear()
            time.sleep(1/60.0)


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
        self._prevstate


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

class RecurringEvent(BaseEvent,CompileCodeStringsMixin):
    "This represents an event that happens on a schedule"
    def __init__(self,when,do,scope,continual=False,ratelimit=0,setup = "pass",*args,**kwargs):
        self.polled = False
        self.trigger = when
        self.register_lock = threading.Lock()
        BaseEvent.__init__(self,when,do,scope,continual,ratelimit,setup,*args,**kwargs)
        self._init_setup_and_action(setup,do)
        #Bound methods aren't enough to stop GC
        #TODO, Maybe this method should be asyncified?
        self.handler= self._handler
        self.exact = self.get_exact()
        
        self.selector = recur.getConstraint(when)
        self.tz=self.selector.tz

        self.nextruntime = None
        self.next = None

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
        if not self.nextruntime:
            return

        self.nextruntime = self.selector.after(self.nextruntime,False)

        if self.nextruntime == None:
            return
        self.next=scheduler.schedule(self.handler,self.nextruntime,False)

    def _handler(self):
        if not 'allow_overlap' in self.trigger:
            #If already running, just schedule the next one and go home.
            if not self.lock.acquire(False):
                self.nextruntime = self.selector.after(self.nextruntime,False)

                self.next=scheduler.schedule(self.handler, dt_to_ts(self.nextruntime,self.tz) , False)
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
            self.nextruntime = self.selector.after(self.nextruntime,False)

            if self.nextruntime == None:
                return

            if self.nextruntime:
                self.next=scheduler.schedule(self.handler, dt_to_ts(self.nextruntime,self.tz), False)
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
                self.next=scheduler.schedule(self.handler, dt_to_ts(self.nextruntime,self.tz), False)
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

    def register(self):
        logging.debug("registered")
        with self.register_lock:
            if self.nextruntime:
                return
            self.nextruntime = self.selector.after(datetime.datetime.now(),False)
            if self.nextruntime == None:
                return

            self.next=scheduler.schedule(self.handler, dt_to_ts(self.nextruntime,self.tz), False)
            logging.debug("scheduled"+repr(self.next)+str(self.nextruntime))
            self.disable = False

    def unregister(self):
        self.nextruntime = None
        try:
            self.next.unregister()
        except AttributeError:
            pass
        self.disable = True

#If the system time has been set, we may want to recalculate all of the events.
#Work in progress
def recalc_schedule():
    with _event_list_lock:
        for i in __EventReferences:
            if isinstance(__EventReferences[i],RecurringEvent):
                __EventReferences[i].recalc_time()


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
        gc.collect()

#Every event has it's own local scope that it uses, this creates the dict to represent it
def make_eventscope(module = None, resource=None):
    if module:
        if resource:

            return {'event':modules_state.scopes[module][resource],'module':modules_state.scopes[module],'kaithem':kaithemobj.kaithem}
        else:
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
                #120ms is better than nothing I guess. And we garbage collect before and after,
                #Because we want all the __del__ stuff to get a chance to take effect.
                gc.collect()
                time.sleep(0.120)
                gc.collect()
            if not o:
                #Now we make the event
                x = make_event_from_resource(module,resource)
            else:
                x = o

            if old:
                x.persistent_data = old.persistent_data

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
        except Exception as e:
            if not(module,resource) in  __EventReferences:
                d = makeDummyEvent(module,resource)
                d._handle_exception(e)

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
        return x
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
            self.loadingTraceback = None

        def f(self):
            x = make_event_from_resource(self.module,self.resource)
            x.register()
            #Now we update the references
            globals()['__EventReferences'][self.module,self.resource] = x
            self.evt = x

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

            toLoad =sorted(toLoad,key= lambda x: (x.module,x.resource))
            nextRound = []
            #for each allowed loading attempt, we loop over
            #the events and try to set them up. If this fails,
            #add to the retry list and retry next round. This means they will be attempted again
            #up to the maximum number of tries. The important part is that we don't
            #retry immediately, but only after trying the remaining list of events.
            #This is because inter-event dependancies are the most common reason for failure.

            attempts = max(1,config['max-load-attempts'])
            for baz in range(0,attempts):
                if not toLoad:
                    break
                logging.debug("Event initialization resolution round "+str(baz))
                for i in toLoad:
                    try:
                        logging.debug("Loading "+i.module + ":"+i.resource)
                        slt = time.time()
                        i.f()
                        messagebus.postMessage("/system/events/loaded",[i.module,i.resource])
                        logging.debug("Loaded "+i.module + ":"+i.resource +" in "+str(round(time.time()-slt, 2))+"s")
                        time.sleep(0.005)
                    #If there is an error, add it t the list of things to be retried.
                    except Exception as e:
                        if sys.version_info > (3,0):
                            i.error = traceback.format_exc(chain = True)
                        else:
                            i.error = traceback.format_exc()
                        if baz == attempts-1:
                            i.loadingTraceback = traceback.format_exc()

                        nextRound.append(i)
                        logging.debug("Could not load "+i.module + ":"+i.resource+" in this round, deferring to next round\n"+"failed after"+str(round(time.time()-slt, 2))+"s\n"+traceback.format_exc())

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
    logging.info("Created events from modules")

def make_event_from_resource(module,resource,subst=None):
    """Returns an event object when given a module and resource name pointing to an event resource.
    Also, if subst is a dict, will use the dict given in subst instead of looking it up.

    The reason for this is so that you can try test compiling without having to actually change the resource.
    """
    t=time.time()
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
    x.timeTakenToLoad = time.time()-t
    return x
