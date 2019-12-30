## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1566264981054410
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    import time
    
    #If the tag doesn't exist it's created
    t = kaithem.tags["TestTagPointExample"]
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

def eventAction():
    pass
