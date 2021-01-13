## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1610570841501375, resource-type: event}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__='This event should have an error associated with it.  If it does not, report an bugge!'
    from src import workers
    
    def raise_an_exception():
        raise RuntimeError("This exception raised to test what happens when a function in the thread pool errors")
        
    workers.do(raise_an_exception)

def eventAction():
    pass
