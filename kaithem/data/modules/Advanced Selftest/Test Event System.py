## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1610584797158481, resource-type: event}

"""

__trigger__='kaithem.misc.uptime()>90'

if __name__=='__setup__':
    #This code runs once when the foot loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    from src import newevt,messagebus,modules_state
    import time,traceback
    
    running_tests=[]
    def theTest():
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
            x = newevt.Event("!onmsg /test","global y\ny='test'")
            x.module=x.resource = 'TEST2'
            #Make sure nobody is iterating the eventlist
            #Add new event
            x.register()
            #Update index
            newevt.EventReferences[x.module,x.resource] = x
        time.sleep(0.25)
        #Give it a value to change from
        messagebus.postMessage("/test",'foo')
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
    
        messagebus.postMessage('foo',"/test")
        #If there is no y or pymodule, this test won't work but we can probably assume it unregistered correctly.
        #Maybe we should add a real test that works either way?
        if hasattr(x, 'pymodule') and hasattr(x.pymodule,'y'):            
            if x.pymodule.y == 'test':
                    raise RuntimeError("Message Event did not go away when unregistered")
    
    
        print("Success in testing event system")
        running_tests.pop()
    def runtest():
        try:
            theTest()
        except:
            messagebus.postMessage("/system/notifications/errors",    traceback.format_exc(6))
        finally:
            newevt.removeOneEvent('testevt','testevt')
            newevt.removeOneEvent('TEST1','TEST1')
            newevt.removeOneEvent('TEST2','TEST2')

def eventAction():
    time.sleep(3)
    kaithem.misc.do(runtest)
