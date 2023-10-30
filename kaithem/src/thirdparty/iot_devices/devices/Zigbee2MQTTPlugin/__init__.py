from inspect import isawaitable
import os
import time
import logging

import colorzero

import iot_devices.device

logger = logging.Logger("plugins.zigbee2mqtt")


def hex_to_xy(hex):
    c = colorzero.Color.from_string(hex)
    x, y, z = c.xyz

    return (x / (x + y + z), y / (x + y + z), y)


def xy_to_hex(x, y, Y):
    Y = 1
    X = (x * Y) / y
    Z = ((1 - x - y) * Y) / y
    return colorzero.Color.from_xyz(X, Y, Z).html


class Zigbee2MQTT(iot_devices.device.Device):
    device_type = 'Zigbee2MQTT'

    description = "Connects to a Zigbee2MQTT gateway and makes the devices accessible via a tags API"

    def pair(self, t=120):
        #Enable pairing for 120 seconds
        self.connection.publish('zigbee2mqtt/bridge/request/permit_join', {
            "value": True,
            "time": t
        })

    def __init__(self, name, data, **kw):
        iot_devices.device.Device.__init__(self, name, data, **kw)
        self.devicesData = []

        self.knownDevices = {}

        self.nameToType = {}
        self.nameToTopic = {}
        self.nameToZBInfo = {}
        self.nameToHandler = {}

        self.set_config_default("device.mqtt_server", 'localhost')
        self.set_config_default("device.friendly_name", '__all__')

        try:
            from kaithem.src.scullery import mqtt

            #Ensure a new real connection.  This makes sure we get any retained messages.
            self.connection = mqtt.getConnection(
                self.config['device.mqtt_server'],
                connectionID=str(time.time()))

            self.connection.subscribe('zigbee2mqtt/bridge/devices',
                                      self.onDevices)
        except Exception:
            self.handleException()

    def on_data_point_change(self, tn, v, t, a):
        if not a == 'ZigBee':
            if tn in self.nameToZBInfo:
                type = self.nameToType[tn]
                topic = self.nameToTopic[tn]
                j = self.nameToZBInfo[tn]

                if type == "bool":
                    # Convert back to zigbee2mqtt's idea of true/false
                    self.connection.publish(topic + "/set", {
                        j['property']: (j['value_on'] if v else j['value_off'])
                    })

                elif type == 'color_xy':
                    # Convert back to zigbee2mqtt's idea of true/false
                    c = hex_to_xy(v)
                    self.connection.publish(
                        topic + "/set",
                        {j['property']: {
                             'x': c[0],
                             'y': c[1]
                         }})

                elif type == 'numeric' or type == 'string' or type == 'enum':
                    self.connection.publish(topic + "/set", {j['property']: v})

    def onDevices(self, t, v):
        self.devicesData = v

        d = {}
        for i in v:
            if not 'friendly_name' in i:
                continue
            d[i['friendly_name']] = True

            if 'definition' in i and i['definition']:
                if 'exposes' in i['definition']:

                    for f in i['definition']['exposes']:

                        # Normally the inner loop is just dealing with one expose
                        x = [f]

                        isWritable = (f.get("access", 2) & 2) > 0

                        isALight = False
                        # Sometimes there are multiple features
                        if f['type'] in ['switch', 'fan', 'climate']:
                            x = f['features']

                        if f['type'] in ['light']:
                            x = f['features']
                            isALight = True

                        for j in x:
                            if self.config['device.friendly_name'].strip() in (
                                    "*", "any", "__all__", ''):
                                tn = "node/" + i['friendly_name'] + '.' + j[
                                    'property']
                            else:
                                if not self.config[
                                        'device.friendly_name'].strip().lower(
                                        ) == i['friendly_name'].lower():
                                    continue
                                tn = j['property']
                            zn = "zigbee2mqtt/" + i['friendly_name']

                            #Internally we represent all colors as the standard but kinda mediocre CSS strings,
                            #Since ZigBee seems to like to separate color and brightness, we will do the same thing here.
                            if j['name'] == 'color_xy' and isALight:
                                self.string_data_point(
                                    "node/" + i['friendly_name'] + "." +
                                    j['property'],
                                    subtype="color",
                                    writable=isWritable)

                                def f(t, v, tn=tn, j=j):
                                    if j['property'] in v:
                                        v = v[j['property']]
                                        v = xy_to_hex(v['x'], v['y'], 1)
                                        self.set_data_point(
                                            tn, v, annotation='ZigBee')

                                self.nameToTopic[tn] = zn
                                self.nameToZBInfo[tn] = j
                                self.nameToType[tn] = 'color_xy'

                                try:
                                    self.connection.unsubscribe(
                                        zn, self.nameToHandler[tn])
                                except:
                                    pass

                                self.connection.subscribe(zn, f)
                                self.nameToHandler[tn] = f

                            elif j['type'] == 'numeric':
                                self.numeric_data_point(
                                    tn,
                                    min=j.get("value_min", None),
                                    max=j.get("value_max", None),
                                    step=j.get("value_step", None),
                                    unit=j.get("unit", None).replace(
                                        "°", 'deg').replace("lqi", "%"),
                                    writable=isWritable)

                                if 'unit' in j:
                                    # Link quality low signal alarms
                                    if j['unit'] == 'lqi':
                                        self.set_alarm(name="LowSignal",
                                                       datapoint=tn,
                                                       expression="value < 8",
                                                       priority='info',
                                                       trip_delay=60)

                                    if j['name'] == 'battery':
                                        #Timestamp means wait for at least one actual data point
                                        self.set_alarm(name="LowBattery",
                                                       datapoint=tn,
                                                       expression="value < 33",
                                                       priority='warning')

                                def f(t, v, tn=tn, j=j):
                                    if j['property'] in v:
                                        self.set_data_point(
                                            tn,
                                            v[j['property']],
                                            annotation="ZigBee")

                                self.nameToTopic[tn] = zn
                                self.nameToZBInfo[tn] = j
                                self.nameToType[tn] = 'numeric'

                                try:
                                    self.connection.unsubscribe(
                                        zn, self.nameToHandler[tn])
                                except Exception:
                                    pass

                                self.connection.subscribe(zn, f)
                                self.nameToHandler[tn] = f

                            elif j['type'] == 'binary':
                                self.numeric_data_point(tn,
                                                        min=0,
                                                        max=1,
                                                        writable=isWritable)

                                if j['name'] == 'tamper':
                                    self.set_alarm(name="Tamper",
                                                   datapoint=tn,
                                                   expression="value",
                                                   priority='error')

                                if j['name'] == 'battery_low':
                                    self.set_alarm(name="BatteryLow",
                                                   datapoint=tn,
                                                   expression="value",
                                                   priority='warning')

                                if j['name'] == 'gas':
                                    self.set_alarm(name="GAS",
                                                   datapoint=tn,
                                                   expression="value",
                                                   priority='critical')

                                if j['name'] == 'smoke':
                                    self.set_alarm(name="SMOKE",
                                                   datapoint=tn,
                                                   expression="value",
                                                   priority='critical')

                                if j['name'] == 'water_leak':
                                    self.set_alarm(name="WATERLEAK",
                                                   datapoint=tn,
                                                   expression="value",
                                                   priority='critical')

                                if j['name'] == 'carbon_monoxide':
                                    self.set_alarm(name="CARBONMONOXIDE",
                                                   datapoint=tn,
                                                   expression="value",
                                                   priority='critical')

                                def f(t, v, tn=tn, j=j):
                                    if j['property'] in v:
                                        #Convert back to proper true/false
                                        v = v[j['property']] == j['value_on']
                                        self.set_data_point(
                                            tn,
                                            1 if v else 0,
                                            annotation='ZigBee')

                                self.nameToType[tn] = "bool"
                                self.nameToTopic[tn] = zn
                                self.nameToZBInfo[tn] = j

                                try:
                                    self.connection.unsubscribe(
                                        zn, self.nameToHandler[tn])
                                except Exception:
                                    pass

                                self.connection.subscribe(zn, f)
                                self.nameToHandler[tn] = f

                            #Todo: Tag points need to support enums
                            elif j['type'] in ['enum', 'text']:
                                self.string_data_point(tn, writable=isWritable)

                                def f(t, v, tn=tn, j=j):
                                    if j['property'] in v:
                                        self.set_data_point(
                                            tn,
                                            v[j['property']],
                                            annotation='ZigBee')

                                self.nameToType[tn] = j['type']
                                self.nameToTopic[tn] = zn
                                self.nameToZBInfo[tn] = j

                                try:
                                    self.connection.unsubscribe(
                                        zn, self.nameToHandler[tn])
                                except Exception:
                                    pass

                                self.connection.subscribe(zn, f)
                                self.nameToHandler[tn] = f

    def on_ui_message(self, v):
        # Note that this sends one wake request that lasts 30s only
        try:
            if v[0] == "enablePairing":
                self.pair()
                self.print(
                    "New ZigBee devices will be accepted for 120 seconds")

        except Exception:
            self.handleException()
