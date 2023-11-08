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

    def wait_ready(self, timeout=15):
        # Wait for connection ready
        s = time.time()
        while not self.datapoints["native_api_connected"]:
            if (time.time() - s) > timeout:
                raise RuntimeError("Could not connect")
            time.sleep(timeout / 100)

    def async_on_service_call(self, service: client.HomeassistantServiceCall) -> None:
        """Call service when user automation in ESPHome config is triggered."""
        domain, service_name = service.service.split(".", 1)
        service_data = service.data

        if service.data_template:
            self.handle_error("Can't do HASS service call templating")
            return

        if service.is_event:
            # ESPHome uses servicecall packet for both events and service calls
            # Ensure the user can only send events of form 'esphome.xyz'
            if domain != "esphome":
                self.handle_error("Can't do non esphome domains, yours was: " + domain)

                return

            # Call native tag scan
            if service_name == "tag_scanned":
                tag_id = service_data["tag_id"]

                # Don't clutter up the system with unneeded data points.
                if "scanned_tag" not in self.datapoints:
                    self.object_data_point(
                        "scanned_tag", "RFID reading", writable=False
                    )

                self.set_data_point("scanned_tag", [str(tag_id), time.time(), ""])
                return

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

            elif isinstance(i, client.SwitchInfo):

                def handler(v, t, a):
                    if not a == "FromRemoteDevice":

                        async def f():
                            await self.api.switch_command(
                                i.key, True if v > 0.5 else False
                            )

                        asyncio.run_coroutine_threadsafe(f(), self.loop)

                self.numeric_data_point(
                    i.object_id,
                    min=0,
                    max=1,
                    subtype="bool",
                    writable=True,
                    handler=handler,
                )

            elif isinstance(i, client.NumberInfo):
                self.numeric_data_point(i.object_id, min=i.min_value, max=i.max_value)

            elif isinstance(i, client.SensorInfo):
                self.numeric_data_point(
                    i.object_id,
                    unit=i.unit_of_measurement.replace("°", "deg").replace("³", "3"),
                    writable=False,
                )

                # Onboard WiFi and die temperature get special treatment, always want
                if (
                    i.device_class == "signal_strength"
                    and i.unit_of_measurement == "dBm"
                    and i.entity_category == "diagnostic"
                ):
                    self.set_alarm(
                        "WiFi Signal low", i.object_id, "value < -89", auto_ack=True
                    )

                if (
                    i.device_class == "signal_strength"
                    and i.unit_of_measurement == "°C"
                    and i.entity_category == "diagnostic"
                ):
                    self.set_alarm(
                        "Temperature Below Freezing",
                        i.object_id,
                        "value < 0",
                        auto_ack=True,
                        priority="warning",
                    )

                    self.set_alarm(
                        "Temperature High",
                        i.object_id,
                        "value > 75",
                        auto_ack=True,
                        priority="warning",
                    )

            elif isinstance(i, client.TextSensorInfo):
                self.string_data_point(i.object_id)

            elif isinstance(i, client.AlarmControlPanelInfo):
                self.string_data_point_data_point(i.object_id, writable=False)
                self.set_alarm(
                    self.name + " " + i.object_id + "Triggered",
                    i.object_id,
                    "value =='TRIGGERED'",
                    priority="critical",
                    auto_ack=True,
                )
                self.set_alarm(
                    self.name + " " + i.object_id,
                    i.object_id,
                    "value =='PENDING'",
                    priority="warning",
                    auto_ack=True,
                )

        except Exception:
            self.handle_exception()

    def incoming_state(self, s):
        try:
            if isinstance(s, (client.BinarySensorState, client.SwitchState)):
                self.set_data_point(
                    self.key_to_name[s.key],
                    1 if s.state else 0,
                    annotation="FromRemoteDevice",
                )

            elif isinstance(s, client.NumberState):
                self.set_data_point(self.key_to_name[s.key], s.state)

            elif isinstance(s, client.AlarmControlPanelState):
                self.set_data_point(self.key_to_name[s.key], s.state.name)

            elif isinstance(s, client.SensorState) or isinstance(
                s, client.TextSensorState
            ):
                self.set_data_point(self.key_to_name[s.key], s.state)
        except Exception:
            self.handle_exception()

    def __init__(self, name: str, config: Dict[str, str], subdevice_config=None, **kw):
        self.name_to_key = {}
        self.key_to_name = {}
        self.input_units = {}
        self.thread = threading.Thread(
            target=self.asyncloop, name="ESPHOME " + self.name
        )
        self.numeric_data_point(
            "native_api_connected", min=0, max=1, subtype="bool", writable=False
        )
        self.set_alarm(
            "Not Connected",
            "native_api_connected",
            "value<1",
            trip_delay=120,
            auto_ack=True,
        )

        self.set_config_default("device.hostname", "")
        self.set_config_default("device.apikey", "")

        super().__init__(name, config, subdevice_config, **kw)
        self.thread.start()

    def asyncloop(self):
        self.loop = asyncio.new_event_loop()
        self.loop.run_until_complete(self.main())
        self.loop.run_forever()

    def close(self):
        if self.api:
            try:
                t = asyncio.run_coroutine_threadsafe(self.api.disconnect(), self.loop)

                d = False

                st = time.monotonic()
                while (time.monotonic() - st) < 1:
                    if t.done():
                        d = True
                        break
                    time.sleep(0.025)

                if not d:
                    self.handle_error("Timeout waiting for clean disconnect")
            except Exception:
                self.handle_exception()
                
        asyncio.run_coroutine_threadsafe(self.loop.shutdown_asyncgens(), self.loop)
        self.loop.stop()

        for i in range(50):
            if not self.loop.is_running():
                self.loop.close()
                break
            time.sleep(0.1)


        return super().close()

    async def main(self, *a, **k):
        """Connect to an ESPHome device and get details."""

        # Establish connection
        api = aioesphomeapi.APIClient(
            self.config["device.hostname"],
            6053,
            None,
            noise_psk=self.config["device.apikey"] or None,
            keepalive=10,
        )
        self.api = api
        # await api.connect(login=True)

        reconnect_logic = aioesphomeapi.ReconnectLogic(
            client=self.api,
            on_connect=self.on_connect,
            on_disconnect=self.on_disconnect,
            zeroconf_instance=zc,
        )

        self.reconnect_logic = reconnect_logic
        await reconnect_logic.start()

    async def on_connect(self, *a):
        api = self.api

        # Get API version of the device's firmware
        print(api.api_version)

        # Show device details
        device_info = await api.device_info()
        self.metadata["Model"] = device_info.model
        self.metadata["Manufacturer"] = device_info.manufacturer
        self.metadata["Project Version"] = device_info.project_version
        self.metadata["Has Deep Sleep"] = device_info.has_deep_sleep

        # List all entities of the device
        entities = await api.list_entities_services()
        for i in entities[0]:
            self.obj_to_tag(i)

        def cb(state):
            self.incoming_state(state)

        await api.subscribe_states(cb)
        await api.subscribe_logs(
            self.handle_log, log_level=client.LogLevel.LOG_LEVEL_INFO
        )
        await api.subscribe_service_calls(self.async_on_service_call)
        time.sleep(0.5)
        self.set_data_point("native_api_connected", 1)

    async def on_disconnect(self, *a):
        self.set_data_point("native_api_connected", 0)
