from typing import Dict
import aioesphomeapi
import aioesphomeapi.client as client
import asyncio
import threading
import zeroconf

import iot_devices.device
import iot_devices.host

zc = zeroconf.Zeroconf()

iot_devices.host.app_exit_register(zc.close)






class ESPHomeDevice(iot_devices.device.Device):
    device_type="ESPHomeDevice"

    def handle_log(self,l):
        self.print(l)

    def add_bool(self,name, w=False):
        self.numeric_data_point(name,min=0,max=1,subtype="bool",writable=w)

    def obj_to_tag(self,i):
        self.key_to_name[i.key] = i.object_id
        self.name_to_key[i.object_id] = i.key

        if isinstance(i, client.BinarySensorInfo):
            self.add_bool(i.object_id)
            
        elif isinstance(i, client.NumberInfo):
            self.numeric_data_point(i.object_id,min=i.min_value,max=i.max_value)


    def incoming_state(self, s):
        if isinstance(s, client.BinarySensorState):
            self.set_data_point(self.key_to_name[s.key], 1 if s.state else False)
        
        if isinstance(s, client.NumberState):
            self.set_data_point(self.key_to_name[s.key], s.state)

    def __init__(self, name: str, config: Dict[str, str], subdevice_config=None, **kw):
        
        self.name_to_key = {}
        self.key_to_name = {}
        self.thread = threading.Thread(target=self.asyncloop)
        self.thread.start()
        self.numeric_data_point("api_connected",min=0,max=1,subtype="bool",writable=False)
        self.set_alarm("Not Connected", "api_connected","value<1", trip_delay=120, auto_ack=True)

        super().__init__(name, config, subdevice_config, **kw)


    def asyncloop(self):
        self.loop = asyncio.new_event_loop()
        self.loop.run_until_complete(self.main())
        self.loop.run_forever()

    def close(self):
        self.loop.stop()
        self.loop.close()
        return super().close()

    async def main(self, *a, **k):
        """Connect to an ESPHome device and get details."""

        # Establish connection
        api = aioesphomeapi.APIClient(
            "JukeboxProp.local", 6053, None, noise_psk="gKksYX76kvp7lWh2gY/jN4kjIEAXbHekQwcfGvUvnio=", keepalive=10)
        self.api = api
        # await api.connect(login=True)

        reconnect_logic = aioesphomeapi.ReconnectLogic(client=self.api,
                                                       on_connect=self.on_connect,
                                                       on_disconnect=self.on_disconnect,
                                                       zeroconf_instance=zc)

        self.reconnect_logic = reconnect_logic
        await reconnect_logic.start()

    async def on_connect(self, *a):
        api = self.api

        # Get API version of the device's firmware
        print(api.api_version)

        # Show device details
        device_info = await api.device_info()
        print(device_info)

        # List all entities of the device
        entities = await api.list_entities_services()
        print(entities)
        for i in entities[0]:
            self.obj_to_tag(i)

        def cb(state):
            self.incoming_state(state)
        await api.subscribe_states(cb)
        await api.subscribe_logs(self.handle_log, log_level=client.LogLevel.LOG_LEVEL_INFO)
        self.set_data_point('api_connected', 1)

    async def on_disconnect(self, *a):
        self.set_data_point('api_connected', 0)

