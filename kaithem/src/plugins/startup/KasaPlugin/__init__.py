#Plugin that manages TP-Link Kasa devices.

from src import remotedevices
import os,mako,time,threading,logging

logger = logging.Logger("plugins.kasa")

from mako.lookup import TemplateLookup
templateGetter = TemplateLookup(os.path.dirname(__file__))


allDevices = {}
lookup={}

lastRefreshed = 0

lock = threading.Lock()

def maybeRefresh():
    if lastRefreshed<time.time()-30:
        refresh()

def refresh():
    global lastRefreshed,lookup
    from pyHS100 import Discover
    lastRefreshed= time.time()
    allDevices=  Discover.discover()
    l={}

    #Build a structure that allows lookup by both type and IP address
    for i in allDevices:
        try:
            l[allDevices[i].alias] = allDevices[i]
        except:
            logger.exception()
    lookup=l


def getDevice(locator):
    """Since plugs can change name, you should't keep a reference
    to a plug for too long. Instead use this function.
    """
    if locator in lookup:
        return lookup[locator]
    else:
        return allDevices[locator]

class KasaDevice(remotedevices.RemoteDevice):
    deviceTypeName="KasaDevice"
    descriptors={
        "kaithem.device.powerswitch":1,
        #all powerswitches are also analogsensors
        "kaithem.device.analogsensor":None,
        "kaithem.device.powermeter":None,
        "kaithem.device.rssi":-80
    }

    def __init__(self,name,data):
        remotedevices.RemoteDevice.__init__(self,name,data)
        self.rssiCache =0
        self.rssiCacheTime = 0

        self.analogChannels=[["W"]]


    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data,obj=self)

    def setSwitch(self,channel, state):
        if channel>0:
            raise ValueError("This is a 1 channel device")

        if state:
            getDevice(self.data.get("locator")).turn_on()
        else:
            getDevice(self.data.get("locator")).turn_off()



    def rssi(self):
        "Returns the current RSSI value of the device"
        if time.time()-self.rssiCacheTime<5:
            return self.rssiCache

        self.rssiCache= getDevice(self.data.get("locator")).get_sysinfo()['rssi']
        self.rssiCacheTime=time.time()

        return self.rssiCache

remotedevices.deviceTypes["KasaDevice"]=KasaDevice