#Copyright Daniel Dunn 2019
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

import weakref, threading,time,logging
from . import alerts, tagpoints

## User visible APIs
portInterfaces = {}

lock = threading.RLock()

def manage():
    with lock:
        portInterfaces = {i:portInterfaces[i] for i in portInterfaces if portInterfaces[i]()}

        for i in portInterfaces:
            x = portInterfaces[i]()
            if x:
                with x.lock:
                    if not x.isConnected():
                        x.alert.trip()
                        x.tag.defaultClaim.set('disconnected')
                        try:
                            import serial
                            p = serial.Serial(x.portName, **x.portSettings)
                            x._port= p
                            x.tag.defaultClaim.set('connected')
                            x.alert.clear()
                        except Exception as e:
                            x.alert.trip(e)
                            x.tag.defaultClaim.set('disconnected')
                    else:
                        x.tag.defaultClaim.set('connected')
                        x.alert.clear()

            del x
            
loopThread = None
def loop():
    while 1:
        try:
            manage()
            #Stop when not needed, we can always dynamically start again when we are
            if not portInterfaces:
                return()
        except:
            logging.exception("Error in serial port manager loop")
        time.sleep(5)


def setupThread():
    global loopThread
    with lock:
        if not loopThread:
            loopThread=threading.Thread(target=loop,daemon=True)

class PortInterface():
    def __init__(self,port,alertPriority="warning", alertZone="",*,**kwargs):
        with lock:
            if port in portInterfaces and portInterfaces[self]():
                raise ValueError("Port is already open")
            
            self.portSettings = kwargs.update({'baudrate':9600, 'timeout': 0.1, 'write_timeout': 10, 'inter_byte_timeout': 0.03})
            self.alert = alerts.Alert("/serial/ports/"+port+"/disconnected",priority=alertPriority, zone=alertZone)
            self.tag = tagpoints.StringTag("/serial/ports/"+port+"/status")
            self.tag.value = "disconnected"
            self.portName = port
            self.lock = threading.Lock()
          
            portInterfaces[port] = weakref.ref(self)
            import serial
            try:
                self.port = serial.Serial(port, **portSettings)
            finally:
                self.port = None
            
            setupThread()

    def __enter__(self):
        self.lock.acquire()
    def __enter__(self):
        self.lock.release()

    
    def isConnected(self):
        try:
            self.port.in_waiting
            return True
        except:
            return False

    def available(self):
        "Return number of bytes available. Never raised errors, returns 0 on disconnected ports"
        try:
            return self.port.in_waiting
        except Exception as e:
            self.alert.trip(e)
            self.tag.defaultClaim.set('disconnected')
            return 0
    
    def read(self):
        "Read all available data from the port. If it is disconnected, just return an empty bytestring"
        try:
            x= self.port.read(self.port.in_waiting)
            return x            
        except Exception as e:
            self.alert.trip(e)
            self.tag.defaultClaim.set('disconnected')
            return b''
    
    def write(self, s):
        "Write the string to the port. All errors are ignored"
        try:
            self.port.write(s)
        except Exception as e:
            #Errors here could just be buffer overruns
            return b''

    def sendBreak(self,time=0.002):
        try:
            self.port.send_break(time)
        except:
            pass