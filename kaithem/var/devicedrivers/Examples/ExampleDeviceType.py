#Here we create a new driver for a device type.

#Try creating an ExampleDeviceType device in the devices page!
class ExampleDeviceType(Device):
    def hello(self):
        print("Hello World!")
        
    def getColor(self):
        return self.data.get('device.color','Clear')

    def discoverDevices(self):
        #This makes it easier to auto-create devices.
        #Note that the data dicts we return don't need anything besides
        #The relevant stuff, the core attributes that all devices have get added for you.
        return {
                'Blue Example Device':{
                    'device.color': 'blue'
                    }
            }
