from iot_devices import device

import random

class RandomDevice(device.Device):
    device_type = "RandomDevice"
    def __init__(self,name, data):
        device.Device.__init__(self,name, data)

        # Push type data point set by the device
        self.numeric_data_point("random")
        self.set_data_point("random",random.random())


        # On demand requestable data point pulled by application.
        # All you have to do is set the val to a callable.
        self.numeric_data_point("dyn_random")
        self.set_data_point_getter("dyn_random", random.random)
