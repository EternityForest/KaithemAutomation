## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1671835407677572
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    import time,os
    
    
    
    module.config ={
        'soundFolders': [],
        'allowAllTags': False,
        'netTime': False
    }
    
    saveLocation = os.path.join(kaithem.misc.vardir,"chandler")
    
    if  os.path.exists( os.path.join(saveLocation,"config.yaml")):
        module.config.update(kaithem.persist.load(os.path.join(saveLocation,"config.yaml")))
    
    
    def maketimefunc():
        global timefunc
        timefunc = time.time
        module.maketimefunc = maketimefunc
        
    maketimefunc()
    module.timefunc = timefunc

def eventAction():
    pass
