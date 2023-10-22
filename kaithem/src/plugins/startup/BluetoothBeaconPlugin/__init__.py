import logging
import time,threading,os
import weakref
from kaithem.src import messagebus
from kaithem.src import tagpoints

from collections import OrderedDict
from weakref import WeakValueDictionary
lock = threading.Lock()

tags = weakref.WeakValueDictionary()

from kaithem.src import kaithemobj




def scan():
    while 1:
            time.sleep(9)
            with lock:
                try:
                    for i in tags:
                        #If the last signal was very strong, we don't need to wait as long before considering
                        #it gone, because packet loss will be less
                        m = 3 if tags[i].value > -65 else 7

                        if tags[i]._bleTimestamp<time.monotonic()-(tags[i].interval*m):
                            tags[i]._bleTimestamp=time.monotonic()
                            tags[i].value=-180
                except:
                    logging.exception("BLE err")                            
                        

t = threading.Thread(target=scan,name="BluetoothPresenceBot",daemon=True)
t.start()

from mako.lookup import TemplateLookup

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""

from kaithem.src import devices
import json
import uuid

class EspruinoHubBLEClient(devices.Device):
    deviceTypeName = 'EspruinoHubBLEClient'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode
    shortDescription="This device lets you get BLE data from one specific BLE device via an EspruinoHub server"



    def __init__(self, name, data):
        raise RuntimeError("This plugin not supported till it is rewritten not to use kaithem.mqtt")
        devices.Device.__init__(self, name, data)

        try:
            self.tagpoints["rssi"] = tagpoints.Tag("/devices/"+name+".rssi")
            self.tagpoints["rssi"].default = -180
            self.tagpoints["rssi"].min = -180
            self.tagpoints["rssi"].max = 12
            self.tagpoints["rssi"].max = 12
            self.tagpoints["rssi"].interval = float(data.get("device.interval",5))
            self.tagpoints["rssi"]._bleTimestamp = time.monotonic()

            data['device.id']=data.get('device.id','').lower().strip()

            self.connection = kaithemobj.kaithem.mqtt.Connection(
                data.get("device.server", "localhost"),
                int(data.get("device.port", "1883").strip() or 1883),
                password=data.get("device.password", "").strip(),
                connectionID=str("EspruinoConnection")
            )
            self.tagPoints['EspruinoHubStatus'] = self.connection.statusTag


            topic = data.get("device.mqtttopic","/ble/")


            def onRSSI(t,m):
                m=float(m)
                self.tagpoints['rssi'].value=m
            def onBattery(t,m):
                m=float(m)
                if not 'battery' in self.tagpoints:
                    self.tagpoints["battery"] = tagpoints.Tag("/devices/"+name+".battery")
                self.tagpoints['battery'].value=m

            def onEspruino(t,m):
                m=json.loads(m)
                if not 'espruino' in self.tagpoints:
                    self.tagpoints["espruino"] = tagpoints.tagpoints.ObjectTag("/devices/"+name+".espruino")
                self.tagpoints['espruino'].value=m

            def onUrl(t,m):
                m=json.loads(m)
                if not 'url' in self.tagpoints:
                    self.tagpoints["url"] = tagpoints.tagpoints.StringTag("/devices/"+name+".url")
                self.tagpoints['url'].value=m


            def onTemp(t,m):
                m=float(m)
                if not 'temp' in self.tagpoints:
                    self.tagpoints["temp"] = tagpoints.Tag("/devices/"+name+".temp")
                    self.tagpoints['temp'].unit = "degC"

                self.tagpoints['temp'].value = m

            def onHum(t,m):
                m=float(m)
                if not 'humidity' in self.tagpoints:
                    self.tagpoints["humidity"] = tagpoints.Tag("/devices/"+name+".humidity")
                    self.tagpoints['humidity'].unit = "%"
                    self.tagpoints['humidity'].min = 0
                    self.tagpoints['humidity'].max = 100

                self.tagpoints['humidity'].value = m

            def onPres(t,m):
                m=float(m)
                if not 'pressure' in self.tagpoints:
                    self.tagpoints["pressure"] = tagpoints.Tag("/devices/"+name+".pressure")
                    self.tagpoints['pressure'].unit = "pa"


                self.tagpoints['pressure'].value = m

            
            def onWeight(t,m):
                m=float(m)
                if not 'weight' in self.tagpoints:
                    self.tagpoints["weight"] = tagpoints.Tag("/devices/"+name+".weight")
                    #self.tagpoints['weight'].unit = "pa"


                self.tagpoints['weight'].value = m

            def onHeartRate(t,m):
                m=float(m)
                if not 'heartRate' in self.tagpoints:
                    self.tagpoints["heartRate"] = tagpoints.Tag("/devices/"+name+".heartRate")
                self.tagpoints['heartRate'].value = m


            def onJSON(t,m):
                m=json.loads(m)

                if 'rssi' in m:
                    onRSSI(0,m['rssi'])
                if 'humidity' in m:
                    onHum(0,m['humidity'])
                if 'temp' in m:
                    onTemp(0,m['temp'])
                if 'pressure' in m:
                    onPres(0,m['pressure'])
                if 'battery' in m:
                    onBattery(0,m['battery'])
                if 'espruino' in m:
                    onEspruino(0,json.dumps(m['espruino']))

                if 'weight' in m:
                    onWeight(0,m['weight'])

            self.noGarbage =[onJSON,onTemp,onHum,onPres,onEspruino,onJSON]

            if data['device.id']:
                self.connection.subscribe(topic+"advertise/"+data['device.id']+"/rssi",onRSSI,encoding="raw")
                self.connection.subscribe(topic+"advertise/"+data['device.id']+"/temp",onTemp,encoding="raw")
                self.connection.subscribe(topic+"advertise/"+data['device.id']+"/humidity",onHum,encoding="raw")
                self.connection.subscribe(topic+"advertise/"+data['device.id']+"/pressure",onPres,encoding="raw")
                self.connection.subscribe(topic+"advertise/"+data['device.id']+"/espruino",onEspruino,encoding="raw")
                self.connection.subscribe(topic+"advertise/"+data['device.id'],onJSON,encoding="raw")



        except:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["EspruinoHubBLEClient"] = EspruinoHubBLEClient
