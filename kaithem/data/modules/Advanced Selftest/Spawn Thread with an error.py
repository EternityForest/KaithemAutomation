## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1610584445174183, resource-type: event}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__='This Event runs once and starts a thread with an error in it. This you should see something in the notifications signifying a thread stopped.'
    import threading
    
    def f():
        nonexistant()
    t = threading.Thread(target=f)
    t.name= "ThisThreadShouldExitWithAnException"
    t.start()

def eventAction():
    pass
