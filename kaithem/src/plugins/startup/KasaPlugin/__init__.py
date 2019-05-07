#Plugin that manages TP-Link Kasa devices.

from src import remotedevices,alerts, scheduling,tagpoints
import os,mako,time,threading,logging

from src import widgets

logger = logging.Logger("plugins.kasa")

from mako.lookup import TemplateLookup
templateGetter = TemplateLookup(os.path.dirname(__file__))


allDevices = {}
lookup={}

lastRefreshed = 0

lock = threading.Lock()

def maybeRefresh(t=30):
    global lastRefreshed
    if lastRefreshed<time.time()-t:
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
    if locator in allDevices:
        return allDevices[locator]
    else:
        maybeRefresh()
        return allDevices[locator]
class KasaSmartplug(remotedevices.RemoteDevice):
    deviceTypeName="KasaSmartplug"
    descriptors={
        "kaithem.device.powerswitch":1,
        "kaithem.device.rssi":-80
    }

    def __init__(self,name,data):
        remotedevices.RemoteDevice.__init__(self,name,data)
        self.lock = threading.Lock()
        self.rssiCache =0
        self.rssiCacheTime = 0

        #Assume no e-meter till we're told otherwise
        self._has_emeter = False

        self.analogChannels=[["W"]]

        #We really don't need either of these to have persistent alerts.
        self.lowSignalAlert = alerts.Alert(name+".lowsignalalert",tripDelay=80,autoAck=True)
        self.unreachableAlert = alerts.Alert(name+".unreachablealert", autoAck=True)
        self.highCurrentAlert = alerts.Alert(priority='warning', name=name+".highcurrentalert", autoAck=False)
        self.overCurrentAlert = alerts.Alert(priority='error', name=name+".overcurrentalert", autoAck=False)

        #Set it up with a tagpoint
        self.switchTagPoint = tagpoints.Tag("/devices/"+self.name+".switch")
        self.switchTagPoint.min=0
        self.switchTagPoint.max=1
        self.switchTagPoint.owner= "Kasa Smartplug"

        self.tagPoints={
            "switch": self.switchTagPoint
        }

        def switchTagHandler(v):
            try:
                self.setSwitch(0,v>=0.5)
            except:
                pass

        def switchTagGetter():
            try:
                return 1 if self.getSwitch(0) else 0
            except:
                return None
        self.switchTagPoint.claim(switchTagGetter)

        self.sth = switchTagHandler

        #We use the handler to set this. This means that an error will
        #Be raised if we try to set the tag with an unreachable device
        self.switchTagPoint.setHandler(switchTagHandler)

        #We probably don't need to poll this too often
        self.switchTagPoint.interval= 3600

        self.tagPoints={
            "switch":self.switchTagPoint
        }

        self.alerts={
            "unreachableAlert":self.unreachableAlert,
            "lowSignalAlert": self.lowSignalAlert,
            'highCurrentAlert':self.highCurrentAlert,
            'overCurrentAlert':self.overCurrentAlert
        }

       

       
        self.setAlertPriorities()
        try:
            #Check RSSI as soon as we create the obj to trigger any alerts based on it.
            self.rssi()
        except:
            pass
        self.s = scheduling.scheduler.everyMinute(self._pollRssi)

        def onf(user,value):
            if 'pushed' in value:
                self.setSwitch(0,True)
        def offf(user,value):
            if 'pushed' in value:
                self.setSwitch(0,False)
        
        self.onButton = widgets.Button()
        self.offButton=widgets.Button()
        self.onButton.attach(onf)
        self.offButton.attach(offf)

        self.powerWidget = widgets.Meter(high_warn=float(data.get("device.alarmcurrent",1400)), max=1600,min=0)

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data,obj=self)

    def setSwitch(self,channel, state):
        logger.debug("Setting smartplug "+self.data.get("locator")+ "to state "+str(state))
        with self.lock:
            "Set the state of switch channel N"
            if channel>0:
                raise ValueError("This is a 1 channel device")
            try:
                if state:
                    if not self.overCurrentAlert.sm.state=="normal":
                        raise RuntimeError("You cannot turn the switch on while the overcurrent shutdown has an unacknowledged error")
                    getDevice(self.data.get("locator")).turn_on()
                else:
                    getDevice(self.data.get("locator")).turn_off()
            except:
                self.handleError("Device was unreachable")
                self.unreachableAlert.trip()
                raise

            #Obviously not unreachable if we just got the RSSI!
            self.unreachableAlert.clear()

    def getSwitch(self,channel):
        with self.lock:
            "Set the state of switch channel N"
            if channel>0:
                raise ValueError("This is a 1 channel device")
            try:
                s = getDevice(self.data.get("locator")).state=="ON"
            except:
                self.handleError("Device was unreachable")
                self.unreachableAlert.trip()
                raise

            #Obviously not unreachable if we just got the RSSI!
            self.unreachableAlert.clear()
            return s
        
    
    def getEnergyStats(self,channel):
        if channel>0:
            raise ValueError("This is a 1 channel device")
        try:
            s = getDevice(self.data.get("locator")).get_emeter_realtime()
            self.doOvercurrentHandling(s)
        except:
            #Try to get RSSI to test if it works at all and set the alert as needed.
            try:
                self.rssi()
            except:
                pass
            raise
        #Obviously not unreachable if we just got the RSSI!
        self.unreachableAlert.clear()
        return s

    def _pollRssi(self):
        "Background polling of RSSI to detect when things are available or not"
        
        #No reason to poll if we already know we can't reach it.
        if not self.data.get('locator',None):
            return
        try:
            self.rssi()
            #Also do this here as well
            self._pollEnergy()
        except:
            pass

    def _pollEnergy(self):
        "Background polling of RSSI to detect when things are available or not"        
        #No reason to poll if we already know we can't reach it.
        if not self.data.get('locator',None):
            return
        #Don't bother if we don't have the meter anyway
        if not self._has_emeter:
            return
        try:
            self.getEnergyStats(0)
        except:
            logging.exception("Err")

    def doOvercurrentHandling(self,x):
        w= x['current']*x['voltage']
        self.powerWidget.write(w)

        limit = float(self.data.get("device.alarmcurrent", 1500))
        hardlimit =float(self.data.get("device.maxcurrent", 1600))

        if w> limit:
            self.highCurrentAlert.trip()
        else:
            self.highCurrentAlert.clear()
            self.overCurrentAlert.clear()

        #Note: does nothing about multiple channels.
        if w>hardlimit:
            self.setSwitch(0, False)
            self.overCurrentAlert.trip()

    def rssi(self):
        with self.lock:
            "Returns the current RSSI value of the device"
            if time.time()-self.rssiCacheTime<5:
                return self.rssiCache

            try:
                info = getDevice(self.data.get("locator")).get_sysinfo()
                self.rssiCache= info['rssi']
                #It's just a handy place to get this info because
                #we're getting sysinfo anyway.
                self._has_emeter = ('model' in info) and ('HS110' in info['model'])
            except:
                self.handleError("Device was unreachable")
                self.unreachableAlert.trip()
                raise

            #Obviously not unreachable if we just got the RSSI!
            self.unreachableAlert.clear()
            self.rssiCacheTime=time.time()

            if self.rssiCache>-85:
                self.lowSignalAlert.clear()
            if self.rssiCache<-89:
                self.lowSignalAlert.trip()

            return self.rssiCache

remotedevices.deviceTypes["KasaSmartplug"]=KasaSmartplug