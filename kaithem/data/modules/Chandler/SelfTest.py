## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1582208662379375
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    import uuid,time
    sc = kaithem.chandler.Scene("ChandlerSelftestScene")
    sc2 = kaithem.chandler.Scene("ChandlerSelftestScene2")
    uid = uuid.uuid4().hex
    u = module.Universe(uid)
    
    
    cue1 = sc.cues["default"]
    cue1.setValue(uid,7,100)
    
    if not u.values[7]==0:
        raise RuntimeError("Expected 0 for universe background")
    
    sc.setAlpha(1)
    
    time.sleep(0.2)
    if not u.values[7]==100:
        raise RuntimeError("Expected val 100 from cue1")
    
    sc2.setAlpha(1)
    
    time.sleep(0.2)
    if not u.values[7]==100:
        raise RuntimeError("Expected val 100 from cue1 still, sc2 should not affect it")
    
    
    cue = sc2.addCue("test")
    sc2.gotoCue('test')
    
    time.sleep(0.2)
    if not u.values[7]==100:
        raise RuntimeError("Expected val 100 from cue1 still, sc2 should not affect it")
    
    cue1 = sc.cues["default"]
    cue1.setValue(uid,7,50)
    u.close()
    
    sc.stop()
    sc2.stop()
    
    del sc
    del sc2

def eventAction():
    pass
