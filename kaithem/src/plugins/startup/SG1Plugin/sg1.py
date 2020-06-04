from Crypto.Cipher import ChaCha20_Poly1305
import serial
import time
import threading
import weakref
import struct
import traceback
import base64
import logging

from scullery import mqtt

import logging

logger = logging.Logger("SG1")


def b64(b):
    return base64.b64encode(b).decode('utf8').replace("=", '')


MSG_NEWDATA = 1
MSG_SET_KEY = 2
MSG_DECODE = 3
MSG_DECODED = 4
MSG_FAIL = 5
MSG_SEND = 6
MSG_RX = 7
MSG_SENT = 8
MSG_RNG = 9
MSG_CFG = 10
MSG_TIME = 11
MSG_RFPOWER = 12
MSG_DECODEDRT = 13
MSG_SENDRT = 14
MSG_PAIR = 15
MSG_VERSION = 16

# define RF_PROFILE_GFSK600 1
# define RF_PROFILE_GFSK1200 2
# define RF_PROFILE_GFSK4800 3
# define RF_PROFILE_GFSK10K 4
# define RF_PROFILE_GFSK38K 5
# define RF_PROFILE_GFSK100K 6
# define RF_PROFILE_GFSK250K 7

# RF Profiles
profiles = {
    600: 1,
    1200: 2,
    4800: 3,
    10000: 4,
    38400: 5,
    100_000: 6,
    250_000: 7
}


def hintBytesToNumber(hint):
    hint = hint[0:3]
    hint = hint + b'\0'
    hint = struct.unpack("<I", hint)[0] & 0b11111111111111111111
    return hint


def toIntervalNumber(t):
    return abs((int(t*10**6)) >> 24) % 2**32


def computeHintSequences(key, time):

    interval = toIntervalNumber(time)

    # closest interval number besides the current one
    altInterval = toIntervalNumber(time + 800000)
    if altInterval == interval:
        altInterval = toIntervalNumber(time - 8000000)

    c = ChaCha20_Poly1305.new(key=key, nonce=struct.pack("<Q", interval))
    x = c.encrypt(b"\0\0\0\0\0\0")
    hint = hintBytesToNumber(x[0:3])
    wake = hintBytesToNumber(x[3:6])

    c = ChaCha20_Poly1305.new(key=key, nonce=struct.pack("<Q", altInterval))
    x = c.encrypt(b"\0\0\0\0\0\0")
    althint = hintBytesToNumber(x[0:3])
    altwake = hintBytesToNumber(x[3:6])

    c = ChaCha20_Poly1305.new(key=key, nonce=b'\0\0\0\0\0\0\0\0')
    x = c.encrypt(b"\0\0\0")
    fixedhint = hintBytesToNumber(x[0:3])

    x = {
        'phint': hint,
        'altphint': althint,
        'fixedhint': fixedhint,
        'pwake': wake,
        'altpwake': altwake
    }
    return x


class HintLookup():
    def __init__(self):
        self.channelKeys = {}
        self.hintToChannelKeys = {}
        self.cacheTime = 0

    def compute(self, force=False):
        # Round to next time slot to compute cache
        t = (int(time.time()*10**6) + 2**23) >> 24
        if not force:
            if self.cacheTime == t:
                return
        self.cacheTime = t

        # Start with all the channel
        keys = self.channelKeys.copy()

        # Dict of lists of all the possible channel keys, indexed by
        # the hint, as a number.
        d = {}
        for i in self.channelKeys:
            h = computeHintSequences(i, time.time())
            for j in h:
                if h[j] in d:
                    d[h[j]].append(i)
                else:
                    d[h[j]] = [i]
        self.hintToChannelKeys = d


class NanoframeParser():
    def __init__(self, debugCallback):
        self.state = 0
        self.len = 0
        self.buf = []
        self.handleDebugOutput = debugCallback
        self.debugOutput = b''

    def parse(self, d):
        for b in d:
            if self.state == 0:
                if b == 42:
                    self.state = 1
                # Non ascii here, probably a framing error
                elif b < 10 or b > 127:
                    # Not a start byte, go to waiting for end
                    self.state = 3
                else:
                    # ASCII outside a packet, probably debug info
                    self.debugOutput += bytes([b])
                    if(b == ord('\n')):
                        if self.handleDebugOutput:
                            self.handleDebugOutput(self.debugOutput)
                        self.debugOutput = b''

            elif self.state == 1:
                self.len = b
                self.state = 2

            elif self.state == 2:
                self.buf.append(b)

                if len(self.buf) == self.len:
                    self.state = 3
                    buf = self.buf
                    self.buf = []
                    yield (buf[0], bytes(buf[1:]))
            elif self.state == 3:
                if b == 43:
                    self.state = 0
                else:
                    print("overrun")


def makeThreadFunction(wr):
    def f():
        while 1:
            x = wr()
            try:
                if x:
                    if not x.loop():
                        return
                else:
                    return
            except:
                print(traceback.format_exc())
            del x
    return f


class SG1Device():
    def __init__(self, channelKey, nodeID=7, gateways=None, mqttServer="__virtual__SG1", mqttPort="default"):
        self.bus = mqtt.getConnection(mqttServer, mqttPort)
        self.gateways = ['__all__']
        self.key = channelKey
        self.nodeID = nodeID

        self.bus.subscribe(
            "/SG1/i/"+b64(channelKey), self.onMessage, encoding="msgpack")

        self.bus.subscribe(
            "/SG1/ri/"+b64(channelKey), self.onRTMessage, encoding="msgpack")

        # This is how the gateway keeps track of what devices it's interested in.
        self.bus.subscribe(
            "/SG1/discoverDevices", self.replyToDiscovery, encoding="msgpack")

        # Tell any listening gateways that we exist
        self.bus.publish("/SG1/registerDevice/", self.key, encoding="msgpack")

        #Gateway, time, rssi
        self.lastMessageInfo = (None, 0, -127)

    def replyToDiscovery(self, t, m):
        self.bus.publish(
            "/SG1/registerDevice/", self.key, encoding="msgpack")

    def onMessage(self, t, m):
        print(t, m)
        t = time.monotonic()
        # If we get multiple copies of a message in rapid succession,
        # We want to mark the strongest gateway as the one we use for outgoing stuff
        if t > self.lastMessageInfo[1]-1 or m['rssi'] > self.lastMessageInfo[2]:
            self.lastMessageInfo = (m['gw'], t, m['rssi'])

    def onRTMessage(self, t, m):
        print(t, m)
        pass

    def sendMessage(self, data, rt=False):
        t = time.monotonic()
        # Select the gateway with the strongest signal, if we can
        # Otherwise we have to send from all gateways.
        if self.lastMessageInfo[1] > (t-60):
            gw = self.lastMessageInfo[0]
        else:
            gw = "__all__"
        self.bus.publish("/SG1/send/"+gw,
                         {
                             "key": self.key,
                             "data": data,
                             "rt": rt
                         },
                         encoding="msgpack"
                         )

    def wake(self):
        # Not sure how to properly do dynamic selection for this.
        self.bus.publish(
            "/SG1/wake__all__", self.channelKey, encoding="msgpack")

    def pair(self):
        self.bus.publish("/SG1/pair/"+self.gateways[0],
                         {
            "key": self.key,
            "nodeID": self.nodeID
        }, encoding="msgpack"
        )


# These objects represent a request from a device to the gateway to
# keep an object awake.


class SG1WakeRequest():
    pass


class SG1Gateway():
    def __init__(self, port, id="default", mqttServer="__virtual__SG1", mqttPort="default"):
        self.bus = mqtt.getConnection(mqttServer, mqttPort)
        self.lock = threading.RLock()
        self.port = port

        def debugMessage(m):
            self.bus.publish("/SG1/hwmsg/"+self.gwid, m)
        self.debugMessage = debugMessage
        self.parser = NanoframeParser(debugMessage)
        self.connected = False
        self.lastDidDiscovery = 0
        self.lastSentTime = 0

        self.lastSerConnectAttempt = 0

        self.thread = threading.Thread(
            target=makeThreadFunction(weakref.ref(self)), daemon=True)
        self.waitingTypes = {}

        self.connect()
        self.gwid = id
        # Devices that have been discovered via the bus, plus their
        # last announce timestamp
        self.discoveredDevices = {}
        self.hintlookup = HintLookup()

        self.thread.start()
        try:
            self.sync()
        except:
            pass
        self.lastSentTime = 0

        self.waitOnSyncLock = threading.Lock()

        self.currentKey = b'\0'*32
        self.currentProfile = 5
        self.currentChannel = 3

        # Indexed by channel key, ordered by timestamp, wake requests expire after
        # 30 seconds. Only change this list under lock.
        self.wakeRequests = {}

        # Now do the bus subscriptions
        self.bus.subscribe(
            "/SG1/wake/"+self.gwid, self.onWakeRequest, encoding="msgpack")
        self.bus.subscribe(
            "/SG1/send/"+self.gwid, self.onSendRequest, encoding="msgpack")
        self.bus.subscribe(
            "/SG1/wake/"+"__all__", self.onWakeRequest, encoding="msgpack")
        self.bus.subscribe(
            "/SG1/send/"+"__all__", self.onSendRequest, encoding="msgpack")
        self.bus.subscribe(
            "/SG1/pair/"+self.gwid, self.onDeviceRequestPair, encoding="msgpack")
        self.bus.subscribe(
            "/SG1/wake/"+"__all__", self.onDeviceRequestPair, encoding="msgpack")

        self.bus.subscribe("/SG1/registerDevice/",
                           self.handleAnnounce, encoding="msgpack")

    def setKeyList(self, keys):
        with self.lock:
            self.hintlookup.channelKeys = keys.copy()
            self.hintlookup.compute(True)

    def onMessage(self, channel, data, rssi, pathloss):
        n = "/SG1/i/"+b64(channel)
        m = {
            'data': data,
            'rssi': rssi,
            'gw': self.gwid,
            'loss': pathloss
        }
        self.bus.publish(n, m, encoding="msgpack")

    def onRtMessage(self, channel, data, rssi):
        n = "/SG1/ri/"+b64(channel)
        m = {
            'data': data,
            'rssi': rssi,
            'gw': self.gwid
        }
        self.bus.publish(n, m, encoding="msgpack")

    def onDisconnect(self):
        n = "/SG1/gwDisconnected"
        m = self.gwid
        self.bus.publish(n, m, encoding="msgpack")

    def onConnect(self):
        n = "/SG1/gwDisconnected"
        m = self.gwid
        self.bus.publish(n, m, encoding="msgpack")

    def onWakeRequest(self, topic, message):
        with lock:
            t = time.monotonic()
            self.wakeRequests[base64.b64decode(message)] = t

            # List gets full of old stuff, we garbage collect
            if len(self.wakeRequests) > 80:
                t = t-32
                self.wakeRequests = {
                    i: self.wakeRequests[i] for i in self.wakeRequests[i] if self.wakeRequests[i] > t}

    def onSendRequest(self, topic, message):
        # Don't wait around forever to send RT messages
        if self.lock.acquire(0.5 if message['rt'] else 10):
            try:
                self.setChannelKey(message['channel'])
                if message.rt:
                    self.sendSG1RT(message['data'])
                else:
                    self.sendSG1(message['data'])
            finally:
                self.lock.release()

    def onDeviceRequestPair(self, topic, message):
        "Used by a device object to request that the hub pair with a device"
        with self.lock:
            self.setChannelKey(message['key'])
            self.pair()

    def connect(self):
        if self.lastSerConnectAttempt > time.monotonic()-5:
            return
        self.lastSerConnectAttempt = time.monotonic()

        try:
            self.portObj = serial.Serial(self.port, 250000)
            self.portObj.timeout = 1
            # Re-sync the remote decoder
            logger.info("Reconnected to SG1 Gateway at "+self.port)

        except Exception:
            self.portObj = None
            print(traceback.format_exc())

    def handleAnnounce(self, topic, message):
        with self.lock:
            new = message not in self.discoveredDevices
            self.discoveredDevices[message] = time.monotonic()
            if new:
                self.setKeyList(self.discoveredDevices)

    def rediscoverDevices(self):
        self.bus.publish("/SG1/discoveredDevices", "", encoding="msgpack")
        with self.lock:
            # Device registration dissapears in 1 minute
            t = time.monotonic() * (60)
            self.discoveredDevices = {
                i: self.discoveredDevices[i] for i in self.discoveredDevices if self.discoveredDevices[i] > t}

    def loop(self):
        if time.monotonic() > self.lastDidDiscovery+10:
            self.rediscoverDevices()
            self.lastDidDiscovery = time.monotonic()

        try:
            try:
                b = self.portObj.read(1)
               
            except Exception:
                if self.connected:
                    self.connected = False
                    self.onDisconnect()

                time.sleep(1)
                with self.lock:
                    self.connect()
                    self.sync()
                time.sleep(1)
            if b:
                for i in self.parser.parse(b):
                    self._handle(*i)

            # The abs is there because we
            # want to send right away should the system time jump
            # We do this every second so they stay tightly in sync.
            if abs(time.time()-self.lastSentTime) > 1:
                self.sendTime()
                # Also check if a recompute is needed
                self.hintlookup.compute()

                self.listen()
                self.lastSentTime = time.time()

        except Exception:
            print(traceback.format_exc())
        return True

    def _handle(self, cmd, data):
         if not self.connected:
            self.connected = True
            self.onConnect()
        if cmd == MSG_RNG:
            self.rngData = data
            self.bus.publish("/SG1/RNG/"+self.gwid, data, encoding='raw')

        elif cmd == MSG_NEWDATA:
            with self.lock:
                rssi = struct.unpack("<b", data[:1])

                # We don't know what this packet is.
                # So we have to try both the realtime and standard encoding
                hint1 = hintBytesToNumber(data[1:4])
                hint2 = hintBytesToNumber(data[4:7])

                d = False
                if hint1 in self.hintlookup.hintToChannelKeys:
                    # Hints are literally just hints that don't uniquely define
                    # Anything, we could have multiple keys with the same hint
                    for i in self.hintlookup.hintToChannelKeys[hint1]:
                        key = i

                        self.setChannelKey(key)
                        self.decode(self.wakeRequests.get(key, 0))
                        # Give it time to actually decode, don't try to send
                        # More data than the gateway can handle.

                        # Other than that, we just send the decoding data
                        # For all keys, and the gateway will stop when it gets the
                        # correct one.
                        time.sleep(0.003)
                        d = True

                if hint2 in self.hintlookup.hintToChannelKeys:
                    for i in self.hintlookup.hintToChannelKeys[hint2]:
                        key = i
                        self.setChannelKey(key)
                        self.decode(self.wakeRequests.get(key, 0))
                        time.sleep(0.003)
                        d = True
                print(hint1, hint2)
                if not d:
                    print("UNKNOWN", hint1, hint2)
                    # Tell gateway to discard packet and move on
                    self.listen()

        elif cmd == MSG_DECODED:
            pathLoss = struct.unpack("<b", data[:1])
            rssi = struct.unpack("<b", data[1:2])
            rxiv = data[2:10]
            reserved = data[10:14]
            channel = data[14:46]
            data = data[46:]
            print(channel)
            self.onMessage(channel, data, rssi, pathLoss)

        elif cmd == MSG_DECODEDRT:
            rssi = struct.unpack("<b", data[:1])
            channel = data[1:33]
            data = data[33:]
            self.onRtMessage(channel, data, rssi)

        if cmd in self.waitingTypes:
            with self.lock:
                for i in self.waitingTypes[cmd]:
                    i[1].append(data)
                    i[0].set()

    def _sendMessage(self, cmd, m):
        with self.lock:
            self.portObj.write(b'\x2a')
            # +1 for the cmd byte
            self.portObj.write(bytes([len(m)+1]))
            self.portObj.write(bytes([cmd]))
            self.portObj.write(m)
            self.portObj.write(b'\x2b')
            self.portObj.flush()

    def sync(self):

        time.sleep(0.1)
        self.sendTime()

        # Wait till we are connected for real and the device is booted
        m = self.waitForMessage(MSG_VERSION)
        if not m:
            raise RuntimeError("Gateway did not publish version packet")
        ident = m[0:3]
        if not ident == b'SG1':
            raise RuntimeError("Bad magic number: "+str(ident))
        self.gwVersion = m[3]

        # Ensure decoder is in await_start state
        self.portObj.write(b'\x2b'*256)

        # Sync the time
        self.sendTime()

    def setChannelKey(self, key):
        if not len(key) == 32:
            raise ValueError("Key length must be 32")
        self.currentKey = key
        self._sendMessage(MSG_SET_KEY, key)

    def setRF(self, profile, channel):
        if profile in profiles:
            profile = profiles[profile]
        self.currentProfile = profile
        self.currentChannel = channel
        self._sendMessage(MSG_CFG, struct.pack("<BH", profile, channel))

    def listen(self):
        self._sendMessage(MSG_RX, b'')

    def decode(self, wakeUp=0):
        "WakeUp is the timestamp of the last wakerequest for the key we are decoding"
        self._sendMessage(MSG_DECODE, "b\x01" if (
            wakeUp > time.monotonic()-32) else b'\x01')

    def sendTime(self):
        t = struct.pack("<q", int(time.time() * 10**6))
        self._sendMessage(MSG_TIME, t)

    def getTime(self):
        self._sendMessage(MSG_TIME, b'')
        x = self.waitForMessage(MSG_TIME)
        if x:
            return struct.unpack("<Q", x)[0]/10**6
        return None

    def pair(self, newDeviceNodeId):
        with self.lock:
            self._sendMessage(MSG_PAIR, bytes([newDeviceNodeId]))
            time.sleep(5)

    def waitForMessage(self, t, timeout=3):
        e = threading.Event()
        boxlist = []
        x = (e, boxlist)
        with self.lock:
            if t not in self.waitingTypes:
                self.waitingTypes[t] = []
            self.waitingTypes[t].append(x)
        e.wait(timeout)

        with self.lock:
            self.waitingTypes[t].remove(x)

        if boxlist:
            return boxlist[0]
        else:
            return None

    def readRNG(self):
        "This function basically exists just for testing"
        self._sendMessage(MSG_RNG, b'')
        return self.waitForMessage(MSG_RNG)

