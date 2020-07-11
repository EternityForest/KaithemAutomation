from Crypto.Cipher import ChaCha20_Poly1305
import serial
import time
import threading
import weakref
import struct
import traceback
import base64
import logging
import collections
import random

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
MSG_DECODEDBEACON = 18
MSG_PING = 19
MSG_BGNOISE = 20
MSG_SENDREQUEST = 21
MSG_SENDREPLY = 22

MSG_DECODEDSPECIAL = 23
MSG_SENDSPECIALREQUEST = 24
MSG_SENDSPECIAL = 25
MSG_SENDSPECIALREPLY = 26
MSG_DECODEDREPLY = 27
MSG_DECODEDSPECIALREPLY = 28

#define MSG_DECODEDREPLY 27
HEADER_TYPE_FIELD = 0b1110000
HEADER_TYPE_SPECIAL = 0b0000000
HEADER_TYPE_UNRELIABLE = 0b0010000
HEADER_TYPE_RELIABLE = 0b0100000
HEADER_TYPE_REPLY = 0b1000000
HEADER_TYPE_REPLY_SPECIAL = 0b1010000

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
            try:
                x = wr()
                if x:
                    x.loop()
                    if not x.running:
                        return
                else:
                    return
                del x

            except:
                print(traceback.format_exc())
                try:
                    del x
                except:
                    pass
    return f


class SG1Device():
    def __init__(self, channelKey, nodeID=0, gateways=None, mqttServer="__virtual__SG1", mqttPort="default",localNodeID=1):
        self.bus = mqtt.getConnection(mqttServer, mqttPort)
        self.gateways = ['__all__']
        self.key = channelKey
        #Default 0, disable node ID filtering
        self.nodeID = nodeID
        self.localNodeID= 1
        self.keepAwake = False
        self.lock = threading.RLock()

        self.rxMessageTimestamps = collections.OrderedDict()

        self.bus.subscribe(
            "/SG1/i/"+b64(channelKey), self._onMessage, encoding="msgpack")

        self.bus.subscribe(
            "/SG1/ri/"+b64(channelKey), self._onRTMessage, encoding="msgpack")

        self.bus.subscribe(
            "/SG1/b/"+b64(channelKey), self._onBeacon, encoding="msgpack")

        # This is how the gateway keeps track of what devices it's interested in.
        self.bus.subscribe(
            "/SG1/discoverDevices", self.replyToDiscovery, encoding="msgpack")

        self.running = True

        # Tell any listening gateways that we exist
        self.bus.publish("/SG1/registerDevice/", self.key, encoding="msgpack")

        #Gateway, time, rssi, pathloss
        self.lastMessageInfo = (None, 0, -127, 127)

    def validateIncoming(self, m):
        """Enforce once and only once on the messages.  
        Even though gateways already do this, we could have multiple gateways."""
        if m['ts'] in self.rxMessageTimestamps:
            return False

        # Check if it's impossibly old.
        t = (time.time()-16)*10**6
        if m['ts'] < t:
            return False

        self.rxMessageTimestamps[m['ts']] = True

        try:
            # Garbage collect old messages that would be caught by the window
            if len(self.rxMessageTimestamps) > 2000:
                with self.lock:
                    torm = []
                    for i in self.rxMessageTimestamps:
                        if i < t:
                            torm.append(i)
                    for i in torm:
                        del self.rxMessageTimestamps[i]
        except:
            print(traceback.format_exc())
            self.handleError(traceback.format_exc())
            
        return True

    def replyToDiscovery(self, t, m):
        if self.running:
            self.bus.publish(
                "/SG1/registerDevice/", self.key, encoding="msgpack")

            if self.keepAwake and self.keepAwake():
                self.sendWakeRequest()

    def _onMessage(self, t, m):
        if self.running:
            # If we get multiple copies of a message in rapid succession,
            # We want to mark the strongest gateway as the one we use for outgoing stuff

            # Use abs to handle backwards time corrections

            # Do before the replay attack prevention stuff because we need to look at multiple
            # Gateways and find the strongest
            if abs(self.lastMessageInfo[1]-m['ts']) > 10**6 or m['rssi'] > self.lastMessageInfo[2]:
                self.lastMessageInfo = (m['gw'], m['ts'], m['rssi'], m['loss'])

            if (self.nodeID< 1) or (not 'id' in m) or (self.nodeID==m.get('id',0)):
                if self.validateIncoming(m):
                    self.onMessage(m)

    def sendWakeRequest(self):
        # Create a wake request at the selected gateway.
        # This request will last for 30 seconds.
        t = time.monotonic()
        if self.lastMessageInfo[1] > (t-60):
            gw = self.lastMessageInfo[0]
        else:
            gw = "__all__"

        self.bus.publish("/SG1/wake/"+gw, self.key, encoding="msgpack")

    def _onRTMessage(self, t, m):
        if self.running:
            if abs(self.lastMessageInfo[1]-m['ts']) > 10**6 or m['rssi'] > self.lastMessageInfo[2]:
                self.lastMessageInfo = (
                    m['gw'], m['ts'], m['rssi'], self.lastMessageInfo[3])

            if self.validateIncoming(m):
                self.onRTMessage(m)

    def onMessage(self, m):
        pass

    def onRTMessage(self, m):
        pass

    def _onBeacon(self, t, m):
        self.onBeacon(m)

    def onBeacon(self, m):
        pass

    def sendMessage(self, data, rt=False, power=-127, special=False, request=False, replyTo=False):
        t = time.monotonic()
        # Select the gateway with the strongest signal, if we can
        # Otherwise we have to send from all gateways.
        if self.lastMessageInfo[1] > (t-60):
            gw = self.lastMessageInfo[0]
            if power == -127:
                # Use path loss info to compute what to do.
                power = min(8, (-75) + self.lastMessageInfo[3])
        else:
            power = 8
            gw = "__all__"

        m = {
            "key": self.key,
            "data": data,
            "rt": rt,
            "pwr": power
        }

        if request:
            m['req'] = True
        if replyTo:
            m['replyTo'] = replyTo
        if special:
            m['special'] = special
        
        if not self.localNodeID==1:
            m['localID'] = self.localNodeID

        self.bus.publish("/SG1/send/"+gw,
                         m,
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

    def handleException(self, msg):
        logger.exception(msg)

    def handleError(self, msg):
        logger.error(msg)

    def close(self):
        self.running = False


# These objects represent a request from a device to the gateway to
# keep an object awake.


class SG1WakeRequest():
    pass


class SG1Gateway():
    def __init__(self, port, id="default", mqttServer="__virtual__SG1", mqttPort="default", channelNumber=3, rfProfile=7):
        self.bus = mqtt.getConnection(mqttServer, mqttPort)
        self.lock = threading.RLock()

        # Used for matching requests to responses.
        self.reqID = 0

        self.reqsAwaiting = {}

        self.port = port
        self.gwid = id

        self.currentProfile = rfProfile
        self.currentChannel = channelNumber

        self.lastMessageSentPerChannelKey = collections.OrderedDict()

        self.running = True

        self.parser = NanoframeParser(self.onHWMessage)
        self.connected = False
        self.lastDidDiscovery = 0
        self.lastSentTime = 0

        self.lastSerConnectAttempt = -9999999999

        self.thread = threading.Thread(
            target=makeThreadFunction(weakref.ref(self)), daemon=True)
        self.waitingTypes = {}

        self.portObj = None
        self.portRetryTimes = {}

        # For each key, we are going to store the last IV of the message we sent
        # This is slightly complicated, because we don't know the message
        # IV until the gateway tells us what it is, after it's been sent

        # For the gateway to be able to recieve challenge-response replies,
        # We must tell it the challenge when we are decoding.
        # This is because the gateway interface itself doesn't have enough memory
        # to store multiple challenges.
        self.lastSentOnKey = {}

        # This maps send request IDs to the channel key that we were sending on.
        # This means that when we get a "sent" packet, we can update our list of
        # the most recent IV sent

        # No GC needed, there are only 256 possible request IDs
        self.sendReqIdToKey = {}

        # Maps request for decoding to Key,challenge pair
        self.decodeReqIdToKeyIV = {}

        self.reqIDCounter = int(random.random()*255)

        self.connect()
        # Devices that have been discovered via the bus, plus their
        # last announce timestamp
        self.discoveredDevices = {}
        self.hintlookup = HintLookup()

        self.thread.start()
        try:
            self.sync()
        except Exception:
            logger.exception(
                "Error connecting to SG1 Gateway at: "+str(port)+",retrying later")
        self.lastSentTime = 0

        self.waitOnSyncLock = threading.Lock()

        self.currentKey = b'\0'*32
        self.currentProfile = rfProfile
        self.currentChannel = channelNumber

        # Indexed by channel key, ordered by timestamp, wake requests expire after
        # 30 seconds. Only change this list under lock.
        self.wakeRequests = {}

        # Now do the bus subscriptions
        self.bus.subscribe(
            "/SG1/wake/"+self.gwid, self.onWakeRequest, encoding="msgpack")
        self.bus.subscribe(
            "/SG1/send/"+self.gwid, self.onSendRequest, encoding="msgpack")
        self.bus.subscribe(
            "/SG1/wake/"+self.gwid, self.onWakeRequest, encoding="msgpack")
        self.bus.subscribe(
            "/SG1/send/"+"__all__", self.onSendRequest, encoding="msgpack")
        self.bus.subscribe(
            "/SG1/pair/"+self.gwid, self.onDeviceRequestPair, encoding="msgpack")
        self.bus.subscribe(
            "/SG1/wake/"+"__all__", self.onWakeRequest, encoding="msgpack")

        self.bus.subscribe("/SG1/registerDevice/",
                           self.handleAnnounce, encoding="msgpack")

    def handleError(self, msg):
        logger.error(msg)

    def setKeyList(self, keys):
        with self.lock:
            self.hintlookup.channelKeys = keys.copy()
            self.hintlookup.compute(True)

    def close(self):
        self.running = False

    def onHWMessage(self, t):
        logging.info("GW HW msg:" + str(t))

    def onBeacon(self, channel, rssi, pathLoss):
        n = "/SG1/b/"+b64(channel)
        m = {
            'rssi': rssi,
            'gw': self.gwid,
            'loss': pathLoss
        }
        self.bus.publish(n, m, encoding="msgpack")

    def onMessage(self, channel, data, rssi, pathloss, timestamp, nodeID, rxHeader1, replyTo=None, request=False):
        n = "/SG1/i/"+b64(channel)
        m = {
            'data': data,
            'rssi': rssi,
            'gw': self.gwid,
            'loss': pathloss,
            'id': nodeID,
            "ts": timestamp,
            "h": rxHeader1
        }
        if replyTo:
            m['replyTo'] = replyTo

        if request:
            m['req'] = True

        self.bus.publish(n, m, encoding="msgpack")

    def onSpecialMessage(self, channel, data, rssi, pathloss, timestamp, nodeID, rxHeader1,replyTo=None,request=False):
        n = "/SG1/sp/"+b64(channel)
        m = {
            'data': data,
            'rssi': rssi,
            'gw': self.gwid,
            'loss': pathloss,
            'id': nodeID,
            "ts": timestamp,
            "h": rxHeader1
        }

        if replyTo:
            m['replyTo'] = replyTo

        if request:
            m['req'] = True
        self.bus.publish(n, m, encoding="msgpack")

    def onRtMessage(self, channel, data, rssi, timestamp, nodeID):
        n = "/SG1/ri/"+b64(channel)
        m = {
            'data': data,
            'rssi': rssi,
            'gw': self.gwid,
            'id': nodeID,
            "ts": timestamp
        }
        self.bus.publish(n, m, encoding="msgpack")

    def onDisconnect(self):
        n = "/SG1/gwDisconnected"
        m = self.gwid
        self.bus.publish(n, m, encoding="msgpack")

    def onConnect(self):
        n = "/SG1/gwConnected"
        m = self.gwid
        self.bus.publish(n, m, encoding="msgpack")

    def onWakeRequest(self, topic, message):
        with self.lock:
            t = time.monotonic()
            self.wakeRequests[message] = t

            # List gets full of old stuff, we garbage collect
            if len(self.wakeRequests) > 3600:
                t = t-32
                self.wakeRequests = {
                    i: self.wakeRequests[i] for i in self.wakeRequests[i] if self.wakeRequests[i] > t}

    def onSendRequest(self, topic, message):
        # Don't wait around forever to send RT messages
        if self.lock.acquire(1 if message['rt'] else 3):
            try:
                self.setChannelKey(message['key'])

                #Normally anything from the gateway has an ID of 1, but sometimes we want local "virtual"
                #devices to talk between gateways.
                id = message.get('localID',1)
                if message['rt']:
                    self.sendSG1RT(message['data'], message['pwr'],id)
                else:

                    # Determine which of the six message types to send
                    # By combination of special, request, and reply attributes
                    if message.get("sp", False):
                        if message.get("req", False):
                            self.sendSG1SpecialRequest(
                                message['data'], message['pwr'],id)
                        elif message.get("replyTo", False):
                            self.sendSG1SpecialReply(
                                message['data'], message.get("replyTo", False), message['pwr'],id)
                        else:
                            self.sendSG1Special(
                                message['data'], message['pwr'],id)
                    else:
                        if message.get("req", False):
                            self.sendSG1Request(
                                message['data'], message['pwr'],id)

                        elif message.get("replyTo", False):
                            self.sendSG1Reply(
                                message['data'], message.get("replyTo", False), message['pwr'],id)
                        else:
                            self.sendSG1(
                                message['data'], message['pwr'],id)

            finally:
                self.lock.release()

    def sendSG1(self, data, power=0, id=1):
        # 2 reserved bytes

        self.reqIDCounter = (self.reqIDCounter+1)%256
        self.sendReqIdToKey[self.reqIDCounter]=self.currentKey

        m = bytes([struct.pack("<b",power)[0], self.reqIDCounter, id, 0]) + data

        self._sendMessage(MSG_SEND, m)

    def sendSG1Request(self, data, power=0,id=1):
        # 2 reserved bytes
        
        self.reqIDCounter = (self.reqIDCounter+1)%256
        self.sendReqIdToKey[self.reqIDCounter]=self.currentKey
        m = bytes([struct.pack("<b",power)[0], self.reqIDCounter, id, 0]) + data

        self._sendMessage(MSG_SENDREQUEST, m)

    def sendSG1Reply(self, data, challenge, power=0,id=1):

        if isinstance(challenge, dict):
            challenge = challenge['ts']

        self.reqIDCounter = (self.reqIDCounter+1)%256
        self.sendReqIdToKey[self.reqIDCounter]=self.currentKey

        # 3 reserved bytes
        m = bytes([struct.pack("<b",power)[0], self.reqIDCounter, id, 0]) + challenge + data

        self._sendMessage(MSG_SENDREPLY, m)


    def sendSG1Special(self, data, power=0,id=1):
        
        self.reqIDCounter = (self.reqIDCounter+1)%256
        self.sendReqIdToKey[self.reqIDCounter]=self.currentKey
        # 2 reserved bytes
        m = bytes([struct.pack("<b",power)[0], self.reqIDCounter, id, 0]) + data

        self._sendMessage(MSG_SENDSPECIAL, m)

    def sendSG1SpecialRequest(self, data, power=0,id=1):
        # 3 reserved bytes
        self.reqIDCounter = (self.reqIDCounter+1)%256
        self.sendReqIdToKey[self.reqIDCounter]=self.currentKey
        m = bytes([struct.pack("<b",power)[0], self.reqIDCounter, id, 0]) + data

        self._sendMessage(MSG_SENDSPECIALREQUEST, m)

    def sendSG1SpecialReply(self, data, challenge, power=0,id=1):
        # 3 reserved bytes
        self.reqIDCounter = (self.reqIDCounter+1)%256
        self.sendReqIdToKey[self.reqIDCounter]=self.currentKey
        m = bytes([struct.pack("<b",power)[0], self.reqIDCounter, id, 0]) + challenge + data

        self._sendMessage(MSG_SENDSPECIALREPLY, m)


    def sendSG1RT(self, data, power=0):
        # 3 reserved bytes
        m = bytes([struct.pack("<b",power)[0], 0, 0, 0]) + data
        self._sendMessage(MSG_SENDRT, m)

    def onDeviceRequestPair(self, topic, message):
        "Used by a device object to request that the hub pair with a device"
        with self.lock:
            self.setChannelKey(message['key'])
            self.pair()

    def connect(self):
        # If last attempt is too recent
        if self.lastSerConnectAttempt > (time.monotonic()-5):
            return 0
        self.lastSerConnectAttempt = time.monotonic()

        # Basically tries a random one we haven't tried before
        if self.port.strip() == "__auto__":
            import serial.tools.list_ports as serlisttools

            x = {i.device for i in serlisttools.comports()}

            port = random.choice(x)

            # Remove and reinsert resets retry restrictions
            for i in list(self.portRetryTimes.keys()):
                if i not in x:
                    self.portRetryTimes.pop(i)

            if self.portRetryTimes.get(port, 0) > time.monotonic() - 1200:
                return 0
        else:
            port = self.port
        try:
            self.portObj = serial.Serial(self.port, 250000,timeout=1, writeTimeout=1)
            #Wait till we can actually open a connection
            for i in range(0, 5):
                try:
                    self.portObj.write(b'\x2b')
                    break
                except:
                    time.sleep(0.01)
            # Re-sync the remote decoder
            logger.info("Connected to SG1 Gateway at "+port)
            return 1


        except Exception:
            self.portObj = None
            if self.portRetryTimes.get(port,0)< time.monotonic()-600:
                logging.exception("Reconnect fail (ratelimited message) to: "+port)
                self.handleError("Could not connect to: "+port)
            self.portRetryTimes[port] = time.monotonic()

            print(traceback.format_exc())

    def handleAnnounce(self, topic, message):
        with self.lock:
            new = message not in self.discoveredDevices
            self.discoveredDevices[message] = time.monotonic()
            if new:
                self.setKeyList(self.discoveredDevices)

    def rediscoverDevices(self):
        self.bus.publish("/SG1/discoverDevices", "", encoding="msgpack")
        with self.lock:
            # Device registration dissapears in 1 minute
            t = time.monotonic() + (60)
            self.discoveredDevices = {
                i: self.discoveredDevices[i] for i in self.discoveredDevices if self.discoveredDevices[i] > t}

    def loop(self):
        if time.monotonic() > self.lastDidDiscovery+10:
            self.rediscoverDevices()
            self.lastDidDiscovery = time.monotonic()

        try:
            try:

                b = self.portObj.read(1)
                if b:
                    for i in self.parser.parse(b):
                        try:
                            self._handle(*i)
                        except:
                            self.handleError(traceback.format_exc(chain=True))
            except Exception:
                print(traceback.format_exc())
                if self.connected:
                    self.connected = False
                    self.onDisconnect()

                time.sleep(1)
                with self.lock:
                    if self.connect():
                        self.sync()
                    else:
                        return
                time.sleep(1)

            # The abs is there because we
            # want to send right away should the system time jump
            # We do this every second so they stay tightly in sync.

            # Don't block the loop though
            if self.lock.acquire(False):
                try:
                    if abs(time.time()-self.lastSentTime) > 1:
                        self.sendTime()
                        # Also check if a recompute is needed
                        self.hintlookup.compute()

                        self.listen()
                        self.lastSentTime = time.time()
                finally:
                    self.lock.release()

        except Exception:
            print(traceback.format_exc())

        return self.running

    def testLatency(self):
        #Average, min, max
        self._sendMessage(MSG_PING, b'')
        self.waitForMessage(MSG_PING, 5)

        avg = 0
        mn = 1000
        mx = 0
        for i in range(0, 10):
            start = time.monotonic()
            self._sendMessage(MSG_PING, b'')
            self.waitForMessage(MSG_PING)
            x = time.monotonic()-start
            mn = min(x, mn)
            mx = max(x, mx)
            avg += x
        return((avg/10, mn, mx))

    def _handle(self, cmd, data):
        #logger.info("pkt:" +str(cmd)+"  "+str(data))
        if cmd == MSG_VERSION:
            if not self.connected:
                self.connected = True
                self.onConnect()
        if cmd == MSG_RNG:
            self.rngData = data
            self.bus.publish("/SG1/RNG/"+self.gwid, data, encoding='msgpack')

        elif cmd == MSG_NEWDATA:
            with self.lock:
                rssi = struct.unpack("<b", data[:1])[0]

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
#                print(hint1, hint2)
                if not d:
                    #                    print("UNKNOWN", hint1, hint2)
                    # Tell gateway to discard packet and move on
                    self.listen()

        elif cmd == MSG_DECODEDBEACON:
            pathLoss = struct.unpack("<b", data[:1])[0]
            rssi = struct.unpack("<b", data[1:2])[0]
            channel = data[6:6+32]
            self.onBeacon(channel, rssi, pathLoss)

        elif cmd == MSG_DECODED:
            pathLoss = struct.unpack("<b", data[:1])[0]
            rssi = struct.unpack("<b", data[1:2])[0]
            rxiv = data[2:10]
            rxHeader1 = data[10]
            reserved = data[11:14]
            channel = data[14:46]
            data = data[46:]

            timestamp = struct.unpack("<Q", rxiv)[0]
            nodeID = rxiv[0]

            request = rxHeader1 & HEADER_TYPE_RELIABLE

            self.onMessage(channel, data, rssi, pathLoss,
                           timestamp, nodeID, rxHeader1, request=request)

        elif cmd == MSG_DECODEDREPLY:
            pathLoss = struct.unpack("<b", data[:1])[0]
            rssi = struct.unpack("<b", data[1:2])[0]
            rxiv = data[2:10]
            rxHeader1 = data[10]
            reserved = data[11:14]
            channel = data[14:46]
            challenge = data[46:54]
            data = data[54:]

            timestamp = struct.unpack("<Q", rxiv)[0]
            nodeID = rxiv[0]

            # Maybe race condition here, don't care, very rare dropped
            # packets are the worst it could do.

            #This is under lock, we can't possibly decode, then send the gateway
            #the same already used key.

            #It may be possible to decode twice before the first one ever gets to us,

            #That should be insanely rare and caught be the window of stored messages we keep
            #For replay protection.
            if self.lastSentOnKey[channel] == challenge:
                self.lastSentOnKey.pop(channel, None)

            self.onMessage(channel, data, rssi, pathLoss,
                           timestamp, nodeID, rxHeader1, replyTo=challenge)

        elif cmd == MSG_DECODEDSPECIAL:
            pathLoss = struct.unpack("<b", data[:1])[0]
            rssi = struct.unpack("<b", data[1:2])[0]
            rxiv = data[2:10]
            rxHeader1 = data[10]
            reserved = data[11:14]
            channel = data[14:46]
            data = data[46:]

            timestamp = struct.unpack("<Q", rxiv)[0]
            nodeID = rxiv[0]

            request = rxHeader1 & HEADER_TYPE_RELIABLE


            self.onSpecialMessage(channel, data, rssi,
                                  pathLoss, timestamp, nodeID, rxHeader1,request=request)



        elif cmd == MSG_DECODEDSPECIALREPLY:
            pathLoss = struct.unpack("<b", data[:1])[0]
            rssi = struct.unpack("<b", data[1:2])[0]
            rxiv = data[2:10]
            rxHeader1 = data[10]
            reserved = data[11:14]
            channel = data[14:46]
            challenge = data[46:54]
            data = data[54:]

            timestamp = struct.unpack("<Q", rxiv)[0]
            nodeID = rxiv[0]

            # Maybe race condition here, don't care, very rare dropped
            # packets are the worst it could do.
            if self.lastSentOnKey[channel] == challenge:
                self.lastSentOnKey.pop(channel, None)

            self.onSpecialMessage(channel, data, rssi, pathLoss,
                           timestamp, nodeID, rxHeader1, replyTo=challenge)
      

        elif cmd == MSG_DECODEDRT:
            rssi = struct.unpack("<b", data[:1])[0]
            rxiv = data[1: 9]
            reserved = data[9: 13]
            channel = data[13:45]
            data = data[45:]

            timestamp = struct.unpack("<Q", rxiv)[0]
            nodeID = rxiv[0]

            self.onRtMessage(channel, data, rssi, timestamp, nodeID)

        elif cmd == MSG_BGNOISE:
            rssi = struct.unpack("<b", data[:1])[0]
            self.onNoiseMeasurement(rssi)

        elif cmd == MSG_SENT:
            # Let the gateway tell us the IV that it was sent with.
            if data:
                reqID = data[0]
                iv = data[1:9]
                # Store the IV we sent, we will need it later for
                # challenge response
                if iv:
                    x = self.sendReqIdToKey.pop(reqID, None)
                    if not x is None:
                        self.lastSentOnKey[x] = iv

        if cmd in self.waitingTypes:
            # Lock free here. Scary!
            for i in self.waitingTypes[cmd]:
                i[1].append(data)
                i[0].set()

    def onNoiseMeasurement(self, rssi):
        pass

    def _sendMessage(self, cmd, m):
        with self.lock:
            try:
                self.portObj.write(b'\x2a')
                # +1 for the cmd byte
                self.portObj.write(bytes([len(m)+1]))
                self.portObj.write(bytes([cmd]))
                self.portObj.write(m)
                self.portObj.write(b'\x2b')
                self.portObj.flush()
            except:
                print("ERRRRRRRRRRRRRRRRRRRr", self.portObj)
                raise

    def sync(self):

        time.sleep(0.1)

        # Wait till we are connected for real and the device is booted
        m = self.waitForMessage(MSG_VERSION, 5)
        if not m:
            raise RuntimeError("Gateway did not publish version packet")
        ident = m[0:3]
        if not ident == b'SG1':
            raise RuntimeError("Bad magic number: "+str(ident))
        self.gwVersion = m[3]

        # Ensure decoder is in await_start state
        with self.lock:
            self.portObj.write(b'\x2b'*256)

        # Sync the time
        self.sendTime()
        self.setRF(self.currentProfile, self.currentChannel)

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

    def decode(self, wakeUp=0, challenge=b''):
        "WakeUp is the timestamp of the last wakerequest for the key we are decoding"

        flags = b"\x01" if (
            wakeUp > time.monotonic()-32) else b'\x00'

        self._sendMessage(MSG_DECODE, flags+challenge)

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
