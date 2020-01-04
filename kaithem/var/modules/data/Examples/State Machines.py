## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: true
enable: true
once: true
priority: interactive
rate-limit: 5.0
resource-timestamp: 1577965176292682
resource-type: event
versions:
  __draft__:
    action: "sm.event(\\"toggle\\")\\r\\nprint(time.time())"
    continual: true
    enable: true
    once: true
    priority: interactive
    rate-limit: 5.0
    resource-loadedfrom: State Machines.py
    resource-timestamp: 1577965176292682
    resource-type: event
    setup: "#This code runs once when the event loads. It also runs when you save\\
      \\ the event during the test compile\\r\\n#and may run multiple times when kaithem\\
      \\ boots due to dependancy resolution\\r\\n__doc__='This is a demo of state machines.\\
      \\ State machines are VirtualResources and can be displayed on the module pages.'\\r\\
      \\n\\r\\nsm = kaithem.states.StateMachine(start='off', description=\\"This state\\
      \\ machine toggles every 5s if enableTurningOn is True.\\")\\r\\n\\r\\nmodule['State\\
      \\ Machine'] = sm\\r\\n\\r\\n#These states can have any string as a name as long\\
      \\ as it doesn't have special characters\\r\\nsm.addState('on')\\r\\nsm.addState('off')\\r\\
      \\n\\r\\n\\r\\nenableTurningOn = True\\r\\nsm.addRule(\\"on\\", \\"toggle\\", \\"off\\")\\r\\
      \\n#Rules can target a function that returns the actual destination or None for\\
      \\ no change.\\r\\nsm.addRule(\\"off\\", \\"toggle\\", lambda sm: 'on' if enableTurningOn\\
      \\ else None)\\r\\nimport time"
    trigger: 'True'

"""

__trigger__='True'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__='This is a demo of state machines. State machines are VirtualResources and can be displayed on the module pages.'
    
    sm = kaithem.states.StateMachine(start='off', description="This state machine toggles every 5s if enableTurningOn is True.")
    
    module['State Machine'] = sm
    
    #These states can have any string as a name as long as it doesn't have special characters
    sm.addState('on')
    sm.addState('off')
    
    
    enableTurningOn = True
    sm.addRule("on", "toggle", "off")
    #Rules can target a function that returns the actual destination or None for no change.
    sm.addRule("off", "toggle", lambda sm: 'on' if enableTurningOn else None)
    import time

def eventAction():
    sm.event("toggle")
    print(time.time())
