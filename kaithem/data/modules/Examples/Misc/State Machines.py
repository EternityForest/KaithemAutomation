## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: true
enable: true
once: true
priority: interactive
rate-limit: 5.0
resource-timestamp: 1646963689429589
resource-type: event
versions: {}

"""

__trigger__='True'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__='This is a demo of state machines. State machines are VirtualResources and can be displayed on the module pages.'
    
    sm = kaithem.states.StateMachine(start='off', description="This state machine toggles every 5s if enableTurningOn is True.")
    
    
    #These states can have any string as a name as long as it doesn't have special characters
    sm.addState('on')
    sm.addState('off')
    
    
    enableTurningOn = True
    sm.addRule("on", "toggle", "off")
    #Rules can target a function that returns the actual destination or None for no change.
    sm.addRule("off", "toggle", lambda sm: 'on' if enableTurningOn else None)

def eventAction():
    sm.event("toggle")
