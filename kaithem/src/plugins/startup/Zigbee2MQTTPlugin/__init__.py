from mako.lookup import TemplateLookup
import scullery
from src import devices, alerts, scheduling, messagebus, workers, directories
import subprocess
import os
import mako
import time
import threading
import logging
import weakref
import base64
import traceback
import shutil
import socket
import uuid
import socket

from src import widgets

logger = logging.Logger("plugins.zigbee2mqtt")

templateGetter = TemplateLookup(os.path.dirname(__file__))


defaultSubclassCode = """
class CustomDeviceType(DeviceType):
    pass
"""

from src import tagpoints

import colorzero


def hex_to_xy(hex):
    c = colorzero.Color.from_string(hex)
    x,y,x = c.xyz

    return (x/(x+y+z), y/(x+y+z), y) 

def xy_to_hex(x,y,Y): 
    Y=1 
    X=(x*Y)/y 
    Z=((1-x-y)*Y)/y
    return colorzero.Color.from_xyz(X,Y,Z).html



class Zigbee2MQTT(devices.Device):
    deviceTypeName = 'Zigbee2MQTT'
    readme = os.path.join(os.path.dirname(__file__), "README.md")
    defaultSubclassCode = defaultSubclassCode

    def pair(self,t=120):
        #Enable pairing for 120 seconds
        self.connection.publish('zigbee2mqtt/bridge/request/permit_join',{"value": True, "time": t})
    
    def __init__(self, name, data):
        devices.Device.__init__(self, name, data)
        self.devicesData = []
        
        
        self.apiWidget = widgets.APIWidget()
        self.apiWidget.attach(self.apiWidgetHandler)
        self.apiWidget.require("/admin/settings.edit")

        self.knownDevices ={}

        self.exposeConverters = {}
        
        try:
            from scullery import mqtt
            #Ensure a new real connection.  This makes sure we get any retained messages.
            self.connection = mqtt.getConnection(data.get('server','localhost') or 'localhost', connectionID=str(time.time()))

            self.connection.subscribe('zigbee2mqtt/bridge/devices', self.onDevices)
        except Exception:
            self.handleException()

    def onDevices(self, t,v):
        self.devicesData=v
        self.apiWidget.send(['devices', self.devicesData])

        d = {}
        for i in v:
            if not 'friendly_name' in i:
                continue
            d[i['friendly_name']]=True


            if 'definition' in i and i['definition']:
                if 'exposes' in i['definition']:
                    
                    for f in i['definition']['exposes']:

                        #Normally the inner loop is just dealing with one expose
                        x=[f]

                        isALight=False
                        #Sometimes there are multiple features
                        if f['type'] in ['switch','fan','climate']:
                            x=f['features']
                        
                        if f['type'] in ['light']:
                            x=f['features']
                            isALight=True

                        for j in x:
                            tn = i['friendly_name']+'/'+j['property']

                            zn = "zigbee2mqtt/"+i['friendly_name']


                            #Internally we represent all colors as the standard but kinda mediocre CSS strings,
                            #Since ZigBee seems to like to separate color and brightness, we will do the same thing here.
                            if j['property']=='color' and j['name']=='color_xy' and isALight:
                                self.tagPoints[tn] = tagpoints.StringTag("/devices/"+self.name+"/node/"+i['friendly_name']+"/"+j['property'])
                                self.tagPoints[tn].unit = 'color'

                                def f(t,v,tn=tn,j=j):
                                    v =v[j['property']]
                                    v =xy_to_hex(v['x'],v['y'],1)
                                    self.tagpoints[tn].defaultClaim.set(v,annotation='ZigBee')
                                
                                def f2(v,t,a,tn=tn,j=j):
                                    if not a == 'ZigBee':
                                        #Convert back to zigbee2mqtt's idea of true/false
                                        c = hex_to_xy(v)
                                        self.connection.publish(zn+"/set", {j['property']:{'x':c[0], 'y': c[1]}})
                                
                                try:
                                    self.tagpoints[tn].unsubscribe( self.tagpoints[tn].zigbeeHandler)
                                except:
                                    pass

                                try:
                                    self.connection.unsubscribe(zn, self.tagpoints[tn].incomingHandler)
                                except:
                                    pass
                                self.connection.subscribe(zn, f)
                                self.tagpoints[tn].incomingHandler = f

                                self.tagpoints[tn].subscribe(f2)
                                self.tagpoints[tn].zigbeeHandler = f2
                                self.tagpoints[tn].deviceFriendlyName = i['friendly_name']


                          
                                self.exposeConverters[tn]=f

                            if j['type'] == 'numeric':
                                self.tagPoints[tn] = tagpoints.Tag("/devices/"+self.name+"/node/"+i['friendly_name']+"."+j['property'])

                                if 'value_min' in j:
                                    self.tagPoints[tn].min = j['value_min']
                                if 'value_max' in j:
                                    self.tagPoints[tn].max = j['value_max']
                                if 'value_step' in j:
                                    self.tagPoints[tn].step = j['value_step']
                                if 'unit' in j:
                                    self.tagPoints[tn].unit = j['unit'].replace("°",'deg')

                                    #Link quality low signal alarms
                                    if j['unit']=='lqi':
                                        #Timestamp means wait for at least one actual data point
                                        self.tagPoints[tn].setAlarm("LowSignal", "value < 8 and timestamp", priority='warning')
                                        #Assume that all devices check in at least once a day.
                                        self.tagPoints[tn].setAlarm("Offline", "timestamp and timestamp<(time.monotonic()-(36*3600))", priority='warning')

                                    if j['name']=='battery':
                                        #Timestamp means wait for at least one actual data point
                                        self.tagPoints[tn].setAlarm("LowBattery", "value < 33 and timestamp", priority='warning')


                                def f(t,v,tn=tn,j=j):
                                    self.tagpoints[tn].defaultClaim.set(v[j['property']],annotation='ZigBee')
                                
                                def f2(v,t,a,tn=tn,j=j):
                                    if not a == 'ZigBee':
                                        self.connection.publish(zn+"/set",{j['property']:v})
                                
                                try:
                                    self.connection.unsubscribe(zn, self.tagpoints[tn].incomingHandler)
                                except:
                                    pass
                                self.connection.subscribe(zn, f)
                                self.tagpoints[tn].incomingHandler = f


                                try:
                                    self.tagpoints[tn].unsubscribe( self.tagpoints[tn].zigbeeHandler)
                                except:
                                    pass
                                self.tagpoints[tn].subscribe(f2)
                                self.tagpoints[tn].zigbeeHandler = f2
                                self.tagpoints[tn].deviceFriendlyName = i['friendly_name']


                                self.exposeConverters[tn]=f



                            elif j['type'] == 'binary':
                                self.tagPoints[tn] = tagpoints.Tag("/devices/"+self.name+"/node/"+i['friendly_name']+"/"+j['property'])


                                if j['name']=='tamper':
                                        self.tagPoints[tn].setAlarm("Tamper", "value", priority='error')

                                if j['name']=='battery_low':
                                        self.tagPoints[tn].setAlarm("BatteryLow", "value", priority='warning')

                                if j['name']=='gas':
                                        self.tagPoints[tn].setAlarm("GAS", "value", priority='critical')

                                if j['name']=='smoke':
                                        self.tagPoints[tn].setAlarm("SMOKE", "value", priority='critical')

                                if j['name']=='water_leak':
                                        self.tagPoints[tn].setAlarm("WATERLEAK", "value", priority='critical')


                                if j['name']=='carbon_monoxide':
                                        self.tagPoints[tn].setAlarm("CARBONMONOXIDE", "value", priority='critical')

                                def f(t,v,tn=tn,j=j):
                                    #Convert back to proper true/false
                                    v = v[j['property']]==j['value_on']
                                    self.tagpoints[tn].defaultClaim.set(v,annotation='ZigBee')
                                
                                def f2(v,t,a,tn=tn,j=j):
                                    if not a == 'ZigBee':
                                        #Convert back to zigbee2mqtt's idea of true/false
                                        self.connection.publish(zn+"/set", {j['property']:(j['value_on'] if v else j['value_off'])})
                                
                                try:
                                    self.connection.unsubscribe(zn, self.tagpoints[tn].incomingHandler)
                                except:
                                    pass
                                self.connection.subscribe(zn, f)
                                self.tagpoints[tn].incomingHandler = f


                                try:
                                    self.tagpoints[tn].unsubscribe( self.tagpoints[tn].zigbeeHandler)
                                except:
                                    pass
                                self.tagpoints[tn].subscribe(f2)
                                self.tagpoints[tn].zigbeeHandler = f2
                                self.tagpoints[tn].deviceFriendlyName = i['friendly_name']


                                self.exposeConverters[tn]=f

                            #Todo: Tag points need to support enums
                            elif j['type'] in ['enum','text']:
                                self.tagPoints[tn] = tagpoints.StringTag("/devices/"+self.name+"/node/"+i['friendly_name']+"/"+j['property'])
                                def f(t,v,tn=tn,j=j):
                                    self.tagpoints[tn].defaultClaim.set(v[j['property']],annotation='ZigBee')
                                
                                def f2(v,t,a,tn=tn,j=j):
                                    if not a == 'ZigBee':
                                        #Convert back to zigbee2mqtt's idea of true/false
                                        self.connection.publish(zn+"/set", {j['property']:v})

                                try:
                                    self.connection.unsubscribe(zn, self.tagpoints[tn].incomingHandler)
                                except:
                                    pass
                                self.connection.subscribe(zn, f)
                                self.tagpoints[tn].incomingHandler = f


                                try:
                                    self.tagpoints[tn].unsubscribe( self.tagpoints[tn].zigbeeHandler)
                                except:
                                    pass
                                self.tagpoints[tn].subscribe(f2)
                                self.tagpoints[tn].zigbeeHandler = f2
                                self.tagpoints[tn].deviceFriendlyName = i['friendly_name']


                                self.exposeConverters[tn]=f

            #Clean up anything deleted from the actual listing of records
            torm=[]
            for i in self.tagpoints:
                if not self.tagpoints[i].deviceFriendlyName in d:
                    torm.append(i)
            for i in torm:
                del self.tagpoints[i]


    def apiWidgetHandler(self, u, v):
        # Note that this sends one wake request that lasts 30s only
        try:
            if v[0] == "enablePairing":
                self.pair()
                self.print("New ZigBee devices will be accepted for 120 seconds")
            
            if v[0]=='getState':
                self.apiWidget.send(['devices', self.devicesData])


        except:
            self.handleException()

    def getManagementForm(self):
        return templateGetter.get_template("manageform.html").render(data=self.data, obj=self)


devices.deviceTypes["Zigbee2MQTT"] = Zigbee2MQTT
