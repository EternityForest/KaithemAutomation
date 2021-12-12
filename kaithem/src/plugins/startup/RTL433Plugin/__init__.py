import logging
import time
import threading
import os
import weakref
from src import messagebus
from src import tagpoints

from collections import OrderedDict
from weakref import WeakValueDictionary
lock = threading.Lock()

tags = weakref.WeakValueDictionary()

from src import kaithemobj


def scan():
    while 1:
        time.sleep(9)
        with lock:
            try:
                for i in tags:
                    # If the last signal was very strong, we don't need to wait as long before considering
                    # it gone, because packet loss will be less
                    m = 3 if tags[i].value > -65 else 7

                    if tags[i]._rtlTimestamp < time.monotonic() - (tags[i].interval * m):
                        tags[i]._rtlTimestamp = time.monotonic()
                        tags[i].value = -180
            except:
                logging.exception("RTL err")


t = threading.Thread(target=scan, name="RTLPresenceBot")
t.start()

from mako.lookup import TemplateLookup

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""

from src import devices
import json
import uuid


class RTL433Client(devices.Device):
    deviceTypeName = 'RTL433Client'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode
    shortDescription = "This device lets you get data from a device using an RTL433 daemon and MQTT"

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)

        try:
            self.tagpoints["rssi"] = tagpoints.Tag("/devices/" + name + ".rssi")
            self.tagpoints["rssi"].default = -180
            self.tagpoints["rssi"].min = -180
            self.tagpoints["rssi"].max = 12
            self.tagpoints["rssi"].max = 12
            self.tagpoints["rssi"].interval = float(
                data.get("device.interval", 300))
            self.tagpoints["rssi"].description = "-75 if recetly seen, otherwise -180, we don't have real RSSI data"

            self.tagpoints["rssi"]._rtlTimestamp = time.monotonic()

            data['device.id'] = data.get('device.id', '').lower().strip()

            self.connection = kaithemobj.kaithem.mqtt.Connection(
                data.get("device.server", "localhost"),
                int(data.get("device.port", "1883").strip() or 1883),
                password=data.get("device.password", "").strip(),
                connectionID=str("RTL433Connection")
            )
            self.tagPoints['MqttStatus'] = self.connection.statusTag

            topic = data.get("device.mqtttopic", "home/rtl_433")

            # We cannot use priority greater than info because these are unencrypted and untruusted and higher could make noise.

            def onBattery(t, m):
                m = float(m)
                if not 'battery' in self.tagpoints:
                    self.tagpoints["battery"] = tagpoints.Tag(
                        "/devices/" + name + ".battery")
                    self.tagpoints["battery"].setAlarm(
                        "Low battery", "timestamp and value< 15", priority="info")

                self.tagpoints['battery'].value = m

            def onWind(t, m):
                m = float(m)
                if not 'wind' in self.tagpoints:
                    self.tagpoints["wind"] = tagpoints.Tag(
                        "/devices/" + name + ".wind")
                    self.tagpoints['wind'].unit = "km/h"
                    self.tagpoints["wind"].setAlarm(
                        "High wind", "value > 35", priority="info")

                self.tagpoints['wind'].value = m

            def onTemp(t, m):
                m = float(m)
                if not 'temp' in self.tagpoints:
                    self.tagpoints["temp"] = tagpoints.Tag(
                        "/devices/" + name + ".temp")
                    self.tagpoints['temp'].unit = "degC"
                    self.tagpoints["temp"].setAlarm(
                        "Freezing temperature", "timestamp and value <0", priority="info")

                self.tagpoints['temp'].value = m

            def onHum(t, m):
                m = float(m)
                if not 'humidity' in self.tagpoints:
                    self.tagpoints["humidity"] = tagpoints.Tag(
                        "/devices/" + name + ".humidity")
                    self.tagpoints['humidity'].unit = "%"
                    self.tagpoints['humidity'].min = 0
                    self.tagpoints['humidity'].max = 100

                self.tagpoints['humidity'].value = m

            def onMoist(t, m):
                m = float(m)
                if not 'moisture' in self.tagpoints:
                    self.tagpoints["moisture"] = tagpoints.Tag(
                        "/devices/" + name + ".moisture")
                    self.tagpoints['moisture'].unit = "%"
                    self.tagpoints['moisture'].min = 0
                    self.tagpoints['moisture'].max = 100

                self.tagpoints['moisture'].value = m

            def onPres(t, m):
                m = float(m)
                if not 'pressure' in self.tagpoints:
                    self.tagpoints["pressure"] = tagpoints.Tag(
                        "/devices/" + name + ".pressure")
                    self.tagpoints['pressure'].unit = "pa"

                self.tagpoints['pressure'].value = m

            def onWeight(t, m):
                m = float(m)
                if not 'weight' in self.tagpoints:
                    self.tagpoints["weight"] = tagpoints.Tag(
                        "/devices/" + name + ".weight")
                    #self.tagpoints['weight'].unit = "pa"

                self.tagpoints['weight'].value = m

            def onCommandCode(t, m):
                if not 'lastCommandCode' in self.tagpoints:
                    self.tagpoints["lastCommandCode"] = tagpoints.ObjectTag(
                        "/devices/" + name + ".lastCommandCode")
                self.tagpoints['lastCommandCode'].value = (m, time.time())


            def onCommandName(t, m):
                if not 'lastCommandName' in self.tagpoints:
                    self.tagpoints["lastCommandName"] = tagpoints.ObjectTag(
                        "/devices/" + name + ".lastCommandName")
                self.tagpoints['lastCommandName'].value = (m, time.time())

            def onJSON(t, m):
                m = json.loads(m)
                self.print(m, "Saw packet on air")

                # Going to do an ID match.
                if 'device.id' in self.data:
                    if not ('id' in m and str(m['id']) == self.data['id']):
                        self.print(m, "Packet filter miss")
                        return

                if 'device.model' in self.data:
                    if not ('model' in m and m['model'] == self.data['device.model']):
                        self.print(m, "Packet filter miss")
                        return

                self.print(m, "Packet filter hit")

                # No real RSSI
                self.tagpoints['rssi'].value = -75
                self.tagpoints["rssi"]._rtlTimestamp = time.monotonic()

                if 'humidity' in m:
                    onHum(0, m['humidity'])

                if 'moisture' in m:
                    onHum(0, m['moisture'])

                if 'temperature_C' in m:
                    onTemp(0, m['temperature_C'])

                if 'wind_avg_km_h' in m:
                    onWind(0, m['wind_avg_km_h'])

                if 'pressure_kPa' in m:
                    onPres(0, m['pressure_kPa'] * 1000)

                if 'pressure_hPa' in m:
                    onPres(0, m['pressure_hPa'] * 100)

                # Keep a percent based API with randomly chosen high and low numbers
                if 'battery_ok' in m:
                    onBattery(0, 100 if m['battery'] else 5)

                if 'cmd' in m:
                    onCommandCode(0, m['cmd'])
                

                if 'button_id' in m:
                    onCommandCode(0, m['button_id'])


                if 'button_name' in m:
                    onCommandName(0, m['button_name'])

                if 'event' in m:
                    onCommandName(0, m['event'])
                
                if 'code' in m:
                    onCommandCode(0, m['code'])

                    

            self.noGarbage = [onJSON]

            self.connection.subscribe(
                    topic, onJSON, encoding="raw")

        except:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["RTL433Client"] = RTL433Client
