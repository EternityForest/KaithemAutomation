from iot_devices import device
import requests
import json
import time
import os
import sys
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
"""


class YoLinkMQTTClient(object):

    def __init__(self, uid, key, homeid, parent, mqtt_port=8003, client_id=os.getpid()):

        self.topic = "yl-home/" + homeid + "/+/report"
        self.mqtt_url = mqtt_url
        self.mqtt_port = int(mqtt_port)
        self.key = key
        self.parent = parent

        self.client = mqtt.Client(client_id=str(__name__ + str(client_id)),
                                  clean_session=True, userdata=None,
                                  protocol=mqtt.MQTTv311, transport="tcp")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        # self.client.tls_set()

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()

    def connect_to_broker(self):
        """
        Connect to MQTT broker
        """

        log.info("Connecting to broker...")

        self.client.username_pw_set(username=self.key)
        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect

        self.client.connect(self.mqtt_url, self.mqtt_port, 10)
        self.client.loop_start()

    def on_message(self, client, userdata, msg):
        """
        Callback for broker published events
        """
        try:
            payload = json.loads(msg.payload.decode("utf-8"))

            deviceId = payload['deviceId']

            if deviceId in self.parent.devices_by_id:
                self.parent.devices_by_id[deviceId].onData(payload)

        except Exception:
            error = sys.exc_info()[0]
            log.info("Error reading payload: %s" % error)

    def on_connect(self, client, userdata, flags, rc):
        """
        Callback for connection to broker
        """
        log.info("Connected with result code %s" % rc)

        if (rc == 0):
            log.info("Successfully connected to broker %s" % self.mqtt_url)
            self.client.subscribe(self.topic)
            self.parent.connected = True

        else:
            log.info("Connection with result code %s" % rc)
            sys.exit(2)



def listify(d):
    if not isinstance(d, list):
        d = [d]
    return d


class YoLinkDevice(device.Device):
    device_type = "YoLinkDevice"

    def __init__(self, name: str, config: Dict[str, str], **kw):
        super().__init__(name, config, **kw)
        self.numeric_data_point("battery", min=0, max=100, lo=15, writable=False)
        self.numeric_data_point("signal", min=0, max=1, lo=-98, writable=False)
        self.set_alarm('signal', 'signal', 'value < -98')
        self.set_alarm('Low Battery', 'battery', 'value < 30')

    def onData(self, data):

        if 'loraInfo' in data:
            s = data['loraInfo']['signal']
            self.set_data_point('signal', s)
            self.metadata['Gateway ID'] = data['loraInfo']['gatewayID']

        if 'deviceId' in data:
            self.metadata['Device ID'] = data['deviceId']


        if 'battery' in data:
                battery = data['battery'] * (100 / 4)
                self.set_data_point('battery', battery)

        if 'data' in data:
            if 'battery' in data['data']:
                battery = data['data']['battery'] * (100 / 4)
                self.set_data_point('battery', battery)
            if 'soundLevel' in data['data']:
                self.metadata['Sound Level'] = data['data']['soundLevel']

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
        self.numeric_data_point("open", min=0, max=1, subtype='bool', writable=False)

    def onData(self, data):
        YoLinkDevice.onData(self, data)
        if not data['event'] in ('DoorSensor.Alert', 'DoorSensor.Report'):
            return

        open = 0 if (data['data']['state'] == 'closed') else 1
        self.set_data_point('open', open)

    def refresh(self):
        self.simpleMethod("DoorSensor.getState")

class YoLinkOutlet(YoLinkDevice):
    device_type = "YoLinkOutlet"

    def __init__(self, name: str, config: Dict[str, str], **kw):
        super().__init__(name, config, **kw)
        self.numeric_data_point("open", min=0, max=1,
                                subtype='bool', handler=self.setState)

    def onData(self, data):
        YoLinkDevice.onData(self, data)
        if not data['event'] == 'Outlet.Report':
            return

        open = 0 if (data['data']['state'] == 'closed') else 1
        self.set_data_point('open', open)

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
        self.numeric_data_point("leak", min=0, max=1, subtype='bool', writable=False)
        self.set_alarm('Water Detected', 'leak', 'value > 0',
                       priority='critical', auto_ack=True, trip_delay=5)

    def onData(self, data):
        YoLinkDevice.onData(self, data)
        if not data['event'] in ('LeakSensor.Report', 'LeakSensor.Alert'):
            return

        leak = 0 if (data['data']['state'] == 'normal') else 1
        self.set_data_point('leak', leak)

    def refresh(self):
        self.simpleMethod("LeakSensor.getState")

class YoLinkSiren(YoLinkDevice):
    device_type = "YoLinkSiren"

    def __init__(self, name: str, config: Dict[str, str], **kw):
        super().__init__(name, config, **kw)
        self.numeric_data_point("on", min=0, max=1, subtype='bool')
        self.numeric_data_point(
            "usb_power", min=0, max=1, lo=0, subtype='bool')

        self.numeric_data_point("trigger", subtype='trigger',
                                description="Trigger a momentary siren", handler=self.doSiren)

        self.numeric_data_point("cancel", subtype='trigger',
                                description="Stop an active siren", handler=self.stopSiren)

        self.set_alarm('PowerFail', 'usb_power', 'value < 1', priority='error', writable=False)


    def refresh(self):
        self.simpleMethod("Siren.getState")

    def doSiren(self, v,*a, **k):
        self.downlink({
            'method': "Siren.setState",
            'params': {
                'state':
                {'alarm': True}
            }
        })

    def stopSiren(self, v,*a, **k):
        self.downlink({
            'method': "Siren.setState",
            'params': {
                'state':
                {'alarm': False}
            }
        })


    def onData(self, data):
        YoLinkDevice.onData(self, data)

        if not data['event'] == 'Siren.Report':
            return
        on = 0 if (data['data']['state'] == 'normal') else 1
        usb = 1 if (data['data']['powerSupply'] == 'usb') else 0

        self.set_data_point('on', on)
        self.set_data_point('usb_power', usb)


class YoLinkTemperatureSensor(YoLinkDevice):
    device_type = "YoLinkTemperatureSensor"

    def __init__(self, name: str, config: Dict[str, str], **kw):
        super().__init__(name, config, **kw)
        self.numeric_data_point("temperature", min=-40,
                                max=100, unit='degC', writable=False)
        self.numeric_data_point("humidity", min=0, max=100, unit='%', writable=False)

    def onData(self, data):
        if not data['event'] == 'THSensor.Report':
            return

        temp = data['data']['temperature']
        humidity = data['data']['humidity']

        self.set_data_point('temperature', temp)
        self.set_data_point('humidity', humidity)

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
        try:
            data['time'] = int(time.time())

            self.client.client.publish(
                "yl-home" + "/" + self.homeId + "/" + device + "/request", json.dumps(data))

        except Exception:
            self.handle_error(traceback.format_exc())

    def __init__(self, name, data):
        device.Device.__init__(self, name, data)
        try:
            self.set_config_default("device.user_id", "")
            self.set_config_default("device.key", "")

            self.devices_by_id = {}

            if self.config['device.key']:
                # self.create_subdevice(YoLinkBinarySensor, "Subdevice", {'type': "YoLinkBinarySensor"})

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

                print(devList)

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
                    uniqueName = "YoLink_" + t + "_" + i['deviceUDID']

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
        except Exception:
            self.handle_error(traceback.format_exc())
    @classmethod
    def discover_devices(cls, config={}, current_device=None, intent=None, **kw):
        return {}
