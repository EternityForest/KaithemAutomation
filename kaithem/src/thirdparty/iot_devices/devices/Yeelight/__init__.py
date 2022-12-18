#Plugin that manages YeeLight devices.

import os, mako, time, threading, logging, random, weakref, traceback

from yeelight import discover_bulbs

import iot_devices.device

import colorzero

logger = logging.Logger("plugins.yeelight")

from mako.lookup import TemplateLookup
templateGetter = TemplateLookup(os.path.dirname(__file__))

import yeelight

lookup = {}

lastRefreshed = 0

lock = threading.Lock()


def maybeRefresh(t=30):
    global lastRefreshed
    if lastRefreshed < time.time() - t:
        refresh()
    elif lastRefreshed < time.time() - 5:
        refresh(3)


def refresh(timeout=8):
    global lastRefreshed, lookup
    from yeelight import discover_bulbs
    lastRefreshed = time.time()

    d = discover_bulbs()
    l = {}

    for i in d:
        if 'name' in i['capabilities']:
            l[i['capabilities']['name']] = i
        l[i['ip']] = i
    lookup = l


def isIp(x):
    x = x.strip().split('.')
    try:
        x = [int(i) for i in x]
        if len(x) == 4:
            return True
    except:
        return False


def getDevice(locator, timeout=10, klass=None):
    """Since plugs can change name, you should't keep a reference
    to a plug for too long. Instead use this function.
    """
    global lookup
    if not isIp(locator):
        if locator in lookup:
            return lookup[locator]

        maybeRefresh()
        if locator in lookup:
            return lookup[locator]

    return klass(locator)


def makeFlusher(wr):
    def f():
        while 1:
            try:
                time.sleep(3)
                d = wr()
                if not d:
                    return
                if d.closed:
                    return
                d.flush()
            except Exception as e:
                print(traceback.format_exc())

    t = threading.Thread(daemon=True, name="YeelightFlusher", target=f)
    t.start()

class YeelightDevice(iot_devices.device.Device):
    def __init__(self, name, data, **kw):
        self.lock = threading.Lock()
        iot_devices.device.Device.__init__(self, name, data, **kw)

        self.numeric_data_point("rssi",writable=False)
        self.set_alarm("Low Signal", 'rssi', "value < -90")

        self.rssiCacheTime = 0
        self.lastLoggedUnreachable = 0

    def getRawDevice(self):
        return getDevice(self.data.get("device.locator"), 3, self.kdClass)

    def rssi(self, cacheFor=120, timeout=3):
        "These bulbs don't have RSSI that i found, instead we just detect reachability or not"
        with self.lock:
            "Returns the current RSSI value of the device"
            if time.monotonic() - self.rssiCacheTime < cacheFor:
                return self.datapoints['rssi'] or -75

            #Not ideal, but we really can't be retrying this too often.
            #if it's disconnected. Way too much slowdown
            self.rssiCacheTime = time.monotonic()

            try:
                info = getDevice(self.data.get("device.locator"), timeout,
                                 self.kdClass).get_properties()

                self.set_data_point("rssi", -70)
            except Exception:
                self.set_data_point("rssi", -180)
                if self.lastLoggedUnreachable < time.monotonic() - 30:
                    self.handleError("Device was unreachable")
                    self.lastLoggedUnreachable = time.monotonic()
                raise

            return self.datapoints['rssi'] or -75


class YeelightRGB(YeelightDevice):
    device_type = "YeelightRGB"
    kdClass = yeelight.Bulb
    descriptors = {
        "kaithem.device.hsv": 1,
        "kaithem.device.powerswitch": 1,
    }



    def flush(self):
        if not self.hasData:
            return
        
        # Rate limits will prevent getting rejected
        self.allowedOperations= min(self.allowedOperations+(time.monotonic()-self.lastRecalcedAllowed),40)
        self.lastRecalcedAllowed=time.monotonic()


        # Drop frames randomly. This will look a lot better with flickery type effects.
        if (random.random()*20 + 1) > self.allowedOperations:
            return

        self.allowedOperations-=1
        self.hasData = False


        color = colorzero.Color(self.datapoints['color'] or 'white')
        rgb = color.rgb

        # Very crappy color correction done by trial and error
        hsv = colorzero.Color.from_rgb(rgb[0], max(0, rgb[1] - rgb[0]*0.1),  max(0, rgb[2] - rgb[0]*0.1)).hsv

        duration = self.datapoints['fade'] or 0


        if hsv.v < 0.0001:
            self.wasOff = True
            self.setSwitch(0, False, duration)
        else:
            try:
                self.getRawDevice().set_hsv(
                    int(hsv.h* 359.9),
                    int(hsv.s *100),
                    int(hsv.v * 100),
                    effect="smooth" if duration else 'sudden',
                    duration=int(duration * 1000) if not self.wasOff else 0)
            except Exception:
                # Assume turned off.  Turn on. Retry.
                self.setSwitch(0, True, duration)
                self.getRawDevice().set_hsv(
                    int(hsv.h* 359.9),
                    int(hsv.s *100),
                    int(hsv.v * 100),
                    effect="smooth" if duration else 'sudden',
                    duration=int(duration * 1000) if not self.wasOff else 0)


            if self.wasOff:
                self.wasOff = False
                self.setSwitch(0, True, duration)

    def close(self):
        return super().close()
        self.closed = True

    def __init__(self, name, data):
        YeelightDevice.__init__(self, name, data)
        self.closed=False
        self.lastHueChange = time.monotonic()

        self.allowedOperations = 60
        self.lastRecalcedAllowed = time.monotonic()

        # Has color data to flush
        self.hasData=False

        def swhandle(v,t,a):
            try:
                self.setSwitch(0, v >= 0.5)
            except:
                pass

        self.numeric_data_point("switch",
                                min=0,
                                max=1,
                                subtype='bool',
                                interval=300, handler=swhandle)
        self.numeric_data_point("fade", min=0, max=10, subtype="light_fade_duration")

        self.huesat = -1
        self.lastVal = -1
        self.wasOff = True
        self.oldTransitionRate = -1

        def colorhandle(v,t,a):
            self.hasData=True
            self.flush()

        self.string_data_point("color", subtype="color", handler=colorhandle)

        makeFlusher(weakref.ref(self))



    def getSwitch(self, channel, state):
        if channel > 0:
            raise ValueError("Bulb has 1 master power channel only")
        return self.getRawDevice().is_on

    def setSwitch(self, channel, state, duration=1):
        logger.debug("Setting smartplug " + self.data.get("device.locator") +
                     "to state " + str(state))
        self.set_data_point('fade', duration)
        self.set_data_point('switch', 1 if state else 0 )

        duration = self.datapoints['fade'] or 0

        with self.lock:
            "Set the state of switch channel N"
            if channel > 0:
                raise ValueError("This is a 1 channel device")
            try:
                if state:
                    getDevice(self.data.get("device.locator"), 3,
                              self.kdClass).turn_on(effect="smooth",
                                                    duration=int(duration *
                                                                 1000))
                    self.wasOff = False
                else:
                    getDevice(self.data.get("device.locator"), 3,
                              self.kdClass).turn_off(effect="smooth",
                                                     duration=int(duration *
                                                                  1000))
                    self.wasOff = True
                self.oldTransitionRate = duration
            except:
                if self.lastLoggedUnreachable < time.monotonic() - 30:
                    self.handleError("Device was unreachable")
                    self.lastLoggedUnreachable = time.monotonic()
                self.set_data_point("rssi", -180)
                raise

            self.set_data_point("rssi", -75)

    def setHSV(self, channel, hue, sat, val, duration=1):
        if channel > 0:
            raise ValueError("Bulb has 1 color only")
        self.set_data_point("fade", duration)
        self.set_data_point('color',
                            colorzero.Color.from_hsv(hue / 360, sat, val).html)


    @classmethod
    def discover_devices(cls, config= {},current_device=None, intent=None, **kw):
        global lookup
        maybeRefresh()
        l = {}
        for i in lookup:
            config2 = config.copy()

            config2.update(
                {
                    'type': cls.device_type,
                    'device.locator': lookup[i]['capabilities'].get("name",'') or lookup[i]['ip']
                }
            )

            l[lookup[i]['capabilities'].get("name",'') or lookup[i]['ip']] = config2

        return l


    def getManagementForm(self):
        return templateGetter.get_template("bulbpage.html").render(
            data=self.data, obj=self)

