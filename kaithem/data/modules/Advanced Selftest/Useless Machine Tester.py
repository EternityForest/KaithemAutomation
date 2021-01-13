## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: true
enable: true
once: true
priority: interactive
rate-limit: 10.0
resource-timestamp: 1610571423178010
resource-type: event
versions: {}

"""

__trigger__='kaithem.misc.uptime()>90'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__='''Runs when kaithem has beed running for 90s.  Check the log on the event page for success.  Tests that the event system is functioning.  It runs continually, ensure that it prints every 10s.   Rare failures are probably just high CPU load'''
    import time
    
    depend = module.uselessmachine

def eventAction():
    module['Useless Machine'].start()
    time.sleep(1)
    module.uselessmachine =  time.time()
    time.sleep(0.5)
    if module.uselessmachine:
        raise RuntimeError("Useless machine didn't work")
    
    module['Useless Machine'].stop()
    time.sleep(1)
    
    module.uselessmachine =  time.time()
    time.sleep(2)
    if not module.uselessmachine:
        raise RuntimeError("Useless machine didn't turn off")
    
    
    module['Useless Machine'].start()
    time.sleep(1)
    module.uselessmachine =  time.time()
    time.sleep(0.5)
    if module.uselessmachine:
        raise RuntimeError("Useless machine didn't turn back on")
    print("success")
