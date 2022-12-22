from iot_devices import device
import requests
import json
import time
import os
import threading
import copy
import traceback
from typing import Dict

import paho.mqtt.client as mqtt
from logging import getLogger
log = getLogger(__name__)

"""
Object representation for YoLink MQTT Client

"""

server_url = 'https://api.yosmart.com'
mqtt_url = 'api.yosmart.com'


readme = """
    Get the UAC ID and key in the advanced settings of the YoLink app.
    It will auto-discover all your devices.  Save this device again to update the list.
    Supports leak, temperature, door, and siren

    Note that kaithem's devices and tag points are named based on the discovered YoLink names.
    Changing the names in the YoLink app will break your automations and you will have to set them up again.

    Also, you can replace a lost sensor just by giving the replacement the same name, as the identity is linked to
    the name rather than the unique ID.

    This uses an UNENCRYPTED cloud API at the moment. Do NOT use from inside a network you don't trust.

    Also note that subdevices are created dynamically.  This means that your events and modules might be created before this device is finshed
    loading all your YoLink sensors.

    Since this uses a cloud API, it is very possible for the internet connection to fail. 
    Commands sent to devices while the network is out will be ignored.
"""


class RateLimiter():
    def __init__(self, count, duration) -> None:
        self.interval = duration / count
        self.count = count
        self.duration = duration

        self.lastRefill = time.monotonic()

    def limit(self):
        t = time.monotonic() - self.lastRefill
        self.lastRefill = time.monotonic()

        t = t / self.duration
        self.count = self.count + t

        if self.count < - self.count:
            raise RuntimeError("Too many attempts, too fast")

        if self.count < 1:
            time.sleep(self.interval)
            # Add a penalty for event trying to go too fast, so it eventually errors and someone notices
            self.count -= 0.5
        else:
            self.count -= 1


class YoLinkMQTTClient(object):

    def __init__(self, uid, key, homeid, parent, mqtt_port=8003, client_id=os.getpid()):

        self.topic = "yl-home/" + homeid + "/+/report"
        self.topic2 = "yl-home/" + homeid + "/+/response"

        self.mqtt_url = mqtt_url
        self.mqtt_port = int(mqtt_port)
        self.key = key
        self.parent = parent

        self.client = mqtt.Client(client_id=str(__name__ + str(client_id)),
                                  clean_session=True, userdata=None,
                                  protocol=mqtt.MQTTv311, transport="tcp")
        self.client.reconnect_delay_set(60, 30*60)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()

    def connect_to_broker(self):
        self.client.username_pw_set(username=self.key)
        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect

        self.client.connect(self.mqtt_url, self.mqtt_port, 10)
        self.client.loop_start()

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))

            if 'deviceId' in payload:
                deviceId = payload['deviceId']
            elif 'targetDevice' in payload and 'code' in payload:
                deviceId = payload['targetDevice']
            else:
                return

            if deviceId in self.parent.devices_by_id:
                self.parent.devices_by_id[deviceId].onData(payload)

        except Exception:
            self.parent.handle_error(traceback.format_exc())

    def on_connect(self, client, userdata, flags, rc):
        if (rc == 0):
            self.client.subscribe(self.topic)
            self.client.subscribe(self.topic2)

            self.parent.connected = True
            self.parent.set_data_point("connected", 1)
            self.parent.print("Connected to MQTT")

        else:
            self.parent.handle_error(traceback.format_exc())
    
    def on_disconnect(self, *a,**k):
        self.parent.set_data_point("connected", 0)


def listify(d):
    if not isinstance(d, list):
        d = [d]
    return d


# They name the exact same thing different names in reports and responses
# Handles:
# data :{state: normal}
# data :{state:{ state:normal}}
# state: {state: normal}
def get_from_state_or_data(d, p):
    if 'data' in d:
        x = d['data']
    elif 'state' in d:
        x = d['state']
    else:
        return None

    if 'state' in x:
        if isinstance(x['state'], dict):
            x = x['state']

    if p in x:
        return x[p]
    else:
        return None


class YoLinkDevice(device.Device):
    device_type = "YoLinkDevice"

    readme = readme

    has_battery = True

    def __init__(self, name: str, config: Dict[str, str], **kw):
        super().__init__(name, config, **kw)
        self.numeric_data_point("rssi", min=-120, max=8,
                                lo=-100, writable=False, default=-99)


        # Set a very long trip delay because of the slow updates
        self.set_alarm('Low Signal', 'rssi', 'value < -99', trip_delay=(3600*6) if self.has_battery else (3600*4.5), auto_ack=True)

        if self.has_battery:
            self.numeric_data_point(
                "battery", min=0, max=100, lo=30, writable=False, auto_ack=True)
            self.set_alarm('Low Battery', 'battery', 'value < 30')

    def onData(self, data):

        if 'deviceId' in data:
            self.metadata['Device ID'] = data['deviceId']

        if 'data' in data:
            if 'loraInfo' in data['data']:
                s = data['data']['loraInfo']['signal']
                self.set_data_point('rssi', s)
                self.metadata['Gateway ID'] = data['data']['loraInfo']['gatewayId']

        if self.has_battery:
            battery = get_from_state_or_data(data, 'battery')

            if battery is not None:
                battery = battery * 25
                self.set_data_point('battery', battery)

        sl = get_from_state_or_data(data, 'soundLevel')

        if sl is not None:
            self.metadata['Sound Level Setting']= sl

    def downlink(self, d):
        d.update({'token': self.token, 'targetDevice': self.deviceId})
        self.parent.sendDownlink(self.deviceId, d)

    def simpleMethod(self, m):
        self.downlink({'method': m})

    def refresh(self):
        pass


class YoLinkDoorSensor(YoLinkDevice):
    device_type = "YoLinkDoorSensor"

    def __init__(self, name: str, config: Dict[str, str], **kw):
        super().__init__(name, config, **kw)
        self.numeric_data_point("open", min=0, max=1,
                                subtype='bool', writable=False)

    def onData(self, data):
        YoLinkDevice.onData(self, data)
        o = get_from_state_or_data(data, 'state')
        if o is None:
            return

        open = 0 if (o == 'closed') else 1
        self.set_data_point('open', open)

    def refresh(self):
        self.simpleMethod("DoorSensor.getState")


class YoLinkOutlet(YoLinkDevice):
    device_type = "YoLinkOutlet"
    has_battery = False

    def __init__(self, name: str, config: Dict[str, str], **kw):
        super().__init__(name, config, **kw)
        self.numeric_data_point("switch", min=0, max=1,
                                subtype='bool', handler=self.setState)

        self.numeric_data_point("power", min=0, max=2500,
                                unit="W", writable=False)
        
        self.set_alarm("High Power Device", "power", "value > 600", priority='info', auto_ack=True, trip_delay=10)
        self.set_alarm("Overload", "power", "value > 1500", priority='critical', trip_delay=5)


    def onData(self, data):
        YoLinkDevice.onData(self, data)
        o = get_from_state_or_data(data, 'state')
        if o is None:
            return

        open = 0 if (o == 'closed') else 1
        self.set_data_point('switch', open)

    def setState(self, v, *a, **k):
        self.downlink({
            'method': "Outlet.setState",
            'params': {
                'state': 'open' if v else 'closed'
            }
        })

    def refresh(self):
        self.simpleMethod("Outlet.getState")


class YoLinkLeakSensor(YoLinkDevice):
    device_type = "YoLinkLeakSensor"

    def __init__(self, name: str, config: Dict[str, str], **kw):
        super().__init__(name, config, **kw)
        self.numeric_data_point("leak", min=0, max=1,
                                subtype='bool', writable=False)

        self.set_alarm('Water Detected', 'leak', 'value > 0',
                       priority='critical', auto_ack=True, trip_delay=5)

    def onData(self, data):
        YoLinkDevice.onData(self, data)
        o = get_from_state_or_data(data, 'state')
        if o is None:
            return

        leak = 0 if (o == 'normal') else 1
        self.set_data_point('leak', leak)

    def refresh(self):
        self.simpleMethod("LeakSensor.getState")


class YoLinkSiren(YoLinkDevice):
    device_type = "YoLinkSiren"

    def __init__(self, name: str, config: Dict[str, str], **kw):
        super().__init__(name, config, **kw)
        self.numeric_data_point(
            "on", min=0, max=1, subtype='bool', writable=False)

        self.numeric_data_point(
            "powered", min=0, max=1, lo=0, subtype='bool', writable=False)

        self.numeric_data_point("start", subtype='trigger',
                                description="Trigger a momentary siren", handler=self.doSiren)

        self.numeric_data_point("stop", subtype='trigger',
                                description="Stop an active siren", handler=self.stopSiren)

        self.set_alarm('PowerFail', 'powered', 'value < 1',
                       priority='error')

        self.set_alarm('Siren "+name+" is on', 'on', 'value > 0',
                       priority='warning', auto_ack=True)

    def refresh(self):
        self.simpleMethod("Siren.getState")

    def doSiren(self, v, *a, **k):
        self.downlink({
            'method': "Siren.setState",
            'params': {
                'state':
                {'alarm': True}
            }
        })

    def stopSiren(self, v, *a, **k):
        self.downlink({
            'method': "Siren.setState",
            'params': {
                'state':
                {'alarm': False}
            }
        })

    def onData(self, data):
        YoLinkDevice.onData(self, data)
        o = get_from_state_or_data(data, 'state')
        if o is None:
            return

        on = 0 if (o == 'normal') else 1
        self.set_data_point('on', on)

        o = get_from_state_or_data(data, 'powerSupply')
        if o is None:
            return

        usb = 1 if (data['data']['powerSupply'] == 'usb') else 0
        self.set_data_point('powered', usb)


class YoLinkTemperatureSensor(YoLinkDevice):
    device_type = "YoLinkTemperatureSensor"

    def __init__(self, name: str, config: Dict[str, str], **kw):
        super().__init__(name, config, **kw)
        self.numeric_data_point("temperature", min=-40,
                                max=100, unit='degC', writable=False)

        self.numeric_data_point(
            "humidity", min=0, max=100, unit='%', writable=False)

        self.set_alarm("Extreme high temperature", "temperature", "value > 85", priority="critical")
        self.set_alarm("Very high humidity", "humidity", "value > 90", priority="info", auto_ack=True)


    def onData(self, data):
        YoLinkDevice.onData(self, data)

        t = get_from_state_or_data(data, 'temperature')
        if t is None:
            return

        h = get_from_state_or_data(data, 'humidity')
        if h is None:
            return

        self.set_data_point('temperature', t)
        self.set_data_point('humidity', t)

    def refresh(self):
        self.simpleMethod("THSensor.getState")


deviceTypes = {
    "YolinkDevice": YoLinkDevice,
    "DoorSensor": YoLinkDoorSensor,
    "LeakSensor": YoLinkLeakSensor,
    "THSensor": YoLinkTemperatureSensor,
    "Siren": YoLinkSiren,
    "Outlet": YoLinkOutlet
}

connectRateLimit = RateLimiter(5, 5 * 60)


class YoLinkService(device.Device):
    device_type = "YoLinkService"

    def makeRequest(self, r):
        r = copy.deepcopy(r)
        r['time'] = int(time.time())

        return json.loads(requests.post(server_url + '/open/yolink/v2/api', headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.token,
        }, data=json.dumps(r), timeout=5).text)['data']

    def close(self):
        try:
            self.client.close()
        except Exception:
            log.exception("Error closing")
        return super().close()

    def sendDownlink(self, device, data):
        self.dowlinkRateLimit.limit()
        try:
            data['time'] = int(time.time())

            self.client.client.publish(
                "yl-home" + "/" + self.homeId + "/" + device + "/request", json.dumps(data))

        except Exception:
            self.handle_error(traceback.format_exc())

    def initialConnection(self):
        self.token = requests.post(server_url + '/open/yolink/token', params={
            'grant_type': 'client_credentials',
            'client_id': self.config['device.user_id'],
            'client_secret': self.config['device.key'],
        }, timeout=5).text

        r = {
            "method": "Home.getDeviceList",
        }
        self.token = json.loads(self.token)['access_token']
        devList = listify(self.makeRequest(r)['devices'])

        r = {
            "method": "Home.getGeneralInfo",
        }

        gInfo = self.makeRequest(r)

        self.homeId = listify(gInfo)[0]['id']

        c = YoLinkMQTTClient(
            self.config['device.user_id'], self.token, self.homeId, self)
        self.client = c

        self.connected = False
        c.connect_to_broker()

        t = time.monotonic()

        while not self.connected:
            if time.monotonic() - t > 5:
                break

        for i in devList:
            t = i['type']
            d = {

            }

            if t in deviceTypes:
                d = self.create_subdevice(
                    deviceTypes[t], i['name'], d)

                d.deviceId = i['deviceId']
                d.token = i['token']
                d.parent = self

                self.devices_by_id[i['deviceId']] = d
        for i in self.devices_by_id:
            try:
                self.devices_by_id[i].refresh()
            except Exception:
                self.handle_error(traceback.format_exc())

        self.initialConnectionDone = True

    def retryLoop(self):
        while self.shouldRun:
            try:
                if self.initialConnectionDone:
                    time.sleep(60*10)
                    continue


                time.sleep(60*10)

                with self.connectLock:
                    if not self.initialConnectionDone:
                        connectRateLimit.limit()
                        self.initialConnection()
            except Exception:
                self.handle_error(traceback.format_exc())

    def __init__(self, name, data, **kw):
        device.Device.__init__(self, name, data, **kw)
        self.shouldRun = False
        try:
            self.set_config_default("device.user_id", "")
            self.set_config_default("device.key", "")

            self.numeric_data_point("connected",subtype="bool", writable=False)
            self.set_alarm("Disconnected from YoLink API", 'connected', "value < 1", priority="warning", trip_delay=25)

            self.dowlinkRateLimit = RateLimiter(60, 60 * 10)

            self.devices_by_id = {}

            self.initialConnectionDone = False

            self.connectLock = threading.RLock()

            if self.config['device.key']:
                with self.connectLock:
                    if not self.initialConnectionDone:
                        connectRateLimit.limit()
                        try:
                            self.initialConnection()
                        except Exception:
                            self.handle_error(traceback.format_exc())
                            t = threading.Thread(
                                target=self.retryLoop, name="YoLinkConnectionRetry")
                            t.start()

        except Exception:
            self.handle_error(traceback.format_exc())

    @classmethod
    def discover_devices(cls, config={}, current_device=None, intent=None, **kw):
        return {}
