## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.5
resource-timestamp: 1622422494581770
resource-type: event
versions: {}

"""

__trigger__='True'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    import time
    
    #If the tag doesn't exist it's created
    t = kaithem.tags["TestTagPointExample"]
    
    
    #Anyone can read and write this tag from the web API
    t.expose("__guest__","__guest__")
    
    
    t.unit = "degF"
    t.displayUnits="degF|degC|K"
    claim = t.claim(75,"foo")
    
    ts = time.time()
    print(t.value,"direct")
    module['TestTagPointExample']=t
    print("celcius",t.convertTo("degC"))
    print("Kelvin",t.convertTo("K"))
    
    claim.setAs(35, "degF")
    
    print(t.value)
    
    print("Tag point example stuff took(us):", (time.time()-ts)*10**6)
    
    
    #Auto bg polling
    
    randomTag = kaithem.tags['RandomTag']
    import random
    randomTag.value = random.random
    
    #Need at least 1 subscriber for polling to work
    def s(v, t,a):
        pass
    
    #Also needs a nonzero interval
    randomTag.interval = 1
    randomTag.subscribe(s)
    
    
    filterTag = kaithem.tags.LowpassFilter("LowpassFilterTest", randomTag, timeConstant=3)
    filterTag.tag.interval=0.1
    
    filterTag.tag.subscribe(s)
    
    
    
    syncTag1 = kaithem.tags['syncTag1']
    syncTag1.mqttConnect(server='__virtual__',port='examples',mqttTopic="exampleSyncTag")
    
    
    
    syncTag2 = kaithem.tags['syncTag2']
    syncTag2.mqttConnect(server='__virtual__',port='examples',mqttTopic="exampleSyncTag")
    
    syncTag1.value = 70
    
    #Look in the tags page.  syncTag2 will have gotten it's value synced from the first tag.

def eventAction():
    pass
