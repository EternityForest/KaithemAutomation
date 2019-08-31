
# Copyright (c) 2019 Daniel Dunn

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import atexit,threading,socket,time
from urllib.parse import urlparse
import logging

logger=logging.getLogger("upnp")
try:
    from . import upnp as upnpclient
except ImportError:
    upnp=None
    logger.exception("Error loading UPnP")

listlock = threading.Lock()

cleanuplist = []
renewlist=[]

cachelock = threading.Lock()

cachedDevices = None


def cleanup():
    with listlock:
        for i in cleanuplist:
            try:
                i()
            except Exception as e:
                print(e)
atexit.register(cleanup)


#Ask routers for our external IPs
def getWANAddresses():
    devices = getDevicesWithDefault(None)
    addresses = []
    
    for i in devices:
        for j in i.services:
            for k in j.actions:
                if k.name=="GetExternalIPAddress":
                    if "WAN" in j.service_type:
                        addresses.append(j.GetExternalIPAddress()["NewExternalIPAddress"])
    return addresses
                        


class Mapping():
    "Represents one port mapping"
    
    def __init__(self, clfun, renfun):
        self.clfun = clfun
        self.renfun = renfun
    
    def __del__(self):
        self.delete()
    
    def delete(self):
        self.clfun()
        
        with listlock:
            if self.clfun in cleanuplist:
                cleanuplist.remove(self.clfun)
            if self.renfun in cleanuplist:
                renewlist.remove(self.clfun)
        


def getDevicesWithDefault(deviceURL):
    global cachedDevices
    startIfNeeded()
    if deviceURL:
        devices = [upnpclient.Device(deviceURL)]
    else:
        if not cachedDevices:
            #Very quick scan because we let the background thread handle the slow stuff.
            cachedDevices = upnpclient.discover(timeout=1)
        devices = cachedDevices
    return devices
      
#Asks them to open port from the outside world directly to us.
def addMapping(port,proto, desc="Description here", deviceURL=0, register=True, WANPort= None):
    """
        Add a mapping between the outside world and a certain port on the local machine.
        Proto can be UDP or TCP. The mapping will expire in 20 minutes unless autorenew is used.
        deviceURL can be the URL of a router, otherwise defaults to all routers.

        Returns a mapping object, you must keep a ref to it, or else the mapping dissapears
        with the object.
    """
    devices = getDevicesWithDefault(deviceURL)
    #Local cleanup list for just this mapping
    cleanups  = []

    for i in devices:
        l=urlparse(i.location).netloc
        if ":" in l:
            l = l.split(":")[0]

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.connect((l, 12345))
        
        #Get the IP that we use to talk to that particular router
        ownAddr = s.getsockname()[0]
        s.close()
        del s

        for j in i.services:
            for k in j.actions:
                if k.name=="GetExternalIPAddress":
                    if "WAN" in j.service_type:
                        if register:
                            #Function to clean it from one router
                            def clean():
                                j.DeletePortMapping(
                                    NewRemoteHost="0.0.0.0",
                                    NewExternalPort=WANPort or port,
                                    NewProtocol=proto,
                                )
                                
                            with listlock:
                                cleanups.append(clean)
                            
                        j.AddPortMapping(
                            NewRemoteHost='0.0.0.0',
                            NewExternalPort=WANPort or port,
                            NewProtocol=proto,
                            NewInternalPort=port,
                            NewInternalClient=ownAddr,
                            NewEnabled='1',
                            NewPortMappingDescription=desc,
                            NewLeaseDuration=30*60
                        )
        
        if register:
            def renew():
                #No recursive adding things to renew
                addMapping(port,proto, desc, register=False)
            
            def cleanAll():
                for i in cleanups:
                    i()

            with listlock:
                renewlist.append(renew)
                cleanuplist.append(cleanAll)
                m = Mapping(cleanAll,renew)

    return m


cachedMappings =None
cachedMappingsTime = 0

def listMappings(deviceURL= None, cacheTime=1):
    """Scan the entire network for port mappings. Return as list of dicts.

    They will have the keys internal and external, both ip,port pairs.
    They will also have protocol, a string that may be UDP or TCP,
    description, and duration.

    deviceURL can be the URL of a router, otherwise defaults to all routers.
    """

    global cachedMappings
    global cachedMappingsTime
    if cachedMappings and cachedMappingsTime>(time.monotonic()-cacheTime):
        return cachedMappings

    devices = getDevicesWithDefault(deviceURL)
 
    mappings = []


    for i in devices:
        l=urlparse(i.location).netloc
        if ":" in l:
            l = l.split(":")[0]

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.connect((l, 12345))
        
        #Get the IP that we use to talk to that particular router
        ownAddr = s.getsockname()[0]
        s.close()
        del s

        wanIP=None
        for j in i.services:
                for k in j.actions:
                    if k.name=="GetExternalIPAddress":
                        if "WAN" in j.service_type:
                            wanIP= (j.GetExternalIPAddress()["NewExternalIPAddress"])
        if not wanIP:
            continue
                
        for j in i.services:
            for k in j.actions:

                if k.name=="GetGenericPortMappingEntry":
                    if "WAN" in j.service_type:
                        try:
                            ind = 0
                            start= time.time()
                            while(time.time()-start< 100):
                                try:
                                    x = j.GetGenericPortMappingEntry(NewPortMappingIndex=ind)
                                    mappings.append((
                                        {
                                        "external":(wanIP, x['NewExternalPort']),
                                        "internal":(x['NewInternalClient'], x['NewInternalPort']),
                                        
                                        "protocol":x['NewProtocol'],
                                        'description':x['NewPortMappingDescription'],
                                        'duration':x['NewLeaseDuration'],
                                        'remotehost':x['NewRemoteHost']
                                        }
                                    ))
                                    ind+=1
                                except upnpclient.soap.SOAPError:
                                    break    
                        except:
                            logger.exception("Err")
    cachedMappings =mappings
    cachedMappingsTime =time.monotonic()
    return mappings


def detectShortcut(addr,protocol="UDP"):
    """Given a WAN address, check if it maps to a LAN address we can talk to instead.
       This function also resolves DNS names
    """
    #No shortcut needed for these ar all
    if addr[0].startswith("192.") or addr[0].startswith("10.") or  addr[0].startswith("127.") or addr[0].endswith(".local"):
        return

    addr= (socket.gethostbyname_ex(addr[0])[2][0], addr[1])
    try:
        for i in listMappings():
            if i['external']==addr and i['protocol']==protocol:
                return i['internal']
    #Network is unreachable, must not be any
    #Mappings!
    except OSError as e:
        if e.errno == 101:
            return []

def renewer():
    global cachedDevices
    while 1:
        #This takes such a long time that I can't think of a better way,
        #Aside from a background rescan
        try:
            cachedDevices = upnpclient.discover()
            listMappings()
        except:
            logger.exception("err")
        time.sleep(8*60)
        try:
            with listlock:
                for i in renewlist:
                    i()
        except Exception as e:
            print(e)

rth = None

def startIfNeeded():
    global rth
    if rth:
        return
    rth = threading.Thread(target=renewer)
    rth.daemon=True
    rth.start()

