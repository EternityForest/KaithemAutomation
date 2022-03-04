## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1610585064104696, resource-type: event}

"""

__trigger__='kaithem.misc.uptime()>90'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    
    import time
    
        
    blink = kaithem.states.StateMachine(start="off")
    
    on = blink.addState("on")
    off = blink.addState("off")
    
    blink.setTimer("on", 1, "off")
    
    blink.setTimer("off", 1, "on")
    blink.addRule("off", 'begin', "on")
    blink('begin')
    

def eventAction():
    module.sm_lamp = 0
    
    def on():
        module.sm_lamp = 1
        
    def off():
        module.sm_lamp = 0
        
    sm = kaithem.states.StateMachine(start="off")
    
    on = sm.addState("on", enter=on)
    off = sm.addState("off", enter=off)
    
    sm.setTimer("on", 1, "off")
    
    sm.addRule('off', "motion","on")
    
    if module.sm_lamp:
        raise RuntimeError("state machine imaginary lamp is on too soon")
    sm.event("motion")
    time.sleep(0.3)
    if not module.sm_lamp:
        raise RuntimeError("state machine imaginary lamp is not on")
    time.sleep(2)
    
    if module.sm_lamp:
        time.sleep(8)
        if module.sm_lamp:
            raise RuntimeError("state machine imaginary lamp didn't turn itself off within 10s")
        else:
              raise RuntimeError("state machine imaginary lamp didn't turn itself off within 2s")
    
    #Turn it on before deleting so we can make sure the timer won't trigger after it's gone
    sm.event('motion')
    del sm
    print("success")
