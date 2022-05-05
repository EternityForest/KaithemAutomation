from email.policy import default
from re import L
import uuid
from iot_devices import device
import threading
import logging



"""
httpserver code:
Copyright 2021 Brad Montgomery
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and 
associated documentation files (the "Software"), to deal in the Software without restriction, 
including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, 
and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, 
subject to the following conditions:
The above copyright notice and this permission notice shall be included in all copies or substantial 
portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT 
LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. 
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE 
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.    
"""
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler



x = """
<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
<specVersion>
<major>1</major>
<minor>0</minor>
</specVersion>
<device>
<deviceType>urn:roku-com:device:player:1-0</deviceType>
<friendlyName>XXX</friendlyName>
<manufacturer>Roku</manufacturer>
<manufacturerURL>http://www.roku.com/</manufacturerURL>
<modelDescription>Roku Streaming Player Network Media</modelDescription>
<modelName>Roku Streaming Player 3100X</modelName>
<modelNumber>3100X</modelNumber>
<modelURL>http://www.roku.com/</modelURL>
<serialNumber>1234567890</serialNumber>
<UDN>uuid:a74352e2-8caa-4f3d-a64e-7bc343ff8f08</UDN>
<serviceList>
<service>
<serviceType>urn:roku-com:service:ecp:1</serviceType>
<serviceId>urn:roku-com:serviceId:ecp1-0</serviceId>
<controlURL></controlURL>
<eventSubURL></eventSubURL>
<SCPDURL>ecp_SCPD.xml</SCPDURL>
</service>
<service>
<serviceType>urn:dial-multiscreen-org:service:dial:1</serviceType>
<serviceId>urn:dial-multiscreen-org:serviceId:dial1-0</serviceId>
<controlURL></controlURL>
<eventSubURL></eventSubURL>
<SCPDURL>dial_SCPD.xml</SCPDURL>
</service>
</serviceList>
</device>
</root>
"""

def ssdpxml(n):
    return x.replace("XXX",n)








logger = logging.Logger("plugins.pyremote")

import time
import socket

# Attr: https://stackoverflow.com/questions/1365265/on-localhost-how-do-i-pick-a-free-port-number
import socket
from contextlib import closing

def find_free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('0.0.0.0', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def check_port(p):
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(('0.0.0.0', p))
            return True
    except Exception:
        return False



try:
    import network
except:
    pass

# https://github.com/FRC4564/HueBridge/blob/master/hue.py used as reference
# Note: You do not have to use SSDP's schemas. Look at roku, they do their own fields: https://developer.roku.com/docs/developer-program/debugging/external-control-api.md


try:
    ms = time.ticks_ms
    tickdiff = time.ticks_diff
except:
    def ms():
        return int(time.monotonic()*1000)
    def tickdiff(a,b):
        return a-b
    
mxsearch = {
    'method':'M-SEARCH',
    'HOST': '239.255.255.250:1900',
    'MAN': '"ssdp:discover"',
    "MX": "3"
}

reply = {'SERVER': 'Unspecified, UPnP/1.0, Unspecified','EXT': '', 'CACHE-CONTROL': 'max-age=601'}


# Local service definition: 
def getUID():
    try:
        import network
        import ubinascii
        mac = ubinascii.hexlify(network.WLAN().config('mac'),':').decode()
        return (mac.replace(':','').upper())
    except:
        return socket.gethostname()
    
def getLocalIPForRemoteClient(addr):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(addr)
        ip= sock.getsockname()[0]
        sock.close()
    except:
        ip = network.WLAN().ifconfig()[0]
    
    return ip
    

    
class HTTPUServer():
    def __init__(self):
        sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        sock.settimeout(3)
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        addr = ("0.0.0.0",1900)
        sock.bind(addr)
        opt = bytes([239,255,255,250])+bytes([0,0,0,0])
        sock.setsockopt(socket.IPPROTO_IP,socket.IP_ADD_MEMBERSHIP,opt)
        self.sock = sock
        
        self.services = {}
    
    def poll(self):
        try:
            data, addr = self.sock.recvfrom(1024)
        except OSError:
            return
        self._onmsg(addr,parse_httpu(data))
        
    
    def _replyServices(self,st,a):
         for i in self.services:
             if st== 'ssdp:all' or st==i:
                s = {}
                s.update(self.services[i])
                s.update(reply)
                s['ST'] = s.get('ST',i)
                
                s['LOCATION'] = s['LOCATION'].replace('localhost',getLocalIPForRemoteClient(a))
                if not 'USN' in s:
                    s['USN'] = 'uuid:'+getUID() + "::" +s['ST']
                s=make_httpu(s)
                self.sock.sendto(s,a)
                
    def _onmsg(self,a,m):
        if a[0].startswith('192.') or a[0].startswith('10.') or a[0].startswith('127.'):
            if m.get('method','')== 'M-SEARCH':
                if m.get('Man',m.get('MAN',''))=='"ssdp:discover"':
                    st = m.get('ST','')
                    self._replyServices(st, a)
                                 

def make_httpu(d):
    o =  ''
    if 'method' in d:
        o += d['method'] + " * HTTP/1.1\r\n"
    else:
        o += "HTTP/1.1 200 OK\r\n"
        
    for i in d:
        if not i=='method':
            o+= i+': '+d[i] + "\r\n"
    return o.encode()

def parse_httpu(data):
    data=data.decode()
    
    d = {}
    # Compensate for any bad implementations that don't use \r\n
    lines = data.replace('\r','').split('\n')
    
    l0 = lines.pop(0)
    
    if '*' in l0:
        d['method'] = l0.split('*')[0].strip()

        
    for l in lines:
        tokens = l.split(':',1)
        if len(tokens)>1:
            d[tokens[0]]= tokens[1].strip()
    return d
  


import logging
import asyncio


class PyremoteServer(device.Device):
    device_type = 'PyremoteServer'

    def ssdploop(self):
        while (1):
            s = self.ssdp
            if s:
                s.poll()
            else:
                return

    def handlemsg(self,a,b):
        print(a,b)




    @asyncio.coroutine
    def client_coro(self):
        from hbmqtt.client import MQTTClient,QOS_0
        C = MQTTClient()
        self.client = C
        yield from C.connect("mqtt://"+self.bind.replace('0.0.0.0','localhost'))
        # Subscribe to '$SYS/broker/uptime' with QOS=1
        # Subscribe to '$SYS/broker/load/#' with QOS=2
        yield from C.subscribe([
                ('/pyremote/#', QOS_0),
            ])
        try:
            while self.bind:

                try:
                    message = yield from C.deliver_message()
                    packet = message.publish_packet
                    self.handlemsg( packet.variable_header.topic_name, str(packet.payload.data))
                except:
                    self.handle_exception()

            yield from C.unsubscribe(['/pyremote/#'])
            yield from C.disconnect()
        except Exception as ce:
            self.handle_exception()



    @asyncio.coroutine
    def broker_coro(self):
        from hbmqtt.broker import Broker
        conf = {'listeners': {
                'default': {
                    'bind': self.bind,
                    'type': 'tcp'
                }},
                'auth': {
                    'plugins': ['auth.anonymous'],
                    'allow-anonymous': True
                
                }
                }

        try:

            self.broker = Broker(conf)
            yield from self.broker.start()
        except Exception:
            try:
                self.broker.shutdown()
            except:
                pass
            self.handle_exception()

    def close(self):

        self.ssdp = None
        self.bind = None

        try:
            self.client.shutdown()
            del self.client
        except:
            self.handleException()
        

        try:
            self.broker.shutdown()
            del self.broker
        except:
            self.handleException()
        

        try:
            self.loop.stop()
        except:
            self.handleException()

        try:
            self.loop.close()
        except:
            self.handleException()


        try:
            self.cloop.stop()
        except:
            self.handleException()

        try:
            self.cloop.close()
        except:
            self.handleException()
        

        device.Device.close(self)


    def __init__(self, name, data):
        device.Device.__init__(self, name, data)
        self.closed = False

        try:
            self.loop = asyncio.new_event_loop()
            self.set_config_default("device.uuid",str(uuid.uuid4()))
            


            self.set_config_default("device.bind","0.0.0.0:"+str(find_free_port()))

            if not data['device.bind'].strip():
                raise RuntimeError("No address selected")

            p = self.config['device.bind'].split(":")[1]
            p = int(p)

            self.bind = self.config['device.bind']
            if not check_port(p):
                self.bind = "0.0.0.0:"+str(find_free_port())

            self.ssdp = HTTPUServer()
            self.ssdp.services = {'pyremote:app':{'TITLE':self.name[:16], 'LOCATION': "mqtt://"+self.bind.replace('0.0.0.0','localhost'), 
            'USN': 'uuid:'+self.config['device.uuid']+"::pyremote:app"}}


            def f():
                try:
                    self.loop.run_until_complete(self.broker_coro())
                    self.loop.run_forever()
                except Exception:
                    self.handle_exception()


            self.thread = threading.Thread(target=f,name="MQTTBroker"+self.name, daemon=True)
            self.thread.start()


            self.thread2 = threading.Thread(target=self.ssdploop,name='pyremotessdp'+self.name, daemon=True)
            self.thread2.start()

            self.cloop = asyncio.new_event_loop()

            def f():
                try:
                    self.cloop.run_until_complete(self.client_coro())
                except Exception:
                    self.handle_exception()


            self.thread3 = threading.Thread(target=f,name="MQTTClient"+self.name, daemon=True)
            self.thread3.start()



        except Exception:
            self.handleException()


import os
import os.path

def tzget():
    tzname = os.environ.get('TZ')
    if tzname:
        return tzname
    elif os.path.exists('/etc/timezone'):
        with open('/etc/timezone') as f:
            return f.read().strip()
    return "US/Pacific"



def fakeroku(name):
    return """<device-info>
        <udn>015e5108-9000-1046-8035-b0a737964dfb</udn>
        <serial-number>1GU48T017973</serial-number>
        <device-id>1GU48T017973</device-id>
        <vendor-name>KaithemProject</vendor-name>
        <model-number>FRoku</model-number>
        <model-name>Fake Roku</model-name>
        <model-region>US</model-region>
        <ui-resolution>1080p</ui-resolution>
        <supports-ethernet>true</supports-ethernet>
        <wifi-mac>b0:a7:37:96:4d:fb</wifi-mac>
        <ethernet-mac>b0:a7:37:96:4d:fa</ethernet-mac>
        <network-type>ethernet</network-type>
        <user-device-name>"""+name+"""</user-device-name>
        <software-version>0.1.0</software-version>
        <software-build>00000</software-build>
        <secure-device>true</secure-device>
        <language>en</language>
        <country>US</country>
        <locale>en_US</locale>
        <time-zone>"""+tzget()+"""</time-zone>
        <time-zone-offset>""" + str(time.localtime().tm_gmtoff/60)+"""</time-zone-offset>
        <power-mode>PowerOn</power-mode>
        <supports-suspend>false</supports-suspend>
        <supports-find-remote>false</supports-find-remote>
        <supports-audio-guide>false</supports-audio-guide>
        <developer-enabled>false</developer-enabled>
        <keyed-developer-id>acc702ce-af3b-4400-b9b7-9bfcf9b9918d</keyed-developer-id>
        <search-enabled>false</search-enabled>
        <voice-search-enabled>false</voice-search-enabled>
        <notifications-enabled>false</notifications-enabled>
        <notifications-first-use>false</notifications-first-use>
        <supports-private-listening>false</supports-private-listening>
        <headphones-connected>false</headphones-connected>
    </device-info>"""



import logging
import asyncio


class RokuRemoteApp(device.Device):
    device_type = 'RokuRemoteApp'
    description="""
    Implements an extended version of the Roku ECP protocol.  Does not currently work with most real Roku apps,
    intended mostly for use with DIY handheld remotes.

    The battery tag represents the most recently connected remote. It should not be given all that much weight.
    """
    def ssdploop(self):
        while (1):
            s = self.ssdp
            if s:
                s.poll()
            else:
                return

   
    def close(self):
        self.ssdp = None
        self.bind = None
        device.Device.close(self)


    def __init__(self, name, data):
        device.Device.__init__(self, name, data)
        self.closed = False

        self.object_data_point("keypress", subtype='event')
        self.set_data_point('keypress',[None, time.monotonic(),None])

        self.object_data_point("launch", subtype='event')
        self.set_data_point('launch',[None, time.monotonic(),None])

        self.numeric_data_point("battery",min=0,max=100, unit="%")
        self.set_alarm('LowBattery', datapoint='battery', expression='value < 20', priority='warning', release_condition='value > 35')

        try:
            self.set_config_default("device.uuid",str(uuid.uuid4()))
            self.set_config_default("device.bind","0.0.0.0:"+str(find_free_port()))

            if not self.config['device.bind'].strip():
                raise RuntimeError("No address selected")

            p = self.config['device.bind'].split(":")[1]
            p = int(p)

            self.bind = self.config['device.bind']
            if not check_port(p):
                self.bind = "0.0.0.0:"+str(find_free_port())

            self.ssdp = HTTPUServer()
            self.ssdp.services = {'roku:ecp':{'LOCATION': "http://"+self.bind.replace('0.0.0.0','localhost'), 
            'USN': 'uuid:roku:ecp:'+self.config['device.uuid'].replace('-','').upper()}}

            class S(BaseHTTPRequestHandler):
                def _set_headers(s):
                    s.send_response(200)
                    s.send_header("Content-type", "text/xml")
                    s.end_headers()

              

                def do_GET(s):
                    s._set_headers()

                    if s.path =='/query/device-info':
                        s.wfile.write(fakeroku(self.name).encode())
                    
                    elif s.path=="/":
                        s.wfile.write(ssdpxml(self.name).encode())

                    elif s.path=='/unixtime':
                        s.wfile.write(str(time.time()).encode())

                def do_HEAD(s):
                    s._set_headers()

                def do_POST(s):
                    if s.path.startswith("/keypress/"):
                        self.set_data_point('keypress',[s.path[len('/keypress/'):], time.monotonic(),None])
                    if s.path.startswith("/launch/"):
                        self.set_data_point('launch',[s.path[len('/launch/'):], time.monotonic(),None])

                    s._set_headers()


            def f():
                try:
                    ip,port = self.bind.split(':')
                    httpd = HTTPServer((ip,int(port)), S)
                    httpd.serve_forever()
                except Exception:
                    self.handle_exception()


            self.thread = threading.Thread(target=f,name="HTTPRemoteServer"+self.name, daemon=True)
            self.thread.start()


            self.thread2 = threading.Thread(target=self.ssdploop,name='pyremotessdp'+self.name, daemon=True)
            self.thread2.start()

           


        except Exception:
            self.handleException()



