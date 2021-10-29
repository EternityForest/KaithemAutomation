import logging
import time,threading, logging,os
import weakref
from src import tagpoints

from collections import OrderedDict
from weakref import WeakValueDictionary
allBLEDevices = OrderedDict()
lock = threading.Lock()

tags = weakref.WeakValueDictionary()

class BT():
    def __init__(self) -> None:
        self._allBLEDevices=allBLEDevices
        self._lock = lock

from src import kaithemobj
kaithemobj.kaithem.blebeacons = BT() 


def callback(addr, rssi, packet, additional_info):
    with lock:
        allBLEDevices[addr]=rssi
        if "uuid" in additional_info:
            allBLEDevices[additional_info['uuid']]=rssi
        if "identifier" in additional_info:
            allBLEDevices[additional_info['identifier']]=rssi
        if "url" in additional_info:
            allBLEDevices[additional_info['url']]=rssi
        if "namespace" in additional_info and "instance" in additional_info:
            allBLEDevices[additional_info['namespace']+":"+ additional_info['instance'] ]=rssi


        while len(allBLEDevices)>4096:
            allBLEDevices.popitem(False)

    try:
        if addr in tags:
            tags[addr].value = rssi
        
        if "uuid" in additional_info and additional_info['uuid'] in tags:
            tags[additional_info['uuid']].value = rssi
            tags[additional_info['uuid']].bleTimestamp=time.monotonic()
        
        elif "identifier" in additional_info and additional_info['identifier'] in tags:
            tags[additional_info['identifier']].value = rssi
            tags[additional_info['identifier']]._bleTimestamp=time.monotonic()
        
        elif "url" in additional_info and additional_info['url'] in tags:
            tags[additional_info['url']].value = rssi
            tags[additional_info['url']]._bleTimestamp=time.monotonic()

        elif "namespace" in additional_info and "instance" in additional_info:
            x = additional_info['namespace']+":"+ additional_info['instance'] 
            if x in tags:
                tags[x].value = rssi
                tags[x]._bleTimestamp=time.monotonic()
    except:
        logging.exception("U can probably ignore this")


import time

from beacontools import BeaconScanner

# scan for all TLM frames of beacons in the namespace "12345678901234678901"
scanner = BeaconScanner(callback)
scanner.start()


def scan():
    #Don't rely on the scanner not to leak addresses
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
                        

t = threading.Thread(target=scan,name="BluetoothWatcher")
t.start()

from mako.lookup import TemplateLookup

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""

from src import devices

class BluetoothBeacon(devices.Device):
    deviceTypeName = 'BluetoothBeacon'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode



    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)

        try:
            self.tagpoints["rssi"] = tagpoints.Tag("/bt/"+name+".rssi")
            self.tagpoints["rssi"].default = -180
            self.tagpoints["rssi"].min = -180
            self.tagpoints["rssi"].max = 12
            self.tagpoints["rssi"].max = 12
            self.tagpoints["rssi"].interval = float(data.get("device.interval",5))

            self.tagpoints["rssi"]._bleTimestamp = time.monotonic()

            tags[data['device.id']] = self.tagpoints["rssi"]
        except:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["BluetoothBeacon"] = BluetoothBeacon