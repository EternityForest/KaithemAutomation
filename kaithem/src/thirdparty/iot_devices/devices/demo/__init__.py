from iot_devices import device

import random
import time
import os

class DemoDevice(device.Device):
    device_type = "DemoDevice"
    def __init__(self,name, data, **kw):
        device.Device.__init__(self,name, data, **kw)

        self.text_config_files = ['test.conf']

        try:
            if not os.path.exists(os.path.join(self.get_config_folder(), 'test.conf')):
                with open(os.path.join(self.get_config_folder(), 'test.conf'),"w") as f:
                    f.write("Testing")
        except Exception:
            pass


        self.set_config_default("device.fixed_number_multiplier","1")

        # Push type data point set by the device
        self.numeric_data_point("random")
        self.set_data_point("random",random.random() * float(self.config['device.fixed_number_multiplier']))


        # On demand requestable data point pulled by application.
        # All you have to do is set the val to a callable.
        self.numeric_data_point("dyn_random")
        self.numeric_data_point("useless_toggle", subtype="bool")
        self.numeric_data_point("do_nothing", subtype="trigger")
        self.numeric_data_point("read_only", writable=False)
        self.set_data_point("read_only", random.random())

        self.set_data_point_getter("dyn_random", random.random)

        if not 'gen2' in data:
            self.create_subdevice(DemoDevice, "subdevice",{"gen2":True})

    @classmethod
    def discover_devices(cls, config={}, current_device=None, intent=None, **kw):

    
        # Return a modified version of the existing.
        # Never get rid of existing user work for no reason
        cfg = {
            'device.fixed_number_multiplier':"1000"
        }
        config= config.copy()
        config.update(cfg)

        return{ "Big fixed numbers":config}