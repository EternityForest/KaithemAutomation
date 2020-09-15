from mako.lookup import TemplateLookup
from . import sg1
from src import devices, alerts, scheduling, tagpoints, workers
import os
import mako
import time
import threading
import logging
import weakref
import base64
import traceback
import textwrap

from src import widgets

logger = logging.Logger("plugins.sg1")
syslogger = logging.Logger("system")

templateGetter = TemplateLookup(os.path.dirname(__file__))

# Message bus names: i=incoming msg, ri=incoming realtime, b=incoming beacon


class Gateway(sg1.SG1Gateway):
    def __init__(self, *args,  kaithemInterface=None, **kwargs):
        self.kaithemInterface = kaithemInterface
        sg1.SG1Gateway.__init__(self, *args, **kwargs)

    def onNoiseMeasurement(self, noise):
        self.kaithemInterface().onNoiseMeasurement(noise)

    def onHWMessage(self, t):
        try:
            self.kaithemInterface().onHWMessage(t.decode('utf-8', errors='backslashreplace'))
        except:
            self.kaithemInterface().handleException()

    def onConnect(self):
        self.kaithemInterface().onConnect()
        self.kaithemInterface().print("Connected to gateway")

        def f():
            time.sleep(3)
            self.kaithemInterface().print(
                "serial round-trip latency(avg,min,max): "+str(self.testLatency()))
        workers.do(f)
        return super().onConnect()

    def onDisconnect(self):
        return super().onDisconnect()
        self.kaithemInterface().print("Disconnected from gateway")
        self.kaithemInterface().onDisconnect()

    def handleError(self, s):
        self.kaithemInterface().print(s, "ERROR")
        
sc_code = """
class CustomDeviceType(DeviceType):
    #def  writeStructured(type,channel, data): write a structured record to the structured TX buffer
    #def flushStructured(): flush the structured TX buffer
    #def sendMessage(self, msg, rt=False, power=-127): Send msg with the specified power, -127 for automatic.  If rt is true, send an RT message instead.

    #keepAwake: this must be a callable.  While it is true, the gawteway should respond to beacons by keeping the device awake.
    #def sendWakeRequest():  Tell the gw to keep the device awake for 30 seconds. May do nothing if the device does not beacon in that time

    def onMessage(self,m):
        title= "Incoming SG1 Message"

        self.print(m,title)

    def onRTMessage(self,m):
        self.print(m, "Incoming SG1 RT Message")
    
    def onBeacon(self,m):
        # Low power beacons.  Generally you would use this to know when a device is wake-able
        # to send it data.   Not all devices use beacons or sleep though.
        self.print(m, "Incoming Beacon")

    def onStructuredMessage(self,m):
        # m['data'] will be a list of [type, channel, data] tuples
        self.print(m, "Incoming Structured Message")
"""


class Device(sg1.SG1Device):

    def __init__(self, *args,  kaithemInterface=None, **kwargs):
        self.kaithemInterface = kaithemInterface
        sg1.SG1Device.__init__(self, *args, **kwargs)

    def onMessage(self, m):
        try:
            self.kaithemInterface()._onMessage(m)
        except:
            self.kaithemInterface().handleException()


    def onStructuredMessage(self, m):
        try:
            self.kaithemInterface()._onStructuredMessage(m)
        except:
            self.kaithemInterface().handleException()

    def onSpecialMessage(self, m):
        try:
            self.kaithemInterface()._onSpecialMessage(m)
        except:
            self.kaithemInterface().handleException()

    def onRTMessage(self, m):
        try:
            self.kaithemInterface()._onRTMessage(m)
        except:
            self.kaithemInterface().handleException()

    def onBeacon(self, m):
        try:
            self.kaithemInterface()._onBeacon(m)
        except:
            self.kaithemInterface().handleException()
    
    def handleError(self, s):
        self.kaithemInterface().print(s, "ERROR")

def formatConfigData(d):


    d = d.hex()
    x=''
    while d:
        b =d[:16]
        d=d[16:]
        x+=(b+(' ' if d else ''))
        
    
    return '<br>'.join(textwrap.wrap(x,16*4+3))

class SG1Device(devices.Device):
    deviceTypeName = 'SG1Device'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = sc_code

    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        try:
            self.lock = threading.Lock()

            self.lastSeen = 0
            self.lastRSSI = -127
            self.lastPathLoss = 140
            self.expectedMessageInterval = float(
                data.get("device.expectedMessageInterval", 60))

            self.localNodeID = float(
                data.get("device.localNodeID", 60))

            self.rssiTag = tagpoints.Tag("/devices/"+name+".rssi")
            self.rssiTagClaim = self.rssiTag.claim(self.rssi, "HWStatus", 60)
            self.rssiTag.setAlarm(name+'.SG1DeviceLowSignal', "value < -94",
                                  tripDelay=(self.expectedMessageInterval*1.3))
            
            self.rssiTag.unit = "dBm"
            self.rssiTag.min=-140
            self.rssiTag.max = -20

            # No redundant alarm, only alarm when auto tx power can no longer keep up
            self.pathLossTag = tagpoints.Tag("/devices/"+name+".pathloss")
            self.pathLossTagClaim = self.pathLossTag.claim(
                self.pathLoss, "HWStatus", 60)
            
            self.pathLossTag.unit= "dBm"
            self.pathLossTag.min=0
            self.pathLossTag.max = 180
            self.pathLossTag.hi = 90

            # update at 2x the rate because nyquist or something.
            self.rssiTag.interval = self.expectedMessageInterval/2
            self.pathLossTag.interval = self.expectedMessageInterval/2
            self.tagPoints['rssi'] = self.rssiTag
            self.tagPoints['pathloss'] = self.pathLossTag

            d = str(data.get("device.channelKey", 'A'*32))
            if len(d) <= 32:
                d += 'A'*(32-len(d))
                d = d.encode("ascii")
            else:
                d = base64.b64decode(d)

            self.dev = Device(
                kaithemInterface=weakref.ref(self),
                channelKey=d,
                nodeID=int(data.get("device.nodeID", '0')),
                gateways=data.get("device.gateways", "__all__").split(","),
                mqttServer=data.get(
                    "device.mqttServer", "__virtual__SG1"),
                mqttPort=int(
                    data.get("device.mqttPort", 1883))
            )
        except:
            self.handleError(traceback.format_exc(chain=True))



        self.wakeButton = widgets.Button()
        self.wakeButton.attach(self.wakeButtonHandler)
        self.wakeButton.require("/admin/settings.edit")

        self.apiWidget = widgets.APIWidget()
        self.apiWidget.attach(self.apiWidgetHandler)
        self.apiWidget.require("/admin/settings.edit")

        self.configDataWidget = widgets.DynamicSpan()
        self.configDataWidget.attrs= 'style="font-family:monospace;"'


        self.currentConfigData = bytearray(256)

        self.configDataWidget.write(formatConfigData(self.currentConfigData))

        #We can detect missing config data by noting whether the sequence is continuous or not
        self.lastRecievedConfigPage = 0
        self.lastSavedConfigData=0


        self.writeStructured = self.dev.writeStructured
        self.flushStructured = self.dev.flushStructured

    
    def getConfigDataFromDevice(self):
        "Request that the device return it's config data string"
        self.dev.writeStructured(sg1.RECORD_CONFIG_GET,b'\0', 0)
        self.dev.flushStructured()

    def writeConfigData(self,c):
        "Write the entire config data string to the remote devicve"
        self.getConfigDataFromDevice()
        time.sleep(3)
        if isinstance(c,str):
            #Cleanup allows directly inputting hyman readable data
            c =bytes.fromhex(c.replace("0x",'').replace(' ','').replace('\n','').replace('\r','').replace('\t',''))

        s=time.monotonic()
        while not bytes(self.currentConfigData).startswith(c):
            if time.monotonic()-s>5:
                raise RuntimeError("Timeout while setting device config")

            c2 = c
            b=0
            while c2:
                x = c2[:8]
                c2=c2[8:]
                self.dev.writeStructured(sg1.RECORD_CONFIG_SET,x,b)
                b+=1
                self.dev.flushStructured()
                time.sleep(0.1)
            time.sleep(0.5)

    
    def saveConfigData(self):
        "Tell the remote device to save it's config data in nonvolatile memory"
        x = self.lastSavedConfigData
        s=time.monotonic()
        while x == self.lastSavedConfigData:
            if time.monotonic()-s>5:
                raise RuntimeError("Timeout while saving device config")
            self.dev.writeStructured(sg1.RECORD_CONFIG_SAVE,b' ',0)
            self.dev.flushStructured()
            time.sleep(0.5)

    def status(self):
        return str(self.rssiTag.value)+"dB"

    def wakeButtonHandler(self, u, v):
        # Note that this sends one wake request that lasts 30s only
        if "pushed" in v:
            self.dev.sendWakeRequest()
            self.print('User pressed wake button')

    def apiWidgetHandler(self, u, v):
        # Note that this sends one wake request that lasts 30s only
        try:
            if v[0] == "sendExpr":
                x = [int(i, 16 if 'x' in i else 10) for i in v[1].split(",")]
                self.sendMessage(bytes(x))
                self.print('User sent data: '+str(x))

            if v[0] == "sendText":
                self.sendMessage(bytes(v[1],'utf8'))
                self.print('User sent text data: '+str(v[1]))

            if v[0] == "sendExprRT":
                x = [int(i, 16 if 'x' in i else 10) for i in v[1].split(",")]
                self.sendMessage(bytes(x), rt=True)
                self.print('User sent RT data: '+str(x))

            if v[0] == "sendTextRT":
                self.sendMessage(bytes(v[1],'utf8'), rt=True)
                self.print('User sent RT text data: '+str(v[1]))

            if v[0] == "getConfigData":
                self.getConfigDataFromDevice()

            if v[0] == "setConfig":
                self.writeConfigData(v[1])


            if v[0] == "saveConfig":
                self.saveConfigData()
        except:
            self.handleException()

    def _onStructuredMessage(self,m):
        for i in m['data']:
            #config declaration, we must update our local copy of what we think config should be
            if i[0]==sg1.RECORD_CONFIG_DECLARE:
                
                if i[1]<32 and i[1] and (not i[1]==(self.lastRecievedConfigPage+1)):
                    self.handleError("Recieved config page:"+str(i[i])+ "Expected: "+str(self.lastRecievedConfigPage)+ " please refresh the config data")
                    self.lastRecievedConfigPage = i[1]
                
                #Discard the random access bit
                p = i[1]&31
                
                

                for j,k in enumerate(i[2]):
                    self.currentConfigData[p*8 +j]=k
                
                self.configDataWidget.write(formatConfigData(self.currentConfigData))

            if i[0]==7:
                if i[1]==1:
                    self.lastSavedConfigData=time.monotonic()



        try:
            self.onStructuredMessage(m)
        except:
            self.handleError(traceback.format_exc(chain=True))

    def onStructuredMessage(self,m):
        self.print(m,'Structured Message')


    @property
    def keepAwake(self):
        return self.dev.keepAwake

    @keepAwake.setter
    def keepAwake(self, val):
        self.dev.keepAwake = val

    def rssi(self):
        # Get the most recent RSSI from the device, or -127 if we have not recieved any correct
        # Messages at all recently
        if self.lastSeen > (time.monotonic()-self.expectedMessageInterval):
            return self.lastRSSI
        else:
            return -127

    def pathLoss(self):
        # Get the most recent RSSI from the device, or -127 if we have not recieved any correct
        # Messages at all recently
        if self.lastSeen > (time.monotonic()-self.expectedMessageInterval):
            return self.lastPathLoss
        else:
            return 140

    def _onMessage(self, m):
        self.lastRSSI = m['rssi']
        self.lastPathLoss = m['loss']

        self.lastSeen = time.monotonic()
        # Trigger the tag to refresh
        self.rssiTag.pull()
        self.pathLossTag.pull()

        try:
            self.onMessage(m)
        except:
            self.handleError(traceback.format_exc(chain=True))

    def _onSpecialMessage(self, m):
        self.lastRSSI = m['rssi']
        self.lastPathLoss = m['loss']

        self.lastSeen = time.monotonic()
        # Trigger the tag to refresh
        self.rssiTag.pull()
        self.pathLossTag.pull()

        try:
            self.onMessage(m)
        except:
            self.handleError(traceback.format_exc(chain=True))

    def _onRTMessage(self, m):
        self.lastRSSI = m['rssi']
        self.lastSeen = time.monotonic()
        # Trigger the tag to refresh
        self.rssiTag.pull()
        self.pathLossTag.pull()

        try:
            self.onRTMessage(m)
        except:
            self.handleError(traceback.format_exc(chain=True))
    def _onBeacon(self, m):
        self.lastRSSI = m['rssi']
        self.lastPathLoss = m['loss']
        self.lastSeen = time.monotonic()
        # Trigger the tag to refresh
        self.rssiTag.pull()
        self.pathLossTag.pull()

        try:
            self.onBeacon(m)
        except:
            self.handleError(traceback.format_exc(chain=True))

    def onMessage(self, m):
        self.print(str(m))

    def onRTMessage(self, m):
        self.print(m)
    
    #Don't clutter the page with background time sync stuff
    def onSpecialMessage(self, m):
        pass

    def onBeacon(self, m):
        self.print(m)

    def sendMessage(self, msg, rt=False, power=-127):
        if rt:
            limit = 64 - (3+4+4)
        else:
            limit = 64 - (6 + 3 + 8 + 8)
        if len(msg) > limit:
            raise ValueError("Message cannot be longer than " +
                             str(limit)+" when rt="+str(rt))

        self.dev.sendMessage(msg, rt, power, special=False)

    def close(self):
        Device.close(self)

        try:
            self.dev.close()
        except:
            syslogger.exception("Could not close device")
            messagebus.postMessage("/system/notifications/errors","Failed to close device:"+self.name)

    @staticmethod
    def getCreateForm():
        return templateGetter.get_template("createform_device.html").render()

    def getManagementForm(self):
        return templateGetter.get_template("manageform_device.html").render(data=self.data, obj=self)


class SG1Gateway(devices.Device):
    deviceTypeName = 'SG1Gateway'

    def __init__(self, name, data):
        self.lock = threading.Lock()
        self.gatewayStatusTag = tagpoints.StringTag("/devices/"+name+".status")
        self.gatewayStatusTagClaim = self.gatewayStatusTag.claim(
            'disconnected', "HWStatus", 60)
        self.gatewayStatusTag.setAlarm(
            name+".SG1GatewayDisconnected", "value != 'connected'", tripDelay=15)

        self.gatewayNoiseTag = tagpoints.Tag("/devices/"+name+".noiseFloor")
        self.gatewayNoiseTag.unit= "dBm"
        self.gatewayNoiseTag.min= -140
        self.gatewayNoiseTag.max= -60
        self.gatewayNoiseTag.hi= -85

        self.gatewayUtilizationTag = tagpoints.Tag(
            "/devices/"+name+".rxUtilization")
        self.gatewayUtilizationTag.max =1
        self.gatewayUtilizationTag.min=0
        self.gatewayUtilizationTag.hi = 0.75

        devices.Device.__init__(self, name, data)
        self.tagpoints['status'] = self.gatewayStatusTag
        self.tagpoints['noiseFloor'] = self.gatewayNoiseTag
        self.tagpoints['utilization'] = self.gatewayUtilizationTag

        self.gatewayNoiseTag.setAlarm(
            name+'.RFNoiseFloor', "value > -98", tripDelay=60)
        self.gatewayUtilizationTag.setAlarm(
            name+'.RFExcessiveChannelUtilization', "value > 0.8", tripDelay=60)

        self.activityThreshold = float(data.get("device.ccaThreshold", "-94"))

        self.gw = Gateway(
            kaithemInterface=weakref.ref(self),
            port=data.get("device.serialport", "/dev/ttyUSB0"),
            id=data.get("device.gatewayID", "default"),
            mqttServer=data.get(
                "device.mqttServer", "__virtual__SG1"),
            mqttPort=int(
                data.get("device.mqttPort", 1883)),
            rfProfile=int(
                data.get("device.rfProfile", 7)),
            channelNumber=int(
                data.get("device.channelNumber", 3))
        )

        self.gw.kaithemInterface = weakref.ref(self)


        self.print("GW obj created")

    def onNoiseMeasurement(self, noise):
        if self.gatewayNoiseTag.value == 0:
            self.gatewayNoiseTag.value = noise

        b = 1 if(noise >= self.activityThreshold) else 0

        self.gatewayUtilizationTag.value = self.gatewayUtilizationTag.value*0.98 + b*0.02

        # Don't count anything above the threshold as noise, it is probably utilization.
        # And we want to give the real floor.
        if b == 0:
            self.gatewayNoiseTag.value = self.gatewayNoiseTag.value*0.95 + noise*0.05
        else:
            #At the same time, under 100% utilization, we need to correctly show that the
            #Background level is extremely high, so we still update the noise tag, just much slower
            self.gatewayNoiseTag.value = self.gatewayNoiseTag.value*0.99 + noise*0.01


    def onHWMessage(self, t):
        self.print(t)

    def status(self):
        return self.gatewayStatusTag.value

    def close(self):
        try:
            self.gw.close()
        except:
            syslogger.exception("Could not close device")
            messagebus.postMessage("/system/notifications/errors","Failed to close device:"+self.name)

        devices.Device.close(self)

    def onConnect(self):
        self.gatewayStatusTagClaim.set("connected")

    def onDisconnect(self):
        self.gatewayStatusTagClaim.set("disconnected")
        self.print("Disconnected from gateway")

    @staticmethod
    def getCreateForm():
        return templateGetter.get_template("createform_gateway.html").render()

    def getManagementForm(self):
        return templateGetter.get_template("manageform_gateway.html").render(data=self.data, obj=self)


devices.deviceTypes["SG1Gateway"] = SG1Gateway
devices.deviceTypes["SG1Device"] = SG1Device
