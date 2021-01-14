## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1610591228719086
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    import time
    
    t = kaithem.tags["TestTagPointSelftest"]
    
    cl = t.claim(51, "foo", 51)
    cl2 = t.claim(52,"foo2", 52)
    
    if not t.value==52:
        raise RuntimeError('wrong val')
    cl2.release()
    
    if not t.value==51:
        raise RuntimeError('wrong val '+ str(t.value))
    
    t.interval =0
    v =  [90]
    
    cl.set(lambda:v[0])
    
    if not t.value==90:
        raise RuntimeError('wrong val')
    v[0]=91
    
    if not t.value==91:
        raise RuntimeError('wrong val')
    
    
    t.interval =60
    v[0]=60
    
    if t.value==60:
        raise RuntimeError("Seems like the cache isn't working, and the value was updated immediately")
    
    
    # Test tag point values derived from other values
    t = kaithem.tags["TestTagPointSelftestA2"]
    t.value = 90
    
    t2=kaithem.tags["=tv('/TestTagPointSelftestA2')+10"]
    
    if not t2.value==100:
        raise RuntimeError("Expression tagpoint didn't work")
    
    
    t.value = 40
    
    if not t2.value==50:
        raise RuntimeError("Expression tagpoint didn't update, value:"+str(t2.value))
    
    
    t2.setAlarm("TestTagAlarm","value>40")
    
    time.sleep(0.5)
    if not t2.alarms['TestTagAlarm'].sm.state=='active':
        raise RuntimeError("Alarm not activated, state:"+ t2.alarms['TestTagAlarm'].sm.state)
    
    t.value = 0
    time.sleep(3)
    if not t2.alarms['TestTagAlarm'].sm.state=='cleared':
        raise RuntimeError("Alarm not cleared, state:"+t2.alarms['TestTagAlarm'].sm.state+" value:"+str(t2.value))
    
    
    t2.alarms['TestTagAlarm'].acknowledge()
    
    if not t2.alarms['TestTagAlarm'].sm.state=='normal':
        raise RuntimeError("Alarm not normal after acknowledge")
    
    
    
    
    # Test separate trip/release
    t.value = 40
    
    t2.setAlarm("TestTagAlarm","value>40", releaseCondition="value<30")
    
    time.sleep(0.5)
    if not t2.alarms['TestTagAlarm'].sm.state=='active':
        raise RuntimeError("Alarm not activated, state:"+ t2.alarms['TestTagAlarm'].sm.state)
    
    t.value = 28
    time.sleep(0.5)
    if not t2.alarms['TestTagAlarm'].sm.state=='active':
        raise RuntimeError("Alarm not active, separate release conditon was ignored, state:"+t2.alarms['TestTagAlarm'].sm.state+" value:"+str(t2.value))
    
    t.value = 10
    time.sleep(1)
    t2.alarms['TestTagAlarm'].acknowledge()
    
    if not t2.alarms['TestTagAlarm'].sm.state=='normal':
        raise RuntimeError("Alarm not normal after acknowledge and clear with separate release releaseCondition")

def eventAction():
    pass
