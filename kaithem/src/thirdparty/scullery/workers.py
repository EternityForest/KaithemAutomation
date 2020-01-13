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

import threading,sys,traceback, logging
import atexit,time
import random

#I'm reserving the system log for a reasonable low-rate log.
#So this is in a separate namespace that shows up elsewhere.
logger = logging.getLogger("workers")

syslogger = logging.getLogger("system")

lastWorkersError = 0 
backgroundFunctionErrorHandlers=[]

def inWaiting():
    return len(__queue)

#2 and 3 have basically the same module with diferent names
if sys.version_info < (3,0):
    import Queue
    queue = Queue
else:
    import queue

def handleErrorInFunction(f):
    print("Error in: " +str(f))

def stop():
    global run
    logging.info("Stopping worker threads")
    run = False

def EXIT():
    #Tell all worker threads to stop and wait for them all to finish.
    #If they aren't finished within the time limit, just exit.
    t = time.time()
    stop()
    for i in workers:
        try:
            #All threads total must be finished within the time limit
            i.join(worker_wait - (time.time()-t) )
            #If we try to exit befoe the thread even has time to start or something
        except RuntimeError:
            pass


def makeWorker(e,q):
    #one worker that just pulls tasks from the queue and does them. Errors are caught and
    #We assume the tasks have their own error stuff
    e.on=True


    def workerloop():
        f=None


        while(run):
            try:
                #We need the timeout othewise it could block forever
                #and thus not notice if run was False
                # try:
                #     e.on = True
                #     f=__queue.get(block=False)
                # except queue.Empty:
                #     e.clear()
                #     e.on = False
                #     e.wait(timeout=5)
                e.on=True
                #While either our direct  queue or the overflow queue has things in it we do them.
                while(q or overflow_q):
                    if q:
                        f=q.pop(False)

                    elif overflow_q:
                        f=overflow_q.pop(False)
                    if f:
                        #That pass statement is important. Things break if it goes away.
                        pass
                        f[0](*f[1])
                e.on=False
                if not len(ready_threads)>1000:
                    ready_threads.append((q,e))
                e.clear()
                e.wait(timeout=5)
            except Exception:
                global lastWorkersError
                try:
                    if lastWorkersError<time.monotonic()-60:
                        syslogger.exception("Error in function. This message is ratelimited, see debug logs for full.\r\nIn "+f[0].__name__ +" from " + f[0].__module__ +"\r\n")
                        lastWorkersError= time.monotonic()

                    logger.exception("Error in function running in thread pool "+f[0].__name__ +" from " + f[0].__module__)
                except:
                    print("Failed to handle error: "+traceback.format_exc(6))

                for i in backgroundFunctionErrorHandlers:
                    try:
                        i(f)
                    except:
                        print("Failed to handle error: "+traceback.format_exc(6))
            finally:
                #We do not want f staying around, if might hold references that should be GCed away immediatly
                f=None
    return workerloop


ready_threads = []




def waitingtasks():
    "Return the number of tasks in the task queue"
    return __queue.qsize()

#This is a decorator to make an asychronous version of a function
def asyncDecorator(f):
    """Given a function f, return a function g that asyncronously executes f. Basically calling g will immediately run f in the thread pool."""
    def g():
        def h(*args,**kwargs):
            f(*args,**kwargs)
        __queue.put(h)
    return g
overflow_q =[]
workers = []
queues = []

def startDummy():
    "Start the worker pool in dummy mode, that is, don't actually use threads, and have do() run things right in the calling thread"
    global do, do_try

    def do(func):
        func()
    do_try = do

def start(count=8, qsize=64, shutdown_wait=60):
    global do, do_try
    #Start a number of threads as determined by the config file
    def do(func,args=[]):
        """Run a function in the background

        funct(function):
            A function of 0 arguments to be ran in the background in another thread immediatly,
        """
        # try:
        #     __queue.put(func,block=False)
        # except:
        #     time.sleep(random.random()/100)
        #     __queue.put(func)

        if ready_threads:
            try:
                t = ready_threads.pop()
                t[0].append((func,args))
                t[1].set()
                return
            except IndexError:
                pass

        #No unbusy threads? It must go in the overflow queue.
        #Soft rate limit here should work a bit better than the old hard limit at keeping away
        #the deadlocks.

        if len(overflow_q)>1000:
            #ratelimit if the queue gets over
            time.sleep(max(0,(len(overflow_q)-1000)/2000.0))
        overflow_q.append((func,args))

        #Be sure there is an awake thread to deal with our overflow entry.
        for i in queues:
            if not i[0].on:
                i[0].set()
                return

    def do_try(func,args=[]):
        """Run a function in the background

        funct(function):
            A function of 0 arguments to be ran in the background in another thread immediatly,
        """
        __queue.put((func, args))
        
    global __queue, run,worker_wait
    run = True
    worker_wait = shutdown_wait
    __queue = queue.Queue(qsize)
    for i in range(0,count):
        q = []
        e = threading.Event()
        t = threading.Thread(target = makeWorker(e,q), name = "ThreadPoolWorker-"+str(i))
        workers.append(t)
        queues.append((e,q))
        t.start()
    syslogger.info("Started worker threads")
