## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.5
resource-timestamp: 1628410720787040
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


    print("celcius",t.convertTo("degC"))
    print("Kelvin",t.convertTo("K"))
    
    claim.setAs(35, "degF")
    
    print(t.value)
    
    print("Tag point example stuff took(us):", (time.time()-ts)*10**6)
    
    
    #Auto bg polling
    
    randomTag = kaithem.tags['RandomTag']
    import random
    randomTag.value = random.random
    randomTag.expose("__guest__","__never__")
    
    #Need at least 1 subscriber for polling to work, so that we can see the changes in the web UI.
    #Web UI doesn't count as a reall poll subscriber, to save CPU
    def s(v, t,a):
        pass
    
    #Also needs a nonzero interval
    randomTag.interval = 1
    randomTag.subscribe(s)
    
    randomTag2 = kaithem.tags['RandomOverridableTag']
    import random
    randomTag2.value = random.random
    randomTag2.expose("__guest__","__guest__", 70)
    
    
    #Also needs a nonzero interval
    randomTag2.interval = 1
    randomTag.subscribe(s)
    
    
    
    
    filterTag = kaithem.tags.LowpassFilter("LowpassFilterTest", randomTag, timeConstant=3)
    filterTag.tag.interval=0.1
    
    filterTag.tag.subscribe(s)
    
    
def eventAction():
    pass
