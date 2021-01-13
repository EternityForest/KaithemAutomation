## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1610571329277990, resource-type: event}

"""

__trigger__='poll()'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    import time
    module.uselessmachine = False
    
    
    def poll():
        return module.uselessmachine

def eventAction():
    print("responsetimewas",time.time()-module.uselessmachine)
    module.uselessmachine = 0
