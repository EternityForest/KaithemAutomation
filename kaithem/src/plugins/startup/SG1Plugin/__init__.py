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

from src import widgets

logger = logging.Logger("plugins.sg1")

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


sc_code = """
class CustomDeviceType(DeviceType):
    def onMessage(self,m):
        title= "Incoming SG1 Message"

        if m.get("req"):
            title= "Incoming SG1 Request"
            # Uncommemt respond with empty message
            # self.sendMessage(b'', replyTo=m)

        if m.get("replyTo"):
            title= "Incoming SG1 Reply"

        self.print(m,title)

    def onSpecialMessage(self,m):
        self.print(m, "Incoming SG1 Special Message")  

    def onRTMessage(self,m):
        self.print(m, "Incoming SG1 RT Message")
    
    def onBeacon(self,m):
        self.print(m, "Incoming Beacon")
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

            self.rssiTag = tagpoints.Tag("/devices/"+name+".rssi")
            self.rssiTagClaim = self.rssiTag.claim(self.rssi, "HWStatus", 60)
            self.rssiTag.setAlarm(name+'.SG1DeviceLowSignal', "value < -94",
                                  tripDelay=(self.expectedMessageInterval*1.3))
            
            self.rssiTag.unit = "dBm"

            # No redundant alarm, only alarm when auto tx power can no longer keep up
            self.pathLossTag = tagpoints.Tag("/devices/"+name+".pathloss")
            self.pathLossTagClaim = self.pathLossTag.claim(
                self.pathLoss, "HWStatus", 60)
            
            self.pathLossTag.unit= "dBm"


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

    def status(self):
        return str(self.rssiTag.value)+"dB"

    def wakeButtonHandler(self, u, v):
        # Note that this sends one wake request that lasts 30s only
        if "pushed" in v:
            self.dev.sendWakeRequest()
            self.print('User pressed wake button')

    def apiWidgetHandler(self, u, v):
        # Note that this sends one wake request that lasts 30s only
        if v[0] == "sendExpr":
            x = [int(i, 16 if 'x' in i else 10) for i in v[1].split(",")]
            self.sendMessage(bytes(x))
            self.print('User sent data: '+str(x))

        if v[0] == "sendText":
            self.sendMessage(bytes(v[1],'utf8'))
            self.print('User sent request data: '+str(v[1]))

        if v[0] == "sendExprReq":
            x = [int(i, 16 if 'x' in i else 10) for i in v[1].split(",")]
            self.sendMessage(bytes(x), request=True)
            self.print('User sent request data: '+str(x))

        if v[0] == "sendExprRT":
            x = [int(i, 16 if 'x' in i else 10) for i in v[1].split(",")]
            self.sendMessage(bytes(x), rt=True)
            self.print('User sent request data: '+str(x))

        if v[0] == "sendTextRT":
            self.sendMessage(bytes(v[1],'utf8'), rt=True)
            self.print('User sent request data: '+str(v[1]))


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

    def sendMessage(self, msg, rt=False, power=-127, special=False, request=False,replyTo=False):
        if rt:
            limit = 64 - (3+4+4)
        else:
            limit = 64 - (6 + 3 + 8 + 8)
        if len(msg) > limit:
            raise ValueError("Message cannot be longer than " +
                             str(limit)+" when rt="+str(rt))

        if request and replyTo:
            raise ValueError("Message cannot be both request and reply")

        self.dev.sendMessage(msg, rt, power, request=request, special=special, replyTo=replyTo)

    def close(self):
        Device.close(self)
        self.dev.close()

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
        self.gatewayUtilizationTag = tagpoints.Tag(
            "/devices/"+name+".rxUtilization")

        devices.Device.__init__(self, name, data)
        self.tagPoints['status'] = self.gatewayStatusTag
        self.tagPoints['noiseFloor'] = self.gatewayNoiseTag
        self.tagPoints['utilization'] = self.gatewayUtilizationTag

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

        self.tagpoints = {"status": self.gatewayStatusTag}

        self.print("GW obj created")
    def onNoiseMeasurement(self, noise):
        if self.gatewayNoiseTag.value == 0:
            self.gatewayNoiseTag.value = noise

        b = 1 if(noise >= self.activityThreshold) else 0

        self.gatewayUtilizationTag.value = self.gatewayUtilizationTag.value*0.98 + b*0.02

        # Don't count anything above the threshold as noise, it is probably utilization.
        # And we want to give the real floor.
        if b == 0:
            self.gatewayNoiseTag.value = self.gatewayNoiseTag.value*0.98 + noise*0.02
    def onHWMessage(self, t):
        self.print(t)

    def status(self):
        return self.gatewayStatusTag.value

    def close(self):
        self.gw.close()
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
