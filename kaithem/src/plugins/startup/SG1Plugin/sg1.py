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

MSG_DECODEDSPECIAL = 23
MSG_SENDSPECIAL = 25


MSG_DECODEDSTRUCTURED = 29
MSG_SEND_STRUCTURED = 30

HEADER_TYPE_FIELD = 0b1110000
HEADER_TYPE_SPECIAL = 0b0000000
HEADER_TYPE_UNRELIABLE = 0b0010000
# HEADER_TYPE_RELIABLE = 0b0100000
HEADER_TYPE_STRUCTURED = 0b1000000
HEADER_TYPE_REPLY_SPECIAL = 0b1010000



RECORD_CONFIG_SET =6 
RECORD_CONFIG_GET =7
RECORD_CONFIG_SAVE =8
RECORD_CONFIG_DECLARE =9


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
                    yield (buf[0], bytes(buf[1:]))

            elif self.state == 3:
                if b == 43:
                    self.state = 0
                    self.buf = []

                else:
                    print("overrun", self.buf[:3])


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


def decodeStructuredMessage(m):
    "Decode a message and replace the data with a list of type,channel, data structured tuples representing each record in the message"
    d = m['data']
    msg = []

    while d:
        l = 2 + (1 << (d[1] & 0b11))
        c = d[:l]
        d = d[l+2:]
        msg.append((c[0], c[1] >> 2, c[2:]))

    m['data'] = msg
    return m


len_to_cope = {1: 0, 2: 1, 4: 2, 8: 3}


class StructuredMessageWriter():
    "Object which is associated with a device and can be used to send structured messages"
    def __init__(self, dev):
        self.buffer = b''
        self.dev = dev

    def write(self, type, data, channel=0):
        b = bytes([type, channel << 2 | len_to_cope[len(data)]])+data
        b2 = self.buffer+b

        if len(b2) > 12:
            self.flush()
            self.buffer = b
        else:
            self.buffer = b2

    def flush(self,power=-127):
        self.dev.sendMessage(self.buffer,power=power, structured=True)
        self.buffer = b''

class SG1Device():
    """
        Represents one local virtual SG1 device.  Note that this does not directly talk to any hardware devices directly.
        Instead, it uses MQTT to talk to a gateway.  If device and gateway are it the same program, it can use a "virtual mqtt server" provided by scullery.

        There can be multiple gateways on any given MQTT server, and a device can use all of them(the default) or a list of any subset of them by their gateway ID.

        Note: the SG1 encryption keys are sent currently sent in total plaintext via the gateway, so your connection must be secure, and attackers must not be able to connect to it.
        Even localhost is not safe if you allow connections to the local server from unsafe networks.

        The reason for this is that the gateway does most of the real decoding work, and needs to actuallly know the keys

        This is somewhat of a feature, because it makes debugging and reverse engineering your own devices easy.

        All MQTT traffic uses topics starting with /SG1/.
    

        Virtual connections never leave the process.

    """
    def __init__(self, channelKey, remoteNodeID=0, gateways=None, mqttServer="__virtual__SG1", mqttPort="default", localNodeID=None):
        self.bus = mqtt.getConnection(mqttServer, mqttPort)
        self.gateways = gateways or ['__all__']
        self.key = channelKey
        # Default 0, disable node ID filtering
        self.nodeID = remoteNodeID
        self.localNodeID= localNodeID or 1
        self.keepAwake = False
        self.lock = threading.RLock()

        self.rxMessageTimestamps = collections.OrderedDict()

        self.bus.subscribe(
            "/SG1/i/"+b64(channelKey), self._onMessage, encoding = "msgpack")

        self.bus.subscribe(
            "/SG1/is/"+b64(channelKey), self._onStructuredMessage, encoding = "msgpack")

        self.bus.subscribe(
            "/SG1/ri/"+b64(channelKey), self._onRTMessage, encoding = "msgpack")

        self.bus.subscribe(
            "/SG1/b/"+b64(channelKey), self._onBeacon, encoding = "msgpack")

        # This is how the gateway keeps track of what devices it's interested in.
        self.bus.subscribe(
            "/SG1/discoverDevices", self._replyToDiscovery, encoding = "msgpack")

        self.running=True

        # Tell any listening gateways that we exist
        self.bus.publish("/SG1/registerDevice/",
                         self.key, encoding = "msgpack")

        # Gateway, time, rssi, pathloss
        self.lastMessageInfo=(None, 0, -127, 127)
        self.StructuredMessageWriter=StructuredMessageWriter(self)

        self.writeStructured=self.StructuredMessageWriter.write
        self.flushStructured=self.StructuredMessageWriter.flush





    #These are called whith message objects when we gat the different kinds of message
    def onMessage(self, m):
        pass

    def onRTMessage(self, m):
        pass

    def onStructuredMessage(self, m):
        """m['data'] is  a list of type,channel, data tuples, one for each record in the message"""
        pass

    def onBeacon(self, m):
        pass


    def sendMessage(self, data, rt = False, power =-127, special=False,structured=False):
        """
            Send some bytes as an SG1 message.  -127 indicates auto TX power control
        """
        t=time.monotonic()
        # Select the gateway with the strongest signal, if we can
        # Otherwise we have to send from all gateways.
        if self.lastMessageInfo[1] > (t-60):
            gw=self.lastMessageInfo[0]
            if power == -127:
                # Use path loss info to compute what to do.
                power=min(8, (-75) + self.lastMessageInfo[3])
        else:
            power=8
            gw="__all__"

        m={
            "key": self.key,
            "data": data,
            "pwr": power
        }

        if special:
            m['type'] = 'special'

        elif structured:
            m['type'] = 'struct'
            if rt:
                raise ValueError("message can't be rt and structured")
        elif rt:
             m['type'] = 'rt'
        else:
             m['type'] = 'sg1'



        if not self.localNodeID == 1:
            m['localID'] = self.localNodeID

        self.bus.publish("/SG1/send/"+gw,
                         m,
                         encoding = "msgpack"
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


    def sendWakeRequest(self):
        """ Create a wake request at the selected gateway. This request will last for 30 seconds.
           While active, the gateway will try ot wake up the devices on this channel if they are in low power beacon mode
        """
        t=time.monotonic()
        if self.lastMessageInfo[1] > (t-60):
            gw=self.lastMessageInfo[0]
        else:
            gw="__all__"

        self.bus.publish("/SG1/wake/"+gw, self.key, encoding = "msgpack")









    def _validateIncoming(self, m):
        """Enforce once and only once on the messages.
        Even though gateways already do this, we could have multiple gateways."""
        if m['ts'] in self.rxMessageTimestamps:
            return False

        # Check if it's impossibly old.
        t=(time.time()-16)*10**6
        if m['ts'] < t:
            return False

        self.rxMessageTimestamps[m['ts']]=True

        try:
            # Garbage collect old messages that would be caught by the window
            if len(self.rxMessageTimestamps) > 2000:
                with self.lock:
                    torm=[]
                    for i in self.rxMessageTimestamps:
                        if i < t:
                            torm.append(i)
                    for i in torm:
                        del self.rxMessageTimestamps[i]
        except:
            print(traceback.format_exc())
            self.handleError(traceback.format_exc())

        return True

    def _replyToDiscovery(self, t, m):
        if self.running:
            self.bus.publish(
                "/SG1/registerDevice/", self.key, encoding = "msgpack")

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
                self.lastMessageInfo=(m['gw'], m['ts'], m['rssi'], m['loss'])

            if (self.nodeID < 1) or (not 'id' in m) or (self.nodeID == m.get('id',0)):
                if self._validateIncoming(m):
                    self.onMessage(m)

    def _onStructuredMessage(self, t, m):
        if self.running:
            # If we get multiple copies of a message in rapid succession,
            # We want to mark the strongest gateway as the one we use for outgoing stuff

            # Use abs to handle backwards time corrections

            # Do before the replay attack prevention stuff because we need to look at multiple
            # Gateways and find the strongest
            if abs(self.lastMessageInfo[1]-m['ts']) > 10**6 or m['rssi'] > self.lastMessageInfo[2]:
                self.lastMessageInfo=(m['gw'], m['ts'], m['rssi'], m['loss'])

            if (self.nodeID < 1) or (not 'id' in m) or (self.nodeID == m.get('id',0)):
                if self._validateIncoming(m):
                    self.onStructuredMessage(decodeStructuredMessage(m))

    def _onRTMessage(self, t, m):
        if self.running:
            if abs(self.lastMessageInfo[1]-m['ts']) > 10**6 or m['rssi'] > self.lastMessageInfo[2]:
                self.lastMessageInfo=(
                    m['gw'], m['ts'], m['rssi'], self.lastMessageInfo[3])

            if self._validateIncoming(m):
                self.onRTMessage(m)

    
    def _onBeacon(self, t, m):
        self.onBeacon(m)





# These objects represent a request from a device to the gateway to
# keep an object awake.


class SG1WakeRequest():
    pass


class SG1Gateway():
    """Represents an interface to an SG1 gateway hardware device.  You can't do anything application level with this directly,
       you just have 
    """
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
        try:
            self.thread.name="SG1Thread"
        except:
            pass
        self.waitingTypes = {}

        self.portObj = None
        self.portRetryTimes = {}

    
        self.reqIDCounter = int(random.random()*255)

        self.connect()
        # Devices that have been discovered via the bus, plus their
        # last announce timestamp
        self.discoveredDevices = {}
        self.hintlookup = HintLookup()
        self.lastPrintedErr=0


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

    def onMessage(self, channel, data, rssi, pathloss, timestamp, nodeID, rxHeader1):
        if not rxHeader1&HEADER_TYPE_FIELD == HEADER_TYPE_STRUCTURED:
            n = "/SG1/i/"+b64(channel)
        else:
            n = "/SG1/is/"+b64(channel)

        m = {
            'data': data,
            'rssi': rssi,
            'gw': self.gwid,
            'loss': pathloss,
            'id': nodeID,
            "ts": timestamp,
            "h": rxHeader1
        }

        self.bus.publish(n, m, encoding="msgpack")

    def onSpecialMessage(self, channel, data, rssi, pathloss, timestamp, nodeID, rxHeader1):
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
        if self.lock.acquire(1 if message['type'] == 'rt' else 3):
            try:
                self.setChannelKey(message['key'])

                # Normally anything from the gateway has an ID of 1, but sometimes we want local "virtual"
                # devices to talk between gateways.
                id = message.get('localID',1)
                if message['type'] == 'rt':
                    self.sendSG1RT(message['data'], message['pwr'],id)

                elif message['type']=='struct':
                    self.sendSG1Structured(message['data'], message['pwr'],id)
                elif message['type']=='sp':
                    self.sendSG1Special(
                                message['data'], message['pwr'],id)
                elif message['type']=='sg1':
                    self.sendSG1(
                                message['data'], message['pwr'],id)
                else:
                    raise RuntimeError("Invalid type:"+ message['type'])

            finally:
                self.lock.release()

    def sendSG1(self, data, power=0, id=1):
        # 2 reserved bytes
       
        m = bytes([struct.pack("<b",power)[0], self.reqIDCounter, id, 0]) + data
        self._sendMessage(MSG_SEND, m)

    def sendSG1Structured(self, data, power=0, id=1):
        # 2 reserved bytes
      
        m = bytes([struct.pack("<b",power)[0], self.reqIDCounter, id, 0]) + data
        self._sendMessage(MSG_SEND_STRUCTURED, m)

    def sendSG1Special(self, data, power=0,id=1):
        
      
        # 2 reserved bytes
        m = bytes([struct.pack("<b",power)[0], self.reqIDCounter, id, 0]) + data

        self._sendMessage(MSG_SENDSPECIAL, m)


    def sendSG1RT(self, data, power=0,id=1):
        # 3 reserved bytes
        m = bytes([struct.pack("<b",power)[0], id, 0, 0]) + data
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
            # Wait till we can actually open a connection
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
                if time.monotonic()-self.lastPrintedErr>10:
                    print("Ratelimited Message:\n"+traceback.format_exc())
                    self.lastPrintedErr=time.monotonic()
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
        # Average, min, max
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
        # logger.info("pkt:" +str(cmd)+"  "+str(data))
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


            self.onMessage(channel, data, rssi, pathLoss,
                           timestamp, nodeID, rxHeader1)


        elif cmd == MSG_DECODEDSTRUCTURED:
            pathLoss = struct.unpack("<b", data[:1])[0]
            rssi = struct.unpack("<b", data[1:2])[0]
            rxiv = data[2:10]
            rxHeader1 = data[10]
            reserved = data[11:14]
            channel = data[14:46]
            data = data[46:]

            timestamp = struct.unpack("<Q", rxiv)[0]
            nodeID = rxiv[0]

            self.onMessage(channel, data, rssi, pathLoss,
                           timestamp, nodeID, rxHeader1)


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


            #No longer support user level reliable messages
            self.onSpecialMessage(channel, data, rssi,
                                  pathLoss, timestamp, nodeID, rxHeader1)



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
        else:
            #Distinguis bitrates from profile numbers
            if profile> 100:
                raise ValueError("Bad profile value")
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
