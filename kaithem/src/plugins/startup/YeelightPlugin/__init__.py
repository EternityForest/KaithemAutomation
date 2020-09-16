#Plugin that manages YeeLight devices.

from src import devices,alerts, scheduling,tagpoints,messagebus
import os,mako,time,threading,logging

try:
    from yeelight import discover_bulbs
except:
    logger.exception()
    messagebus.postMessage("/system/notifications/errors","Problem loading YeeLight support")

from src import widgets

logger = logging.Logger("plugins.yeelight")

from mako.lookup import TemplateLookup
templateGetter = TemplateLookup(os.path.dirname(__file__))


lookup={}

lastRefreshed = 0

lock = threading.Lock()

def maybeRefresh(t=30):
    global lastRefreshed
    if lastRefreshed<time.time()-t:
        refresh()
    elif lastRefreshed<time.time()-5:
        refresh(1)

def refresh(timeout=8):
    global lastRefreshed,lookup
    from yeelight import discover_bulbs
    lastRefreshed= time.time()
    
    d = discover_bulbs()
    l={}

    for i in d:
        if 'name' in i['capabilities']:
            l[i['capabilities']['name']]=i
            l[i['ip']]=i
    lookup=l



def isIp(x):
    x=x.strip().split('.')
    try:
        x = [int(i) for i in x]
        if len(x)==4:
            return True
    except:
        return False
    
def getDevice(locator,timeout=10,klass=None):
    """Since plugs can change name, you should't keep a reference
    to a plug for too long. Instead use this function.
    """
    global lookup
    if not isIp(locator):
        if locator in lookup:
            return lookup[locator]
        
        maybeRefresh()
        if locator in lookup:
            return lookup[locator]
        
    return klass(locator)


class YeelightDevice(devices.Device):
    def __init__(self,name,data):
        self.lock = threading.Lock()
        devices.Device.__init__(self,name,data)

        self.rssiTag = tagpoints.Tag("/devices/"+name+".rssi")
        self.rssiTag.setAlarm("LowSignal", "value< - 90", priority='warning')

        self.tagPoints["rssi"] = self.rssiTag

        self.rssiTag.value =-120
        self.rssiCacheTime = 0

        self.lastLoggedUnreachable = 0

        try:

            if not data.get("device.locator",''):
                self.setDataKey("device.locator",data.get('temp.locator',''))
            
            #If we were given separate temp and permanent names, then we use the temp
            #To find the device and set it to the proper permanent name
            if not data['device.locator']==data.get('temp.locator',data['device.locator']):
                getDevice(data['temp.locator'],5,self.kdClass).alias = data['device.locator']
                refresh()

        except:
            self.handleError()
            
    def getRawDevice(self):
        return getDevice(self.data.get("device.locator"),3,self.kdClass)

    def rssi(self,cacheFor=120,timeout=3):
        "These bulbs don't have RSSI that i found, instead we just detect reachability or not"
        with self.lock:
            "Returns the current RSSI value of the device"
            if time.monotonic()-self.rssiCacheTime<cacheFor:
                return self.rssiTag.value

            #Not ideal, but we really can't be retrying this too often.
            #if it's disconnected. Way too much slowdown
            self.rssiCacheTime=time.monotonic()


            try:
                info = getDevice(self.data.get("device.locator"),timeout,self.kdClass).get_properties()

                if 'hue' in info:
                    self.hwidget.write(float(info['hue']))
                if 'sat' in info:
                    self.swidget.write(float(info['sat'])/100)
                if 'bright' in info:
                    self.hwidget.write(float(info['bright'])/100)

                self.rssiTag.value= -70
            except:
                self.rssiTag.value= -120
                if self.lastLoggedUnreachable< time.monotonic()-30:
                    self.handleError("Device was unreachable")
                    self.lastLoggedUnreachable=time.monotonic()
                raise


            return self.rssiTag.value

    @staticmethod
    def getCreateForm():
        return templateGetter.get_template("createform.html").render()


import yeelight

class YeelightRGB(YeelightDevice):
    deviceTypeName="YeelightRGB"
    kdClass = yeelight.Bulb
    descriptors={
        "kaithem.device.hsv": 1,
        "kaithem.device.powerswitch":1,
    }

    def __init__(self,name,data):
        YeelightDevice.__init__(self,name,data)
        self.lastHueChange = time.monotonic()

        #Set it up with a tagpoint
        self.switchTagPoint = tagpoints.Tag("/devices/"+self.name+".switch")
        self.switchTagPoint.min=0
        self.switchTagPoint.max=1
        self.switchTagPoint.owner= "YeeLight"



        self.tagPoints["switch"] = self.switchTagPoint
        

        def switchTagHandler(v,ts, a):
            try:
                self.setSwitch(0,v>=0.5)
            except:
                pass


        self.sth = switchTagHandler

        #We use the handler to set this. This means that an error will
        #Be raised if we try to set the tag with an unreachable device
        self.switchTagPoint.setHandler(switchTagHandler)

        #We probably don't need to poll this too often
        self.switchTagPoint.interval= 5

        self.tagPoints["switch"]=self.switchTagPoint
    
        def onf(user,value):
            if 'pushed' in value:
                self.setSwitch(0,True)

        def offf(user,value):
            if 'pushed' in value:
                self.setSwitch(0,False)

        def hsvf(user,value):
            if time.monotonic()-self.lastHueChange>1:
                self.setHSV(0,self.hwidget.value,self.swidget.value,self.vwidget.value)
                self.lastHueChange=time.monotonic()

        self.hwidget = widgets.Slider(max=360)
        self.swidget = widgets.Slider(max=1,step=0.01)
        self.vwidget = widgets.Slider(max=1,step=0.01)
        self.csetButton = widgets.Button()

        self.csetButton.attach(hsvf)
    


        self.onButton = widgets.Button()

        self.offButton=widgets.Button()
        self.onButton.attach(onf)
        self.offButton.attach(offf)
        self.huesat =-1
        self.lastVal =-1
        self.wasOff=True
        self.oldTransitionRate = -1

    def getSwitch(self,channel, state):
        if channel>0:
            raise ValueError("Bulb has 1 master power channel only")
        return  self.getRawDevice().is_on




    def setSwitch(self,channel, state,duration=1):
        logger.debug("Setting smartplug "+self.data.get("device.locator")+ "to state "+str(state))
        with self.lock:
            "Set the state of switch channel N"
            if channel>0:
                raise ValueError("This is a 1 channel device")
            try:
                if state:
                    getDevice(self.data.get("device.locator"),3,self.kdClass).turn_on(effect="smooth", duration=duration)
                    self.wasOff=False
                else:
                    getDevice(self.data.get("device.locator"),3,self.kdClass).turn_off(effect="smooth",duration=duration)
                    self.wasOff=True
                self.oldTransitionRate=duration
            except:
                if self.lastLoggedUnreachable< time.monotonic()-30:
                    self.handleError("Device was unreachable")
                    self.lastLoggedUnreachable=time.monotonic()
                self.rssiTag.value =-120
                raise

            #Obviously not unreachable
            self.rssiTag.value =-70
    
    def setHSV(self,channel, hue,sat,val,duration=1):
        if channel>0:
            raise ValueError("Bulb has 1 color only")

        #The idea here is that if the color has not changed, 
        #We can issue a direct on/off command instead, which is both more semantic,
        #And in theory less damaging to flash memory if they did it right.
        huesat = (int(hue),int(sat*100))

        if huesat == self.huesat or val < 0.01 or (val==self.lastVal):
            if val < 0.01:
                self.wasOff = True
                self.setSwitch(0,False,duration)
            else:
                if self.wasOff and (huesat == self.huesat) and (val==self.lastVal):
                    self.setSwitch(0,True,duration)
                else:
                    self.getRawDevice().set_hsv(int(hue),int(sat*100),int(val*100),effect="smooth", duration=duration)
                    self.lastVal=val
                    self.huesat = huesat
                self.wasOff=False

        else:
            self.getRawDevice().set_hsv(int(hue),int(sat*100),int(val*100),effect="smooth", duration=duration if not self.wasOff else 0)
            if self.wasOff:
                self.wasOff=False
                self.setSwitch(0,True,duration)

            self.huesat = huesat
            self.lastVal = val

    @staticmethod
    def getCreateForm():
        return templateGetter.get_template("createform.html").render()

    def getManagementForm(self):
        return templateGetter.get_template("bulbpage.html").render(data=self.data,obj=self)

devices.deviceTypes["YeelightRGB"]=YeelightRGB
