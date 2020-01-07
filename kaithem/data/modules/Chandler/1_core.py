## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1567226839313672, resource-type: event}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    import time
    
    def maketimefunc():
        global timefunc
        if kaithem.registry.get("lighting/nettime",False):
            timefunc = kaithem.time.lantime
        else:
            timefunc = time.time
        module.maketimefunc = maketimefunc
    maketimefunc()
    module.timefunc = timefunc

def eventAction():
    pass
