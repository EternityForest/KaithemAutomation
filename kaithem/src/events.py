#This file was a sketch. do not import it it will not compile. replaced by newevt

import userglobaldata
import threading
import sys

#2.xx and 3.xx compatibility
if sys.version_info[0] ==2:
        import Queue
        queue = Queue
else:
        import queue


class KaithemEventManager():
    """Manage the polling of events"""
    
    
    def addEvent(name,eventObject):
        """Register a KaithemEvent object by name"""
        #Create a lock object along with the event
        self.__evtdictlock.aquire()
        self.__events[name] = (eventObject,threading.Lock())
        self.__evtdictlock.release()
    
    def __init__(self,numthreads):
        #Make a work queue but don't let it get too big
        self.__workqueue = queue.Queue(numthreads *2)
        #This lock is used to esure only one thread accesses the dict of events
        self.__evtdictlock = threading.Lock()
        self.__events = {}
        #Create worker pool
        for i in range(numthreads):
            self.__spawnthread()
            
    def __spawnthread(self):
            """Create a new worker thread"""
            x = threading.Thread(self.__mainloop())
            x.run()
    
    def __spawnmanager(self):
        """Create the manager thread. I don't think there is any good reason for >1"""
        x = threading.Thread(self.__managerloop())
        x.run()

    def __managerloop(self):
        #This loop puts things the queue
        #it uses the lock to ensure no two threads use the evt dict at the same time.
        while self.running:
            try:
                self.__evtdictock.aquire()
                for i,j in events.items():
                    self.__workqueue.put(j)
                self.__evtdictlock.release()
            except:
                self.__evtdictlock.release()
                break
            
        #If the loop broke due to error, restart it.
        if self.running:
            self.__spawnmanager(self)
                
    def __mainloop(self):
        #Create a way to stop oe thread
        data = threading.local()
        data.running = True
        while(data.running):
                try:
                    #Get a task from the work queue(includes both the check and action)
                    temp =  self.__workqueue.get()
                    #call its check method which will perform the proper action
                    #should the condition evaluate true
                    #Also, aquire and release a lock that makes sure
                    #Only one thread works on an event at a time
                    temp[1].aquire()
                    temp[0].check()
                    temp[1].release()
                    
                #Break thread, and thus exit the while and restart the thread if anything bad
                #Happens.
                except Exception,e:
                    #This should have a lock, but if you have enough errors to need it
                    #you have biger problems especially with tasks executing many times per second
                    self.errorcount += 1
                    break;
        #Should for any reason the while exit, spaw a new thread before exiting to replace self
        if self.running():
            self.__spawnthread
        
class BaseKaithemEvent():
    pass


class KaithemEvent(BaseKaithemEvent):
    """Encapsulates an action consisting of python code triggered when the result is true
       if once is true, will only perform action when trigger goes from negative positive.
       Otherwise it will be performed every polling cycle while trigger evaluates true.
       minInterval will be used as an upper limit for how often to perform action
       
       Each event gets its own local context(KaithemEvent.data)
       but you must pass a reference for it use as its global context.
    """
    class Triggers():
        #give the user some more complex triggers that she might not wat to code herself
        def __init__(self):
            self.changednevercalled = True
        def changed(self,value):
            if self.changednevercalled:
                self.changedlastinput == value
                self.changednevercalled = False
            if value == self.changedlastinput:
                return False
            else:
                self.changedlastinput == value
                return True
                
    def __init__(self,trigger,globals,action,once = True,minInterval=0):
        #Precompile the trigger and action
        self._trigger = compile(trigger,'<string>','eval')
        self._action = compile(action,'<string>','exec')
        self.lastState = False #Record the last state of the regex
        self.once = once
        self.minInterval = minInterval
        x = self.Triggers
        #This is the dict for the local context
        #We give it an instance of Triggers so you can e.g. have triggers.changed(xyz)
        self.data = {'triggers':x}
        self.globals = globals
    
    #Check if we need to do the action
    #self has been renamed to 
    def check(self):
        #this is NOT an unused variable
        #it is so eval has a convinient place to put stuff under thisEvent
        thisEvent = self.data
        #temp is a common name and might conflict with somethig in the eval
        #So we use this big huge name and hope nobody wants to get at a global by that name
        #Note the execution context for both trigger and action:
        #The userglobal dict is used as globals, but events get their own
        #local data pool.
        temp = eval(self.trigger,self.globals,d,self.data)
        if temp:
            #We only want to trigger once when it goes true
            #Unless once has been set to false
            if (self.LastState == False) or (self.once == False):
                #if it has been long enough since it was last triggered.
                now = time.time()
                if self.lastTriggered <= ( now- self.minInterval):
                    self.lastTriggered = now
                    exec(self.action,self.globals,self.data)
            self.lastState = temp

