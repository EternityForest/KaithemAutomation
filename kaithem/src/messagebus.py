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

import weakref,threading,time,os,random,json
from . import workers
from collections import defaultdict, OrderedDict


_subscribers_list_modify_lock = threading.Lock()
parsecache = OrderedDict()

class MessageBus(object):
    
    def __init__(self,executor = None):
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
        
    def subscribe(self,topic,callback):
        if topic.startswith('/'):
            if not len(topic)==1:
                topic = topic[1:]
        #Allright, here is how this works.
        #We have to deal with the possibility that, at any time,
        #The callback will cease to exist. That, in fact, is how one unsubscribes.
        #So, we make this here closure that knows the topic, and
        #When the GC goes Om Nom Nom on the function, we get passed the weakref to it.
        #Then we get rid of the empty weakref and if that causes the entire topic
        #To have no subscribers, delete that too in case of memory leak.
        def delsubscription(weakrefobject):
            try:
                self.subscribers[topic].remove(weakrefobject)
            except:
                pass
            #There is a very slight chance someone will
            #Add something to topic before we delete it but after the test.
            #That would result in a canceled subscription
            #So we use this lock.
            with _subscribers_list_modify_lock:
                if not self.subscribers[topic]:
                    self.subscribers.pop(topic)
        
        self.subscribers[topic].append(weakref.ref(callback,delsubscription))
    
    @staticmethod
    def parseTopic(topic):
        "Parse the topic string into a list of all subscriptions that could possibly match."

        #normalize topic
        if topic.startswith('/'):
            topic = topic[1:]
            
        #Since this is a pure function(except the caching itself) we can cache it
        if topic in parsecache:
            return parsecache[topic]

        #A topic foo/bar/baz would go to
        #foo, foo/bar, and /foo/bar/baz
        #So we need to make a list like that
        matchingtopics = set(['/'])
        parts = topic.split("/")
        last = ""
        matchingtopics.add(topic)
        for i in parts:
            last += (i+'/')
            matchingtopics.add(last)
        parsecache[topic] = matchingtopics
        #Don't let the cache get too big.
        #Getting rid of the oldest should hopefully converge to the most used topics being cached
        if len(parsecache) > 1200:
            parsecache.popitem(last=False) 
        return matchingtopics
    
    def _post(self, topic,message):
        matchingtopics = self.parseTopic(topic)
        
        #We can't iterate on anything that could possibly change so we make copies
        d = self.subscribers.copy()
        for i in matchingtopics:
            if i in d:
                #When we find a match, we make a copy of that subscriber list
                x = d[i][:]
                #And iterate the copy
                for ref in x:
                    #we call the ref to get its refferent
                    #An error could happen in the subscriber
                    #Or a typeerror could because the weakref has been collected
                    #We ignore both of these errors and move on
                    try:
                        f =ref()(topic,message)
                    except:
                        pass
                    
    
    def postMessage(self, topic, message):
        #Use the executor to run the post message job
        #To allow for the possibility of it running in the background as a thread
        
        #A little more checking than usual here because the message bus is so central.
        #Also, if anyone implements logging they will appreciate no crap on the bus.
        try:
            topic = str(topic)
        except Exception:
            raise TypeError("Topic must be a string or castable to a string.")
        
        #Ugly way to find if json serializable. Just try it
        try:
            json.dumps(message)
        except Exception:
            raise ValueError("Message must be serializable as JSON")
        
        def f():
            self._post(topic,message)
        f.__name__ = 'Publish_'+topic
        self.executor(f)
        
        
        

_bus = MessageBus(workers.do)      
subscribe = _bus.subscribe
postMessage = _bus.postMessage
        
    
        
    

