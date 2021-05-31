## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.5
resource-timestamp: 1622421425529383
resource-type: event
versions:
  __draft__:
    action: pass
    continual: false
    enable: true
    once: true
    priority: interactive
    rate-limit: 0.5
    resource-loadedfrom: Tag Points.py
    resource-timestamp: 1622421425529383
    resource-type: event
    setup: "#This code runs once when the event loads. It also runs when you save\\
      \\ the event during the test compile\\r\\n#and may run multiple times when kaithem\\
      \\ boots due to dependancy resolution\\r\\n__doc__=''\\r\\n\\r\\nimport time\\r\\n\\r\\n\\
      #If the tag doesn't exist it's created\\r\\nt = kaithem.tags[\\"TestTagPointExample\\"\\
      ]\\r\\n\\r\\n\\r\\n#Anyone can read and write this tag from the web API\\r\\nt.expose(\\"\\
      __guest__\\",\\"__guest__\\")\\r\\n\\r\\n\\r\\nt.unit = \\"degF\\"\\r\\nt.displayUnits=\\"\\
      degF|degC|K\\"\\r\\nclaim = t.claim(75,\\"foo\\")\\r\\n\\r\\nts = time.time()\\r\\nprint(t.value,\\"\\
      direct\\")\\r\\nmodule['TestTagPointExample']=t\\r\\nprint(\\"celcius\\",t.convertTo(\\"\\
      degC\\"))\\r\\nprint(\\"Kelvin\\",t.convertTo(\\"K\\"))\\r\\n\\r\\nclaim.setAs(35, \\"degF\\"\\
      )\\r\\n\\r\\nprint(t.value)\\r\\n\\r\\nprint(\\"Tag point example stuff took(us):\\",\\
      \\ (time.time()-ts)*10**6)\\r\\n\\r\\n\\r\\n#Auto bg polling\\r\\n\\r\\nrandomTag = kaithem.tags['RandomTag']\\r\\
      \\nimport random\\r\\nrandomTag.value = random.random\\r\\n\\r\\n#Need at least 1 subscriber\\
      \\ for polling to work\\r\\ndef s(v, t,a):\\r\\n    pass\\r\\n\\r\\n#Also needs a nonzero\\
      \\ interval\\r\\nrandomTag.interval = 1\\r\\nrandomTag.subscribe(s)\\r\\n\\r\\n\\r\\nfilterTag\\
      \\ = kaithem.tags.LowpassFilter(\\"LowpassFilterTest\\", randomTag, timeConstant=3)\\r\\
      \\nfilterTag.tag.interval=0.1\\r\\n\\r\\nfilterTag.tag.subscribe(s)\\r\\n\\r\\n\\r\\n\\r\\
      \\nsyncTag1 = kaithem.tags['syncTag1']\\r\\nsyncTag1.mqttConnect(server='__virtual__',port='examples')\\r\\
      \\n\\r\\n\\r\\n\\r\\nsyncTag2 = kaithem.tags['syncTag2']\\r\\nsyncTag2.mqttConnect(server='__virtual__',port='examples')\\r\\
      \\n\\r\\nsyncTag1.value = 70\\r\\n\\r\\n#Look in the tags page.  syncTag2 will have\\
      \\ gotten it's value synced from the first tag."
    trigger: 'True'

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

def eventAction():
    pass
