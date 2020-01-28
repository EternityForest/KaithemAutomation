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

"This file manages the kaithem global message bus that is used mostly for logging but also for many other tasks."

import weakref,threading,time,os,random,traceback,logging,inspect,types,copy
from typing import Callable,Optional

from typeguard import typechecked

from . import workers
from collections import defaultdict, OrderedDict

_subscribers_list_modify_lock = threading.RLock()
cachelock = threading.RLock()
#OrderedDict doesn't seem as fast as dict. So I have a cache of the cache
parsecache = OrderedDict()
parsecachecache = {}

log =logging.getLogger("system.messagebus")
def normalize_topic(topic):
    """"Because some topics are equivalent("/foo" and "foo"), this lets us convert them to the canonical "/foo" representation.
    Note that "/foo/" is not the same as "/foo", because a trailing slash indicates a "directory"."""
    topic = topic.strip()
    if not topic.startswith('/'):
        return '/'+topic
    else:
        return topic

def _shouldReRaiseAttrErr():
    return True

def defaultErrorHandler(*a):
    print(traceback.format_exc())
    
subscriberErrorHandlers = []

def handleError(f,topic,value):
    log.exception("Message bus subscriber error")
    for i in subscriberErrorHandlers:
        try:
            i(f,topic,value)
        except:
            print(traceback.format_exc())

def runFunction(f,a):
    return f(*a)

class MessageBus(object):
    def __init__(self,executor:Optional[Callable] = None):
        """You pass this a function of one argument that just calls its argument. Defaults to calling in
        same thread and ignoring errors.
        """
        if executor==None:
            def do(self, f):
                try:
                    f()
                except:
                    pass
            self.executor = do
        else:
            self.executor = executor

        self.subscribers = defaultdict(list)
        self.subscribers_immutable = {}

    @typechecked
    def subscribe(self,topic:str,callback:Callable):
        topic=normalize_topic(topic)
       
        with _subscribers_list_modify_lock:
            wrappedCallback = self.wrap_callback(callback,topic)

           
            self.subscribers[topic].append(wrappedCallback)
            self.subscribers_immutable = copy.deepcopy(self.subscribers)

    def unsubscribe(self,topic, function):
            "Unsubscribe topic from function"
            try:
                with _subscribers_list_modify_lock:
                    target = None
                    for j in self.subscribers[topic]:
                        if j.originalFunction()==function:
                            target = j
                    if target:
                        self.subscribers[topic].remove(target)
                    else:
                        raise ValueError("No such subscriber found")
            except:
                pass
            #There is a very slight chance someone will
            #Add something to topic before we delete it but after the test.
            #That would result in a canceled subscription
            #So we use this lock.
            try:
                with _subscribers_list_modify_lock:
                    if not self.subscribers[topic]:
                        self.subscribers.pop(topic)
            except AttributeError as e:
                #This try and if statement are supposed to catch nuisiance errors when shutting down.
                if _shouldReRaiseAttrErr():
                    raise e
 
            finally:
                with _subscribers_list_modify_lock:
                    self.subscribers_immutable = copy.deepcopy(self.subscribers)

    @staticmethod
    def parseTopic(topic):
        "Parse the topic string into a list of all subscriptions that could possibly match."
        global parsecache
        #Since this is a pure function(except the caching itself) we can cache it
        if topic in parsecache:
            return parsecache[topic]
        
        #Let's cache by the original version of the topic, so we don't have to convert it to the canonical
        oldtopic = topic
        topic=normalize_topic(topic)

        #A topic foo/bar/baz would go to
        #foo, foo/bar, and /foo/bar/baz
        #So we need to make a list like that
        matchingtopics = set(['/#'])
        parts = topic.split("/")
        last = ""

        #Add the exact one
        matchingtopics.add(topic)
        
        
        for i in parts:
            last += (i+'/')
            matchingtopics.add(last+"#")
        parsecache[oldtopic] = matchingtopics
        #Don't let the cache get too big.
        #Getting rid of the oldest should hopefully converge to the most used topics being cached
        if len(parsecache) > 600:
            parsecache.popitem(last=False)
        return matchingtopics

    @typechecked
    def wrap_callback(self,f:Callable,topic:str):
        """return function g that calls f with (topic,message) or just f(topic), depending
        on how many args there are.
         and if errors is true logs the error"""

        args = len(inspect.signature(f).parameters)


        #Allright, here is how this works.
        #We have to deal with the possibility that, at any time,
        #The callback will cease to exist. That, in fact, is how one unsubscribes.
        #So, we make this here closure that knows the topic, and
        #When the GC goes Om Nom Nom on the function, we get passed the weakref to it.
        #Then we get rid of the empty weakref and if that causes the entire topic
        #To have no subscribers, delete that too in case of memory leak.
        def delsubscription(weakrefobject):
            try:
                with _subscribers_list_modify_lock:
                    self.subscribers[topic].remove(weakrefobject)
            except:
                pass
            #There is a very slight chance someone will
            #Add something to topic before we delete it but after the test.
            #That would result in a canceled subscription
            #So we use this lock.
            try:
                with _subscribers_list_modify_lock:
                    if not self.subscribers[topic]:
                        self.subscribers.pop(topic)
            except AttributeError as e:
                #This try and if statement are supposed to catch nuisiance errors when shutting down.
                if _shouldReRaiseAttrErr():
                    raise e
               
            finally:
                with _subscribers_list_modify_lock:
                    self.subscribers_immutable = copy.deepcopy(self.subscribers)



        if isinstance(f,types.MethodType):
            f=weakref.WeakMethod(f,delsubscription)
        else:
            f = weakref.ref(f,delsubscription)

        #Mutable object that gets saved to the closure for keeping track of if we already loggged this
        alreadyLogged=[False]
        if args==0:
            def g(topic, message,errors,timestamp,annotation):
                try:
                    f2 = f()
                    if f2:
                        f2()
                except:
                    try:
                        if errors:
                            if not alreadyLogged[0]:
                                handleError(f2, topic,message)
                            alreadyLogged[0]=True
                    except Exception as e:
                            print("err",e)
        elif args==2:
            def g(topic, message,errors,timestamp,annotation):
                try:
                    f2 = f()
                    if f2:
                        f2(topic,message)
                except:
                    try:
                        if errors:
                            if not alreadyLogged[0]:
                                handleError(f,topic,message)
                            alreadyLogged[0]=True

                    except Exception as e:
                            print("err",e)
        elif args==4:
            def g(topic, message,errors,timestamp,annotation):
                try:
                    f2 = f()
                    if f2:
                        f2(topic,message,timestamp,annotation)
                except:
                    try:
                        if errors:
                            if not alreadyLogged[0]:
                                handleError(f,topic,message)
                            alreadyLogged[0]=True

                    except Exception as e:
                            print("err",e)
        elif args==1:
            def g(topic, message,errors,timestamp,annotation):
                try:
                    f2 = f()
                    if f2:
                        f2(message)
                except:
                    try:
                        if errors:
                            if not alreadyLogged[0]:
                                handleError(f,topic,message)
                            alreadyLogged[0]=True
                    except Exception as e:
                            print("err",e)
        else:
            raise ValueError("Invalid function signature(0,1,2, or 4 args supported)")

        #Ref to the weakref so it's easy to check if the function we are wrapping
        #Still exists.
        g.originalFunction = f    
        return g



    def _post(self, topic,message,errors,timestamp,annotation,executor=None):

        executor = executor or self.executor

        matchingtopics = self.parseTopic(topic)
        #We can't iterate on anything that could possibly change so we make copies
        d = self.subscribers_immutable
        for i in matchingtopics:
            if i in d:
                #When we find a match, we make a copy of that subscriber list
                x = d[i][:]
                #And iterate the copy
                for f in x:
                    #we call the ref to get its refferent
                    #An error could happen in the subscriber
                    #Or a typeerror could because the weakref has been collected
                    #We ignore both of these errors and move on
                    executor(f,(topic,message,errors,timestamp,annotation))

    def postMessage(self, topic, message,errors=True, timestamp=None,annotation=None, synchronous=False):
        #Use the executor to run the post message job
        #To allow for the possibility of it running in the background as a thread
        topic=normalize_topic(topic)
        try:
            topic = str(topic)
        except Exception:
            raise TypeError("Topic must be a string or castable to a string.")

        timestamp = timestamp or time.monotonic()
        self._post(topic,message,errors,timestamp, annotation, runFunction if synchronous else None)


#Setup the default system messagebus
_bus = MessageBus(workers.do)
subscribe = _bus.subscribe
unsubscribe = _bus.unsubscribe
postMessage = _bus.postMessage
