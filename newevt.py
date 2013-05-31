import threading
import workers
import modules,threading,time
import kaithem

event_list_lock = threading.Lock()
events = []

#Let us now have a way to get at actie event objects by means o their origin resource and module.
EventReferences = {}


#In a background thread, we use the worker pool to check all threads

run = True
def __manager():
    while run:
        event_list_lock.acquire()
        try:
            for i in events:
                workers.do(i.check)
        except:
            print("e")
        finally:
            event_list_lock.release()
            time.sleep(0.025)

t = threading.Thread(target = __manager)
t.daemon = True
t.start()

def makeEventScope(module):
    with modules.modulesLock:
       return {'module':modules.scopes[module],'kaithem':kaithem.kaithem}

def updateOneEvent(resource,module):
    with modules.modulesLock:
        j = modules.ActiveModules[module][resource]
        x = Event(j['trigger'],j['action'],makeEventScope(module))
        event_list_lock.acquire()
        
        try:
            if module in EventReferences:
                if resource in EventReferences[module]:
                    if EventReferences[module][resource] in events:
                        events.remove(EventReferences[module][resource])
                      
            events.append(x)
            EventReferences[module][resource] = x
             
        finally:
            event_list_lock.release ()

#look in the modules and compile all the event code
def getEventsFromModules():
    with modules.modulesLock:
        event_list_lock.acquire()
        global events
        events = []
        try:
            for i in modules.ActiveModules.copy():
                EventReferences[i] = {} # make an empty place or events in this module
                for m in modules.ActiveModules[i].copy():
                    j=modules.ActiveModules[i][m]
                    if j['resource-type']=='event':
                        x = Event(j['trigger'],j['action'],makeEventScope(i))
                        events.append(x)
                        #Same event object, different set of references
                        EventReferences[i][m] = x
        finally:
            event_list_lock.release()
        
class Event():
    """Class represeting one checkable event. when and do must be python code strings,
    scope must be a dict representing the scope in which both the trigger and action will be executed.
    When the trigger goes from fase to true, the action will occur.
    
    optional params:
    ratelimit: Do not do the action more often than every X seconds
    continual: Execute as often as possible while condition remains true
    
    """
    def __init__(self,when,do,scope,continual=False,ratelimit=0,):
        self.scope = scope
        self._prevstate = False
        #Precompile
        self.trigger = compile(when,"<str>","eval")
        self.action = compile(do,"<str>","exec")
        self.continual = continual
        #This lock makes sure that only one copy executes at once
        self.lock = threading.Lock()
        self.lastexecuted = 0
        self.ratelimit = ratelimit
        
    def check(self):
        """Check if the trigger is true and if so do the action."""
        try:
            self.lock.acquire()
            if eval(self.trigger,self.scope,self.scope):
                #Only execute once on false to true change unless continual was set
                if (self.continual or self._prevstate == False):
                    if (time.time()-self.lastexecuted >self.ratelimit):
                        exec(self.action,self.scope,self.scope)
                        self.lastexecuted = time.time()
                self._prevstate = True
            else:
                self._prevstate = False
        finally:
            self.lock.release()
