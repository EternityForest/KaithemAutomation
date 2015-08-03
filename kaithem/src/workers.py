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

#This file manages a work queue that feeds a threadpool
#Tasks will be performed on a best effort basis and errors will be caught and ignored.


#This file manages a work queue that feeds a threadpool
#Tasks will be performed on a best effort basis and errors will be caught and ignored.
import threading,sys,cherrypy,traceback
import atexit,time
from .config import config

def inWaiting():
    return len(__queue)

#2 and 3 have basically the same module with diferent names
if sys.version_info < (3,0):
    import Queue
    queue = Queue
else:
    import queue

__queue = queue.Queue(config['task-queue-size'])
run = True

def EXIT():
    #Tell all worker threads to stop and wait for them all to finish.
    #If they aren't finished within the time limit, just exit.
    global run
    run = False
    t = time.time()
    for i in workers:
        try:
            #All threads total must be finished within the time limit
            i.join(config['wait-for-workers'] - (time.time()-t) )
            #If we try to exit befoe the thread even has time to start or something
        except RuntimeError:
            pass

atexit.register(EXIT)
cherrypy.engine.subscribe("exit",EXIT)

#one worker that just pulls tasks from the queue and does them. Errors are caught and
#We assume the tasks have their own error stuff
def __workerloop():
    while(run):
        try:
            #We need the timeout othewise it could block forever
            #and thus not notice if run was False
            f=__queue.get(timeout = 5)
            f()
        except Exception as e:
            try:
                import messagebus
                messagebus.postMessage('system/errors/workers'+
                                           {"function":f.__name__,
                                            "module":f.__module__,
                                            "traceback":traceback.format_exc()})
            except:
                pass

#Wrap queue.put because it looks nicer
def do(func):
    __queue.put(func)

def waitingtasks():
    return __queue.qsize()

#This is a decorator to make an asychronous version of a function
def async(f):
    def g():
        __queue.put(func)
    return g



workers = []
#Start a number of threads as determined by the config file
for i in range(0,config['worker-threads']):
    t = threading.Thread(target = __workerloop, name = "ThreadPoolWorker-"+str(i))
    workers.append(t)
    t.start()
