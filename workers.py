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

#This file manages a work queue that feeds a threadpool
#Tasks will be performed on a best effort basis and errors will be caught and ignored.


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
#We assume the tasks have their own error stuff
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
