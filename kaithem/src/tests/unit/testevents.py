import common
from src import newevt,messagebus
import time

#Create an event that sets y to 0 if it is 1
x = newevt.Event("y==1","y=0",locals(),setup="y=0")

#Register event with polling.
x.register()
#Set y to 1
x.pymodule.y = 1

time.sleep(0.1)
#y should immediately be set back to 0 at the next polling cycle 
if x.pymodule.y == 1:
        common.fail("Edge-Triggered Event did nothing")
        
#Unregister event and make sure it really goes away
x.unregister() 
x.pymodule.y =1
if not x.pymodule.y == 1:
        common.fail("Edge-Triggered Event did not go away when unregistered")
        
##Testing one time events
x.pymodule.y = False
def f():
    return x.pymodule.y

def g():
    x.pymodule.y = False
    print('anus')
    
newevt.when(f,g)
time.sleep(0.1)
x.pymodule.y = True
time.sleep(0.5)
if x.pymodule.y:
    common.fail("One time event did not trigger")
x.pymodule.y = True
time.sleep(0.5)
if not x.pymodule.y:
    common.fail("One time event did not delete itself properly")

newevt.after(1,g)
x.pymodule.y = True
time.sleep(1.2)
if x.pymodule.y:
    common.fail("Time delay event did not trigger")
    
x.pymodule.y = True
time.sleep(1.2)
if not x.pymodule.y:
    common.fail("Time delay event did not delete itself properly")
        
#Same exact thing exept we use the onchange
x = newevt.Event("!onchange y","y=5",locals())


#Register event with polling.
x.register()
#Give it a value to change from
x.pymodule.y = 0
#Let it notice the old value
time.sleep(0.10)
#Set y to 1
x.pymodule.y = 1

time.sleep(0.10)
#y should immediately be set back to 0 at the next polling cycle 
if x.pymodule.y == 1:
        common.fail("Onchange Event did nothing")
        
#Unregister event and make sure it really goes away
x.unregister() 
x.pymodule.y =1
if not x.pymodule.y == 1:
        common.fail("Onchange Event did not go away when unregistered")
   
   
   
        
#Now we test the message bus event
x = newevt.Event("!onmsg /test","y='test'",locals())


#Register event with polling.
x.register()
#Give it a value to change from
messagebus.postMessage("/test",'poo')
#Let it notice the old value

time.sleep(0.25)
#y should immediately be set back to 0 at the next polling cycle 
if not  x.pymodule.y == 'test':
        common.fail("Message Event did nothing")
    
#Unregister event and make sure it really goes away
x.unregister() 
x.pymodule.y =1

messagebus.postMessage('poo',"/test")
if x.pymodule.y == 'test':
        common.fail("Message Event did not go away when unregistered")
        

print("Sucess in testing event module")
