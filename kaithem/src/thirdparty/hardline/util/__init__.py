
import socket
import traceback
import re
import threading
import time
import struct
import uuid
import weakref
from nacl.hash import blake2b
import nacl


def makeLoopWorker(f):
    def f2():
        while 1:
            x = f()
            if x:
                try:
                    x.poll()
                except Exception:
                    print(traceback.format_exc())
    return f2


class LPDPeer():
    def parseLPD(self, m):
        t = ''
        if self.searchTopic in m:
            t += 'search'
        elif self.announceTopic in m:
            t += 'announce'
        else:
            return (None, None)

        d = {}
        for i in re.findall('^(.*)?: *(.*)\r+$', m, re.MULTILINE):
            d[i[0]] = i[1]

        return (t, d)

    def onDiscovery(self, hash, host, port, title):
        pass

    def makeLPD(self, m, h):
        return (h+" * HTTP/1.1\r\nPort: {Port}\r\nInfohash: {Infohash}\r\ncookie: {cookie}\r\ntitle: {title}\r\n\r\n\r\n").format(**m).encode('utf8')

    def makeLPDSearch(self, m, h):
        return (h+" * HTTP/1.1\r\nInfohash: {Infohash}\r\ncookie: {cookie}\r\n\r\n\r\n").format(**m).encode('utf8')

    def poll(self):
        if self.msock:
            try:
                d, addr = self.msock.recvfrom(4096)
            except socket.timeout:
                return

            except Exception:
                self.msock = None
                raise

            # Ignore not-LAN clients.
            isLan = (addr[0].split(".")[0] in (
                '127', '192', '10', '172', '169'))
            if not isLan:
                return
            
            self.handleData(d, addr)

        else:
            # Retry connect
            time.sleep(30)
            try:
                self.connect()
            except OSError:
                print(traceback.format_exc())
                return


    def handleData(self, d, addr):
        t, msg = self.parseLPD(d.decode('utf-8', errors='ignore'))

        if msg:

            if 'search' in t:
                if not msg.get('cookie', '') == self.cookie:
                    with self.lock:

                        # Empty infohash scans everyone.
                        if not msg['Infohash']:
                            for i in self.activeHashes:
                                # Mcast works better on localhost to localhost in the same process it seems
                                self.advertise(self.activeHashes[i][2], self.activeHashes[i][0][0], self.activeHashes[i][1], addr=(
                                    "239.192.152.143", 6771))

                                # Unicast needed for android without needed the extra multicast permission
                                self.advertise(
                                    self.activeHashes[i][2], self.activeHashes[i][0][0], self.activeHashes[i][1], addr=addr)
                            print("responding to lpd general scan")
                        else:
                            #Lookup by the legacy method
                            if msg['Infohash'] in self.activeHashes:
                                info = self.activeHashes[msg['Infohash']]

                                # Note that the key we actually advertise might not be the stored one.  We need to tell them about the actual
                                # Hash, but discovery may use the DOUBLE hash.  That way, the hash is only

                                # Mcast works better on localhost to localhost in the same process it seems
                                self.advertise(info[2], info[0][0],
                                            info[1], addr=("239.192.152.143", 6771))

                                # Unicast needed for android without needed the extra multicast permission
                                self.advertise(
                                    info[2], info[0][0], info[1], addr=addr)
                                print("responding to lpd")

                            #Allow lookup by the new rolling code method.
                            #To do this, we compute the rolling code of every hash ID.
                            else:
                                for i in self.activeHashes:
                                    rawHash = bytes.fromhex(i)
                                    timePeriod = struct.pack("<Q",int(time.time()/(3600*24)))
                                    rollingCode = blake2b(rawHash+timePeriod, encoder=nacl.encoding.RawEncoder())[:20].hex().lower()

                                    if rollingCode == msg['Infohash'].lower().strip():
                                        info = self.activeHashes[i]
                                        # Note that the key we actually advertise might not be the stored one.  We need to tell them about the actual
                                        # Hash, but discovery may use the DOUBLE hash.  That way, the hash is only

                                        # Mcast works better on localhost to localhost in the same process it seems
                                        self.advertise(info[2], info[0][0],
                                                        info[1], addr=("239.192.152.143", 6771))

                                        # Unicast needed for android without needed the extra multicast permission
                                        self.advertise(
                                            info[2], info[0][0], info[1], addr=addr)


            if 'announce' in t:
                if not msg.get('cookie', '') == self.cookie:
                    if msg.get("Infohash"):
                        self.onDiscovery(msg.get("Infohash"), addr[0], int(
                            msg.get("Port")), msg.get("title", ''))

    def advertise(self, hash, port, info, addr=None):
        # Unicast replies no reatelimit

        title = info.get('title', '')

        if not addr:
            if self.lastAdvertised.get(hash, 0) > time.time()+10:
                return
            self.lastAdvertised[hash] = time.time()


        alsoBroadcast = addr is None

        addr = addr or ("239.192.152.143", 6771)

        self.msock.sendto(self.makeLPD(
            {'Infohash': hash, 'Port': port, 'cookie': self.cookie, 'title': title}, self.announceTopic), addr)

        if alsoBroadcast:
            self.msock.sendto(self.makeLPD({'Infohash': hash, 'Port': port, 'cookie': self.cookie, 'title': title}, self.announceTopic), ("255.255.255.255", 6771))

    def register(self, hash, port, info, addr=None,n=1):

        #Port must be a list where the first item is the actual port!!!
        #This is so it can be mutable and changed later.

        # Ok, so the client should never broadcast the full hash, he might be in a coffee shop or something, roaming where attackers are.
        # So the lookup part of discovery only uses the certificate digest part of the hash.

        # Howver, for discovery listing purposes, the server must broadcast the full hash, everything needed to connect.  This is safer, because servers roam less,
        # And we are only trying to provide opportunistic protection for the names.

        # The reason we use double hashes is for WPA3.  If you roam to a WPA3 coffee shop, you will not reveal the hash to anyone except the router owner, because the
        # unhashed digest in the TLS SNI is unicast, which WPA3 keeps secret from other guests.
        fullhash = hash
        hash = hash.split("-")[-1]

        h = bytes.fromhex(hash)
        doublehash = blake2b(h, encoder=nacl.encoding.RawEncoder())[:20].hex()

        # Lookup by hash or rollingCode, store by fullhash.
        self.activeHashes[hash] = (port, info, fullhash)
        self.activeHashes[doublehash] = (port, info, fullhash)

    def unregister(self, hash):
        hash = hash.split("-")[-1]

        h = bytes.fromhex(hash)
        doublehash = blake2b(h, encoder=nacl.encoding.RawEncoder())[:20].hex()

        try:
            # Lookup by hash or rollingCode, store by fullhash.
            del self.activeHashes[hash]
        except KeyError:
            pass
        try:
            del self.activeHashes[doublehash] 
        except KeyError:
            pass
        
    
    def calcRollingCode(self,hash):
         # Password isn't part of discovery at all
        hash = hash.split("-")[-1]

        # Use double hashes for lookups, because we might be doing a lookup in public on someone eles's wifi
        h = bytes.fromhex(hash)
        
        #New clients use the rolling code method.  This is so that whenever you are on a public network that is not
        #the same network as the server, we don't reveal much information about what sites we are looking for,
        #which would allow fingerprinting based tracking.

        #This limits your trackability time because the code changes.

        #Note that because of traffic sniffing of the actual server connection, this is basically meaningless
        #Except for on networks with isolation between clients and where the attacker is not the network operator.
        #It's really just a slight bit of protection done opportinistically because it is so easy to implement.
        timePeriod = struct.pack("<Q",int(time.time()/(3600*24)))
        return blake2b(h+timePeriod, encoder=nacl.encoding.RawEncoder())[:20].hex().lower()

    def search(self, hash,n=1):
        # Not BT LPD compatible!! Use advertise for both searching and announcing

        # Empty hash leave as is for browsing
        rollingCode = ''
        if hash:

            rollingCode =self.calcRollingCode(hash)
            # Password isn't part of discovery at all
            hash = hash.split("-")[-1]

    
        if not self.msock:
            self.connect()

        try:
            t= self.makeLPDSearch(
                {'Infohash': rollingCode, 'cookie': self.cookie}, self.searchTopic)
            
            self.msock.sendto(t,("255.255.255.255", 6771))
            for i in range(n):
                self.msock.sendto(t,("239.192.152.143", 6771))

        except Exception:
            print(traceback.format_exc())
            self.msock = None
            raise

    def connect(self):

        self.msock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.msock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.msock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.msock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Bind to the server address
        if self.server:

            self.msock.bind(("0.0.0.0", 6771))

            group = socket.inet_aton("239.192.152.143")
            mreq = struct.pack('4sL', group, socket.INADDR_ANY)
            self.msock.setsockopt(
                socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        else:
            self.msock.bind(("0.0.0.0", 0))

        self.msock.settimeout(5)

    def __init__(self, announceTopic="BT-SEARCH", searchTopic="BT-SEARCH", server=True):

        # Message names used to search and announce.
        # You can use the same type for both, as in BT-SEARCH
        self.announceTopic = announceTopic
        self.searchTopic = searchTopic
        self.server = server

        try:
            self.connect()
        except Exception:
            self.msock = None
            print("Connect fail, will retry later. WiFi is probably just turned off.")
            print(traceback.format_exc())

        self.cookie = str(uuid.uuid4())

        self.lastAdvertised = {}

        # hash to (port,info,hash) mapping
        self.activeHashes = {}

        self.lock = threading.Lock()

        self.thread = threading.Thread(
            target=makeLoopWorker(weakref.ref(self)),daemon=True)
        self.thread.start()
