## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1622974123050325, resource-type: event}

"""

__trigger__='!onmsg /test'

if __name__=='__setup__':
    pass

def eventAction():
    #This is an example of how to use a special trigger expression to recieve messages from the internal message bus
    #Every time someone writes to the topic /test,  this event fires.
    
    #__message contains the actual message while __topic has the topic
    #the variable module, like kaithem, is availible almost everywhere but each module has its own instance
    module.last_msg = __message
