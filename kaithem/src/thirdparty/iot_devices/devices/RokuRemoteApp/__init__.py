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


x = """<?xml version="1.0" encoding="UTF-8" ?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
<specVersion>
    <major>1</major>
    <minor>0</minor>
</specVersion>
<device>
    <deviceType>urn:roku-com:device:player:1-0</deviceType>
    <friendlyName>FN</friendlyName>
    <manufacturer>naimo84</manufacturer>
    <manufacturerURL>https://github.com/naimo84/</manufacturerURL>
    <modelDescription>Node Red - fake Roku player</modelDescription>
    <modelName>fakeroku</modelName>
    <modelNumber>4200X</modelNumber>
    <modelURL>https://github.com/naimo84/node-red-contrib-fakeroku</modelURL>
    <serialNumber>XXXX</serialNumber>
    <UDN>uuid:roku:ecp:XXXX</UDN>
    <iconList>
        <icon>
            <mimetype>image/png</mimetype>
            <width>360</width>
            <height>219</height>
            <depth>8</depth>
            <url>device-image.png</url>
        </icon>
    </iconList>
    <serviceList>
    <service>
        <serviceType>urn:roku-com:service:ecp:1</serviceType>
        <serviceId>urn:roku-com:serviceId:ecp1-0</serviceId>
        <controlURL/>
        <eventSubURL/>
        <SCPDURL>ecp_SCPD.xml</SCPDURL>
    </service>
    </serviceList>
</device>
</root>"""


def ssdpxml(name,uuid):
    return x.replace("FN", name).replace('XXXX',uuid.replace('-','').upper())


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
        return int(time.monotonic() * 1000)

    def tickdiff(a, b):
        return a - b

mxsearch = {
    'method': 'M-SEARCH',
    'HOST': '239.255.255.250:1900',
    'MAN': '"ssdp:discover"',
    "MX": "3"
}

reply = {'SERVER': 'Unspecified, UPnP/1.0, Unspecified',
         'EXT': '', 'CACHE-CONTROL': 'max-age=601'}


# Local service definition:
def getUID():
    try:
        import network
        import ubinascii
        mac = ubinascii.hexlify(network.WLAN().config('mac'), ':').decode()
        return (mac.replace(':', '').upper())
    except:
        return socket.gethostname()


def getLocalIPForRemoteClient(addr):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(addr)
        ip = sock.getsockname()[0]
        sock.close()
    except:
        ip = network.WLAN().ifconfig()[0]

    return ip


class HTTPUServer():
    def __init__(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        addr = ("", 1900)
        sock.bind(addr)
        opt = bytes([239, 255, 255, 250]) + bytes([0, 0, 0, 0])
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, opt)
        self.sock = sock

        self.services = {}

    def poll(self):
        try:
            data, addr = self.sock.recvfrom(1024)
        except OSError:
            return
        self._onmsg(addr, parse_httpu(data))

    def _replyServices(self, st, a):
        for i in self.services:
            if st == 'ssdp:all' or st == i:
                s = {}
                s.update(self.services[i])
                s.update(reply)
                s['ST'] = s.get('ST', i)

                s['Location'] = s['Location'].replace(
                    'localhost', getLocalIPForRemoteClient(a))
                
                s['LOCATION'] = s['LOCATION'].replace(
                    'localhost', getLocalIPForRemoteClient(a))
                if not 'USN' in s:
                    s['USN'] = 'uuid:' + getUID() + "::" + s['ST']
                s = make_httpu(s)
                self.sock.sendto(s, a)

    def _onmsg(self, a, m):
        if a[0].startswith('192.') or a[0].startswith('10.') or a[0].startswith('127.'):
            if m.get('method', '') == 'M-SEARCH':
                if m.get('Man', m.get('MAN', '')) == '"ssdp:discover"':
                    st = m.get('ST', '')
                    self._replyServices(st, a)


def make_httpu(d):
    o = ''
    if 'method' in d:
        o += d['method'] + " * HTTP/1.1\r\n"
    else:
        o += "HTTP/1.1 200 OK\r\n"

    for i in d:
        if not i == 'method':
            o += i + ': ' + d[i] + "\r\n"
    o += '\r\n'

    return o.encode()


def parse_httpu(data):
    data = data.decode()

    d = {}
    # Compensate for any bad implementations that don't use \r\n
    lines = data.replace('\r', '').split('\n')

    l0 = lines.pop(0)

    if '*' in l0:
        d['method'] = l0.split('*')[0].strip()

    for l in lines:
        tokens = l.split(':', 1)
        if len(tokens) > 1:
            d[tokens[0]] = tokens[1].strip()
    return d


import logging
import asyncio


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
    <serial-number>X004000B231</serial-number>
    <device-id>S00820BB231</device-id>
    <vendor-name>Roku</vendor-name>
    <model-name>Roku Ninja</model-name>
    <model-number>3930X</model-number>
    <model-region>US</model-region>
    <is-tv>false</is-tv>
    <is-stick>false</is-stick>
    <ui-resolution>1080p</ui-resolution>
    <supports-ethernet>false</supports-ethernet>
    <wifi-mac>10:59:32</wifi-mac>
    <wifi-driver>realtek</wifi-driver>
    <has-wifi-extender>false</has-wifi-extender>
    <has-wifi-5G-support>true</has-wifi-5G-support>
    <can-use-wifi-extender>true</can-use-wifi-extender>
    <network-type>wifi</network-type>
    <network-name>Hillary's Email Server</network-name>
    <friendly-device-name>Roku LivingRoom</friendly-device-name>
    <friendly-model-name>Roku Express</friendly-model-name>
    <default-device-name>Roku Express - X004000AJDX1</default-device-name>
    <user-device-name>""" + name + """</user-device-name>
    <user-device-location>LivingRoom</user-device-location>
    <build-number>AEA.00E04209A</build-number>
    <software-version>10.0.0</software-version>
    <software-build>4209</software-build>
    <secure-device>true</secure-device>
    <language>en</language>
    <country>US</country>
    <locale>en_US</locale>
    <time-zone-auto>true</time-zone-auto>
    <time-zone>""" + tzget() + """</time-zone>
    <time-zone-name>""" + tzget() + """</time-zone>
    <time-zone-tz>""" + tzget() + """</time-zone>
    <time-zone-offset>""" + str(time.localtime().tm_gmtoff / 60) + """</time-zone-offset>
    <clock-format>12-hour</clock-format>
    <uptime>2912968</uptime>
    <power-mode>PowerOn</power-mode>
    <supports-suspend>false</supports-suspend>
    <supports-find-remote>true</supports-find-remote>
    <find-remote-is-possible>false</find-remote-is-possible>
    <supports-audio-guide>true</supports-audio-guide>
    <supports-rva>true</supports-rva>
    <developer-enabled>false</developer-enabled>
    <keyed-developer-id/>
    <search-enabled>true</search-enabled>
    <search-channels-enabled>true</search-channels-enabled>
    <voice-search-enabled>true</voice-search-enabled>
    <notifications-enabled>true</notifications-enabled>
    <notifications-first-use>true</notifications-first-use>
    <supports-private-listening>true</supports-private-listening>
    <headphones-connected>false</headphones-connected>
    <supports-ecs-textedit>true</supports-ecs-textedit>
    <supports-ecs-microphone>true</supports-ecs-microphone>
    <supports-wake-on-wlan>false</supports-wake-on-wlan>
    <supports-airplay>true</supports-airplay>
    <has-play-on-roku>true</has-play-on-roku>
    <has-mobile-screensaver>false</has-mobile-screensaver>
    <support-url>roku.com/support</support-url>
    <grandcentral-version>5.5.62</grandcentral-version>
    <trc-version>3.0</trc-version>
    <trc-channel-version>4.2.3</trc-channel-version>
    <davinci-version>2.8.20</davinci-version>
    </device-info>"""


import logging
import asyncio


class RokuRemoteApp(device.Device):
    device_type = 'RokuRemoteApp'
    readme = """
Implements an extended version of the (https://developer.roku.com/docs/developer-program/debugging/external-control-api.md)[Roku ECP protocol].  Does not currently work with most real Roku apps,
intended mostly for use with DIY handheld remotes.

We condense everything down to a single "Command" tag.  "Launch" commands are mapped to a string like "launch:78797".
Keydown commands are mapped to a string containing the exact key name.

The battery tag represents the most recently connected remote that decided to send something. It should not be given all that much weight.
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
        if self.httpd:
            self.httpd.shutdown()
            self.httpd = None
        device.Device.close(self)

    def __init__(self, name, data):
        device.Device.__init__(self, name, data)
        self.closed = False
        self.httpd = None

        self.object_data_point("command", subtype='event')
        self.set_data_point('command', [None, time.monotonic(), None])

        self.numeric_data_point("battery", min=0, max=100, unit="%")
        self.set_alarm('LowBattery', datapoint='battery', expression='value < 20',
                       priority='warning', release_condition='value > 35')

        try:
            self.set_config_default("device.serial", "P0A070000007")
            self.set_config_default("device.uuid",str(uuid.uuid4()))
            self.set_config_default(
                "device.bind", "0.0.0.0:" + str(find_free_port()))

            if not self.config['device.bind'].strip():
                raise RuntimeError("No address selected")

            p = self.config['device.bind'].split(":")[1]
            p = int(p)

            self.bind = self.config['device.bind']
            if not check_port(p):
                self.bind = "0.0.0.0:" + str(find_free_port())

            self.ssdp = HTTPUServer()
            self.ssdp.services = {'roku:ecp': {'Location': "http://" + self.bind.replace('0.0.0.0', 'localhost'),
                                                'LOCATION': "http://" + self.bind.replace('0.0.0.0', 'localhost'),
                                               'USN': 'uuid:roku:ecp:'+self.config['device.uuid'].replace('-','').upper(),
                                               'Cache-Control': 'max-age=3600'
                                               }}

            class S(BaseHTTPRequestHandler):
                def _set_headers(s):
                    s.send_response(200)
                    s.send_header("Content-type", "text/xml")
                    s.end_headers()

                def do_GET(s):
                    if not s.path.endswith('.png'):                               
                        s.send_response(200)
                        s.send_header('Content-Type', 'text/xml; charset=utf-8')
                        s.end_headers()
                    else:                        
                        s.send_response(200)
                        s.send_header("Content-type", "image/png")
                        s.end_headers()
        
                    if s.path=='/query/apps':
                        x="""<apps>
                        <app id="11">Roku Channel Store</app>
                        <app id="12">Netflix</app>
                        <app id="13">Amazon Video on Demand</app>
                        <app id="837">YouTube</app>
                        <app id="2016">Crackle</app>
                        <app id="3423">Rdio</app>
                        <app id="21952">Blockbuster</app>
                        <app id="31012">MGO</app>  
                        <app id="43594">CinemaNow</app>
                        <app id="46041">Sling TV</app>
                        <app id="50025">GooglePlay</app>
                        </apps>""".encode()
                        x.wfile.write(x.encode())

                    if s.path == '/query/device-info':
                        s.wfile.write(fakeroku(self.name).encode())

                    elif s.path == "/":
                        s.wfile.write(ssdpxml(self.name, self.config['device.uuid']).encode())

                    elif s.path == '/unixtime':
                        s.wfile.write(str(time.time()).encode())

                    elif s.path == '/device-image.png':
                        with open(os.path.join(os.path.dirname(__file__), "placeholder.png"),'rb') as f:
                            s.wfile.write(f.read())

                def do_HEAD(s):
                    s._set_headers()

                def do_POST(s):
                    s._set_headers()
                    s.wfile.write(b'{}')

                    if s.path.startswith("/keypress/"):
                        self.set_data_point(
                            'command', [s.path[len('/keypress/'):], time.monotonic(), None])
                    if s.path.startswith("/launch/"):
                        self.set_data_point(
                            'command', ["launch:" + s.path[len('/launch/'):], time.monotonic(), None])

            def f():
                try:
                    ip, port = self.bind.split(':')
                    self.httpd = HTTPServer((ip, int(port)), S)
                    self.httpd.serve_forever()
                except Exception:
                    self.handle_exception()

            self.thread = threading.Thread(
                target=f, name="HTTPRemoteServer" + self.name, daemon=True)
            self.thread.start()

            self.thread2 = threading.Thread(
                target=self.ssdploop, name='pyremotessdp' + self.name, daemon=True)
            self.thread2.start()

        except Exception:
            self.handleException()
