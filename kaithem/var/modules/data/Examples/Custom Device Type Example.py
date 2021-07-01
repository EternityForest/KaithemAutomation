## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1624012353619848
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__='This script demonstrates how you can create a custom Device that can be managed via the devices page'
    
    from mako.template import Template
    
    myCustomManagementForm = """
    <h3>Info</h3>
    <p class="help">
      This is a custom device type, demonstrating how device drivers can be embedded in a module.  It plays a sound when creating and deleting devices.
    </p>
    
    <table>
        <tr>
            <td>Nonsense Unused Parameter</td>
            <td><input name="device.foo" value="${data.get('device.foo','')|h}"></td>
        </tr>
    </table>
    """
    
    class ExampleCustomDevice(kaithem.devices.Device):
        #DeviceTypeName must be correct!
        deviceTypeName = 'ExampleCustomDevice'
        readme = "What a useless device!!!!"
    
        def close(self):
            kaithem.devices.Device.close(self)
            kaithem.sound.play('alert.ogg')
    
    
        #The "data" parameter here holds the entire state of the device.   New devices are empty.
        #However, the getManagementForm HTML code may contain any number of inputs that allow the user to add items.
    
        #Custom device specific keys must begin with "device."
    
        def __init__(self, name, data):
            print("Device Data Is:", data)
    
            #The init function copies data to self.data
            kaithem.devices.Device.__init__(self, name, data)
    
            #Use this function to directly modify the devices own data in code.
            #Don't modify data directly, as we need to set flags to ensure the data can get saved to disk.        
            self.setDataKey("device.exampleKey", self.data.get("device.exampleKey","someDefaultValue"))
    
            print("Device Data Is(After setting key):", self.data)
            
            #The entire body of custom stuff should be inside try-except tags like this.
            try:
                kaithem.sound.play('alert.ogg')
    
                #You don't technically need Mako to create the management form, it just makes it easier.
                self.template = Template(myCustomManagementForm)
            except Exception:
                self.handleException()
    
        def getManagementForm(self):
            return self.template.render(data=self.data, obj=self)
    
    
    kaithem.devices.deviceTypes["ExampleCustomDevice"] = ExampleCustomDevice

def eventAction():
    pass
