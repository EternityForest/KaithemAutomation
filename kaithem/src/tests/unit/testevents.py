import common
from src import newevt,messagebus
import time

#Create an event that sets y to 0 if it is 1
x = newevt.Event("y==1","y=0",locals())

#Register event with polling.
x.register()
#Set y to 1
y = 1

time.sleep(0.05)
#y should immediately be set back to 0 at the next polling cycle 
if y == 1:
        common.fail("Edge-Triggered Event did nothing")
        
#Unregister event and make sure it really goes away
x.unregister() 
y =1
if not y == 1:
        common.fail("Edge-Triggered Event did not go away when unregistered")
        
##Testing one time events
y = False
def f():
    return y
def g():
    global y
    y = False
    print('turdy')
    
newevt.when(f,g)
y = True
time.sleep(0.35)
if y:
    common.fail("One time event did not trigger")
y = True
time.sleep(0.5)
if not y:
    common.fail("One time event did not delete itself properly")
        
        
#Same exact thing exept we use the onchange
x = newevt.Event("!onchange y","y=5",locals())


#Register event with polling.
x.register()
#Give it a value to change from
y = 0
#Let it notice the old value
time.sleep(0.10)
#Set y to 1
y = 1

time.sleep(0.10)
#y should immediately be set back to 0 at the next polling cycle 
if y == 1:
        common.fail("Onchange Event did nothing")
        
#Unregister event and make sure it really goes away
x.unregister() 
y =1
if not y == 1:
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
if not  y == 'test':
        common.fail("Message Event did nothing")
    
#Unregister event and make sure it really goes away
x.unregister() 
y =1

messagebus.postMessage('poo',"/test")
if y == 'test':
        common.fail("Message Event did not go away when unregistered")
        

print("Sucess in testing event module")
