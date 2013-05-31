#This file manages a work queue that feeds a threadpool
#Tasks will be performed on a best effort basis and errors will be caught and ignored.
import threading,sys

#2 and 3 have basically the same module with diferent names
if sys.version_info < (3,0):
    import Queue
    queue = Queue
else:
    import queue
    
__queue = queue.Queue(120)

run = True

#one worker that just pulls tasks from the queue and does them. Errors are caught and
#We assume the yasks have their own error stuff
def __workerloop():
    while(run):
        try:
            __queue.get()()
        except:
            pass

#Wrap queue.put because it looks nicer
def do(func):
    __queue.put(func)

#Start 8 threads. Can we make this user settable?
for i in range(0,8):
    t = threading.Thread(target = __workerloop)
    t.daemon = True
    t.start()