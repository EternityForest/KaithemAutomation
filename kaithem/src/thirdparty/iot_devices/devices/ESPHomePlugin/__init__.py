from typing import Dict
import aioesphomeapi
import aioesphomeapi.client as client
import asyncio
import threading
import zeroconf
import time

import iot_devices.device
import iot_devices.host

zc = zeroconf.Zeroconf()

iot_devices.host.app_exit_register(zc.close)


class ESPHomeDevice(iot_devices.device.Device):
    device_type = "ESPHomeDevice"

    def update_wireless(self):
        pass

    def handle_log(self, l):
        self.print(l)

    def add_bool(self, name, w=False):
        self.numeric_data_point(name, min=0, max=1, subtype="bool", writable=w)

    def obj_to_tag(self, i):
        try:
            self.key_to_name[i.key] = i.object_id
            self.name_to_key[i.object_id] = i.key

            if isinstance(i, client.BinarySensorInfo):
                self.add_bool(i.object_id)

            elif isinstance(i, client.NumberInfo):
                self.numeric_data_point(
                    i.object_id, min=i.min_value, max=i.max_value)

            elif isinstance(i, client.SensorInfo):
                self.numeric_data_point(
                    i.object_id, unit=i.unit_of_measurement.replace('°', 'deg').replace('³','3'), writable=False)
                
            elif isinstance(i, client.TextSensorInfo):
                self.string_data_point(
                    i.object_id)
                
        except Exception:
            self.handle_exception()

    def incoming_state(self, s):
        try:
            if isinstance(s, client.BinarySensorState):
                self.set_data_point(
                    self.key_to_name[s.key], 1 if s.state else False)

            elif isinstance(s, client.NumberState):
                self.set_data_point(self.key_to_name[s.key], s.state)

            elif isinstance(s, client.SensorState) or isinstance(s, client.TextSensorState):
                self.set_data_point(self.key_to_name[s.key], s.state)
        except Exception:
            self.handle_exception()


    def __init__(self, name: str, config: Dict[str, str], subdevice_config=None, **kw):

        self.name_to_key = {}
        self.key_to_name = {}
        self.thread = threading.Thread(target=self.asyncloop)
        self.numeric_data_point("api_connected", min=0,
                                max=1, subtype="bool", writable=False)
        self.set_alarm("Not Connected", "api_connected",
                       "value<1", trip_delay=120, auto_ack=True)

        self.set_config_default('device.hostname', '')
        self.set_config_default('device.apikey', '')

        super().__init__(name, config, subdevice_config, **kw)
        self.thread.start()

    def asyncloop(self):
        self.loop = asyncio.new_event_loop()
        self.loop.run_until_complete(self.main())
        self.loop.run_forever()

    def close(self):
        self.loop.stop()
        for i in range(50):
            if not self.loop.is_running:
                self.loop.close()
                break
            time.sleep(0.1)
        return super().close()

    async def main(self, *a, **k):
        """Connect to an ESPHome device and get details."""

        # Establish connection
        api = aioesphomeapi.APIClient(
            self.config['device.hostname'], 6053, None, noise_psk=self.config['device.apikey'], keepalive=10)
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
        self.metadata['Model'] = device_info.model
        self.metadata['Manufacturer'] = device_info.manufacturer
        self.metadata['Project Version'] = device_info.project_version
        self.metadata['Has Deep Sleep'] = device_info.has_deep_sleep

        # List all entities of the device
        entities = await api.list_entities_services()
        for i in entities[0]:
            self.obj_to_tag(i)

        def cb(state):
            self.incoming_state(state)
        await api.subscribe_states(cb)
        await api.subscribe_logs(self.handle_log, log_level=client.LogLevel.LOG_LEVEL_INFO)
        self.set_data_point('api_connected', 1)

    async def on_disconnect(self, *a):
        self.set_data_point('api_connected', 0)
