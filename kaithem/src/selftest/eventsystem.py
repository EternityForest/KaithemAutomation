#Copyright Daniel Dunn 2019
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

#This file runs a self test when python starts

import time,traceback,logging, threading,weakref

running_tests=[]

def eventSystemTest():
    from .. import newevt
    try:
        _eventSystemTest()
    finally:
        newevt.removeOneEvent('testevt','testevt')
        newevt.removeOneEvent('TEST1','TEST1')
        newevt.removeOneEvent('TEST2','TEST2')

def _eventSystemTest():
    from .. import newevt,messagebus,modules_state
    logging.info("Beginning self test of event system")
    running_tests.append(1)
    modules_state.scopes['x'] = {}
    #Create an event that sets y to 0 if it is 1
    with newevt._event_list_lock:
        x = newevt.Event("y==1","global y\ny=0",locals(),setup="y=0")
        x.module=x.resource="testevt"
        newevt.EventReferences[x.module,x.resource] = x

        #Register event with polling.
        x.register()
    #Set y to 1
    x.pymodule.y = 1

    time.sleep(2)
    


    try:    
        #y should immediately be set back to 0 at the next polling cycle
        if x.pymodule.y == 1:
                raise RuntimeError("Edge-Triggered Event did nothing")
    except:
        print(x.pymodule.__dict__)
        raise
    finally:
        x.unregister()



    x.pymodule.y =1
    if not x.pymodule.y == 1:
            raise RuntimeError("Edge-Triggered Event did not go away when unregistered")

    blah = [False]

    def f():
        return blah[0]

    def g():
        blah[0]=False

    newevt.when(f,g)
    time.sleep(0.5)
    blah[0]=True

    time.sleep(0.5)
    if blah[0]:
        time.sleep(2)
        if blah[0]:
            raise RuntimeError("One time event did not trigger")

    blah[0]=True
    time.sleep(1)
    if not blah[0]:
        raise RuntimeError("One time event did not delete itself properly")

    newevt.after(1,g)
    blah[0]=True
    time.sleep(1.5)
    if blah[0]:
        raise RuntimeError("Time delay event did not trigger")

    blah[0] = True
    time.sleep(2)
    if not blah[0]:
        raise RuntimeError("Time delay event did not delete itself properly")

    with newevt._event_list_lock:
        #Same exact thing exept we use the onchange
        x = newevt.Event("!onchange y","global y\ny=5")
         #Give it a value to change from
        x.pymodule.y = 0
        
        x.module=x.resource="TEST1"
        newevt.EventReferences[x.module,x.resource] = x

        #Register event with polling.
        x.register()
   
    #Let it notice the old value
    time.sleep(1)
    #Set y to 1
    x.pymodule.y = 1

    time.sleep(1)
    #y should immediately be set back to 0 at the next polling cycle
    x.unregister()

    if x.pymodule.y == 1:
            raise RuntimeError("Onchange Event did nothing")

 

    x.pymodule.y =1
    if not x.pymodule.y == 1:
            raise RuntimeError("Onchange Event did not go away when unregistered")


    #There is a weird old feature where message events don't work if not in EventReferences
    #It was an old thing to caths a circular reference bug.
    with newevt._event_list_lock:
        #Now we test the message bus event
        x = newevt.Event("!onmsg /system/selftest","global y\ny='test'",setup="testObj=lambda x:0")
        x.module=x.resource = 'TEST2'
        #Make sure nobody is iterating the eventlist
        #Add new event
        x.register()
        #Update index
        newevt.EventReferences[x.module,x.resource] = x
    
    testObj = weakref.ref(x.pymodule.__dict__['testObj'])


    time.sleep(0.25)
    #Give it a value to change from
    messagebus.postMessage("/system/selftest",'foo')
    #Let it notice the old value

    time.sleep(0.25)
    x.unregister()
    #y should immediately be set back to 0 at the next polling cycle
    if not hasattr(x.pymodule,'y'):
            time.sleep(5)
            if not hasattr(x.pymodule,'y'):
                raise RuntimeError("Message Event did nothing or took longer than 5s")
            else:
                raise RuntimeError("Message Event had slow performance, delivery took more than 0.25s")

    try:
           x.pymodule.y =1
    except:
        #This might fail if the implementatino makes pymodule not exist anymore
        pass
    x.cleanup()

    #Make sure the weakref isn't referencing
    if testObj():
        raise RuntimeError("Object in event scope still exists after module deletion")

    messagebus.postMessage('foo',"/system/selftest")
    #If there is no y or pymodule, this test won't work but we can probably assume it unregistered correctly.
    #Maybe we should add a real test that works either way?
    if hasattr(x, 'pymodule') and hasattr(x.pymodule,'y'):            
        if x.pymodule.y == 'test':
                raise RuntimeError("Message Event did not go away when unregistered")


    running_tests.pop()




