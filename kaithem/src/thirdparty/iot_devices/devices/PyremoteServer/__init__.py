import uuid
from iot_devices import device
import threading
import logging


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
import os


class PyremoteServer(device.Device):
    device_type = 'PyremoteServer'

    def ssdploop(self):
        while (1):
            s = self.ssdp
            if s:
                s.poll()
            else:
                return

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
        

        device.Device.close(self)


    def __init__(self, name, data):
        device.Device.__init__(self, name, data)
        self.closed = False

        try:
            self.loop = asyncio.new_event_loop()
            self.set_config_default("device.uuid",str(uuid.uuid4()))
            
            self.ssdp = HTTPUServer()
            self.ssdp.services = {'pyremote:app':{'TITLE':self.name[:16], 'LOCATION': self.config['device.bind'].replace('0.0.0.0','localhost'), 
            'USN': 'uuid:'+self.config['device.uuid']+"::pyremote:app"}}

            self.set_config_default("device.bind","0.0.0.0:"+str(find_free_port()))

            if not data['device.bind'].strip():
                raise RuntimeError("No address selected")

            p = self.config['device.bind'].split(":")[1]
            p = int(p)

            self.bind = self.config['device.bind']
            if not check_port(p):
                self.bind = "0.0.0.0:"+str(find_free_port())


            def f():
                try:
                    self.loop.run_until_complete(self.broker_coro())
                    self.loop.run_forever()
                except Exception:
                    self.handle_exception()


            self.thread = threading.Thread(target=f,name="MQTTBroker"+self.name)
            self.thread.start()


            self.thread2 = threading.Thread(target=self.ssdploop)
            self.thread2.start()

        except Exception:
            self.handleException()