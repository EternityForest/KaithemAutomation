## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code through the web UI
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1569526242271009
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    import time
    
    
    tag = kaithem.tags["/system/gpio/8"]
    
    io8 = kaithem.gpio.DigitalInput(8, mock=True, comment="Comments show up in the GPIO tools page")
    io9 = kaithem.gpio.DigitalInput(9, mock=True)
    io10 = kaithem.gpio.DigitalInput(10, mock=True)
    io11 = kaithem.gpio.DigitalOutput(11, mock=True)
    
    #Access the raw object
    print(io8.gpio.value)
    
    #Access as a tag point
    print(io8.tag.value)
    
    
    #Set it low, and pins default to aftive low
    #Fails on real raspberry pi because setRawMockValue
    #Is only for fake pins not real ones
    io8.setRawMockValue(0)
    
    print("Input is active")
    #Access as a tag point, show the fake value, Should be one
    print(io8.tag.value)
    #Access the raw object
    print(io8.gpio.value)
    
    time.sleep(0.55)
    #Set it high
    io8.setRawMockValue(1)
    print("Input is not active")
    #Access as a tag point, show the fake value, Should be 0
    print(io8.tag.value)
    #Access the raw object
    print(io8.gpio.value)

def eventAction():
    pass
