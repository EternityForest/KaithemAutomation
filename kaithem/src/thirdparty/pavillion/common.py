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


import hashlib,logging,struct,threading,atexit,base64,queue,time,subprocess,re,os,socket

def addMulticastGroup(s,address):
    group = socket.inet_aton(address)
    mreq = struct.pack('4sL', group, socket.INADDR_ANY)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    
DEFAULT_PORT=1783
DEFAULT_MCAST_ADDR="239.255.28.12"

MAX_RETRIES=8

lock = threading.RLock()

allow_new = True

cleanup_refs = []

import traceback

def get_interfaces():
    interfaces = os.listdir('/sys/class/net')
    return interfaces

def detect_virtual_interfaces(interfaces):
    for each in interfaces:
        real_path = os.path.realpath(os.path.join('/sys/class/net/', each))
        if '/devices/virtual/net/' in real_path:
            interfaces.remove(each)
    return interfaces

def detect_ethernet(clean_interfaces):
    ethernet_interfaces = []
    for each in clean_interfaces:
        try:
            with open('/sys/class/net/{0}/speed'.format(each), 'r') as speed_file:
                for line in speed_file:
                    ethernet_interfaces.append(each)
        except OSError:
            pass
    return ethernet_interfaces



statusCacheTime = 0;
statusCache = struct.pack("<BBb",0,255, 0)
def getStatusBytes():
    global statusCacheTime, statusCache
    if time.time()< (statusCacheTime+10):
        return statusCache
    statusCacheTime = time.time()
    bstat = 0
    nstat = 255
    temp = 0
    try:
        import psutil
        battery = psutil.sensors_battery()
        bstat = int((battery.percent/100)*63)
        if battery.power_plugged:
            bstat +=128
        else:
            bstat+=0
        temp = 0
        x = psutil.sensors_temperatures()
        for i in x:
            for j in x[i]:
                if temp< j.current:
                    temp = j.current
    except:
        print(traceback.format_exc())
    
    #Linux only
    #TODO: This assumes that if there's wifi,
    #That's what's being used, otherwise we get unknown.
    #This inaccurate data is better than nothing I think.

    #In addition, it assumes there is only one WiFi
    try:

        ##This reports WiFi signal level on
        FNULL = open(os.devnull, 'w')
        p = subprocess.check_output("iwconfig", stderr=FNULL)
        sig = int(re.search(b"Signal level=(.*?)dBm",p).group(1).decode("utf8"))
        sig=min(sig, -20)
        sig=max(sig,-120)
        nstat= sig+120
    except:
       pass
    finally:
        FNULL.close() 

    statusCache = struct.pack("<BBb",int(bstat),nstat, max(min(int(temp), 127), -127))
    return statusCache




class ReturnChannel():
    """Node is supposed to be a secure ID of the node, preferably the session key they send to
    us with"""

    def __init__(self,q=None):
        self.queue = q or queue.Queue(64)
        #It's not a message target thing
        self.target = None
    
    def onResponse(self,data, node=None):
        self.queue.put(data,True,3)

class ExpectedAckTracker():
    def __init__(self,e,nodes):
        self.e = e
        self.nodes = nodes.copy()
        self.target = None

    def onResponse(self, data,node):
        try:
            if node in self.nodes:
                del self.nodes[node]
            #Used to let you specify you want at least one ACK.
            if 0 in self.nodes:
                del self.nodes[0]
        except:
            pass
        if  len(self.nodes)==0:
            self.e.set()



class MessageTarget():
    def __init__(self,target,callback):
        self.callback = callback
        self.target = target





#Allow use of bin, hex, etc PSKs 
def preprocessKey(k):
    #ECC doesn't use psk
    if k==None:
        return k
    if isinstance(k,bytes):
        if len(k)==32:
            return k
    elif isinstance(k,str):
        if len(k)==64:
            return bytes.fromhex(k)
        k = base64.b64decode(k)
        if len(k)==32:
            return k

    else:
        raise TypeError("Key must be bytes or str")
    
    raise ValueError("Key must be 32 bytes, or b64/hex encoded 32 bytes")

def cleanup():
    global allow_new
    allow_new = False
    with lock:
        #Close function mutates the list, copy first
        c = cleanup_refs[:]
        for i in c:
            try:
                i().close()
            except:
                pass

atexit.register(cleanup)

pavillion_logger = logging.getLogger("pavillion")

def nonce_from_number(n):
    return b'\x00'*(24-8)+struct.pack("<Q",n)

class testcipher():
    id=0
    def encrypt(self, d,k,nonce):
        return d+k+nonce
    def decrypt(self,d,k,nonce):
        return d[:-len(k+nonce)]
    def keyedhash(self,d,k):
        return hashlib.md5(d+k).digest()*2


#Attempt to import the crypto library.
try:
    import libnacl
    import libnacl.public
except:
    pavillion_logger.exception("Could not import libnacl, will not be able to handle encrypted messages")


class SodiumCipher():
    "Object providing a Pavillion cipher interface to libsodium"
    id=1
    asym_setup = False
    def encrypt(self,d,k,nonce):
        return libnacl.crypto_secretbox(d, nonce, k)

    def decrypt(self,d,k,nonce):
        return libnacl.crypto_secretbox_open(d, nonce, k)

    def keyedhash(self,d,k):
        return libnacl.crypto_generichash(d,k)

    def pubkey_encrypt(self,data,nonce,pk,sk):
        return libnacl.crypto_box(data,nonce,pk,sk)

    def pubkey_decrypt(self,data,nonce,pk,sk):
        return libnacl.crypto_box_open(data,nonce,pk,sk)

class libnacl_ecc(SodiumCipher):
    id=2
    asym_setup = True


#Don't actually use testcipher
ciphers = { 1:SodiumCipher(), 2:libnacl_ecc()}

