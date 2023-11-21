import threading
from kaithem.src import util, alerts, scheduling, tagpoints, messagebus
import subprocess
import logging
import os

undervoltageDuringBootPosted = False
overTempDuringBootPosted = False
battery = None


def getSDHealth():
    import os
    import json

    p = None
    if os.path.exists("/dev/shm/sdmon_cache_mmcblk0"):
        p = "/dev/shm/sdmon_cache_mmcblk0"

    if os.path.exists("/run/sdmon-cache/mmcblk0"):
        p = "/run/sdmon-cache/mmcblk0"

    if p:
        with open(p) as f:
            try:
                d = json.load(f)
            except Exception:
                return None
        if "enduranceRemainLifePercent" in d:
            return d["enduranceRemainLifePercent"]
        elif "healthStatusPercentUsed" in d:
            return 100 - d["healthStatusPercentUsed"]


try:
    import psutil
    psutil.sensors_temperatures()
    battery = psutil.sensors_battery()

except ImportError:
    logging.exception("Cant load psutil, trying plyer instead")
    psutil = None

    try:
        import plyer
    except ImportError:
        print("Plyer not available either")

if battery:
    batteryTag = tagpoints.Tag("/system/power/battery_level")
    batteryTag.value = battery.percent
    batteryTag.unit = "%"
    batteryTag.min = 0
    batteryTag.max = 100
    batteryTag.lo = 25

    battery_time = tagpoints.Tag("/system/power/battery_time")
    battery_time.unit = 's'
    battery_time.max = 30 * 60 * 60
    battery_time.lo = 40 * 60
    battery_time.value = battery.secsleft if battery.secsleft > 0 else 9999999
    battery_time.setAlarm("lowbattery_timeRemaining", "value < 60*15")

    acPowerTag = tagpoints.Tag("/system/power/charging")
    acPowerTag.value = battery.power_plugged or 0
    acPowerTag.subtype = 'bool'
    acPowerTag.setAlarm(
        "runningOnBattery", "(not value) and (tv('/system/power/battery_level')< 80)", priority='info')


sdhealth = getSDHealth()


# EmberOS has the service needed to make this work
if not sdhealth is None:
    sdTag = tagpoints.Tag("/system/sdcard.health")
    sdTag.min = 0
    sdTag.max = 100
    sdTag.unit = "%"
    sdTag.lo = 50

    sdTag.setAlarm("SDCardWear", 'value < 70', priority='info')
    sdTag.setAlarm("SDCardCloseToFailure", 'value < 10', priority='error')
    sdTag.value = sdhealth

    @scheduling.scheduler.everyHour
    def doSD():
        s = getSDHealth()
        if not s is None:
            sdTag.value = s

diskAlerts = {}

spaceCheckLock = threading.RLock()

if psutil:
    @scheduling.scheduler.everyHour
    def doDiskSpaceCheck():
        with spaceCheckLock:
            import psutil
            partitions = psutil.disk_partitions(all=True)
            found = {}

            for p in partitions:
                if p.device.startswith("/dev") or p.device == 'tmpfs':
                    if 'rw' in p.opts.split(","):
                        id = p.device + " at " + p.mountpoint
                        found[id] = True

                        if not id in diskAlerts:
                            diskAlerts[id] = alerts.Alert("Low remaining space on " + id, priority="warning",
                                                          description="This alert may take a while to go away once the root cause is fixed.")
                        try:
                            full = psutil.disk_usage(p.mountpoint).percent
                            space = psutil.disk_usage(p.mountpoint).free
                        except OSError:
                            continue
                        if (full > 90 and space < (10**9 * 50)) or full > 95:
                            diskAlerts[id].trip()
                        if full < 80:
                            diskAlerts[id].release()

            for i in list(diskAlerts.keys()):
                if not i in found:
                    diskAlerts[i].release()
                    del diskAlerts[i]

    doDiskSpaceCheck()

    tempTags = {}

    @scheduling.scheduler.everyMinute
    def doPsutil():
        temps = {}
        t = psutil.sensors_temperatures()
        for i in t:
            peak = 0
            negpeak = 100
            for j in t[i]:
                peak = max(peak, j.current)
                negpeak = min(peak, j.current)

            # If it is very cold we can report that too, basically we want to detect whatever the main problem is
            # But anything under -50 is probably a placeholder value
            if negpeak < 0 and negpeak > -50:
                peak = negpeak

            if not i in tempTags:
                # Fix the name
                tempTags[i] = tagpoints.Tag(
                    tagpoints.normalizeTagName("/system/sensors/temp/" + i, "_"))
                tempTags[i].setAlarm(
                    "temperature", "value>78", releaseCondition="value<65")
                tempTags[i].setAlarm("lowtemperature", "value<5")

                tempTags[i].unit = 'degC'
                tempTags[i].max = 150
                tempTags[i].min = -25
                tempTags[i].hi = 76
                tempTags[i].lo = -5
            tempTags[i].value = peak

        battery = psutil.sensors_battery()
        if battery:
            acPowerTag.value = battery.power_plugged or 0
            batteryTag.value = battery.percent
            battery_time.value = battery.secsleft if battery.secsleft > 0 else 9999999
    doPsutil()


elif plyer:
    from plyer import battery

    @scheduling.scheduler.everyMinute
    def doPlyer():
        if battery:
            acPowerTag.value = battery.status['isCharging']
            batteryTag.value = battery.status['percentage']
            battery_time.value = batteryTag.value = (
                (3 * 3600) * battery.status['percentage']) / 100

    from plyer import flash

    lightTag = tagpoints.Tag(
        tagpoints.normalizeTagName("/system/hw/flashlight"))

    def lightTagHandler(v, t, a):
        if v:
            flash.on()
        else:
            try:
                flash.off()
            except Exception as e:
                print(e)
            flash.release()

    doPlyer()


# Every minute, we check for overtemperature or overvoltage problems
if util.which("vcgencmd"):
    undervoltageTag = tagpoints.Tag("/system/pi/undervoltage")
    undervoltageTag.setAlarm("undervoltage", "value>0.5")
    undervoltageTagClaim = undervoltageTag.claim(0, "HWSensor")

    overtemperatureTag = tagpoints.Tag("/system/pi/overtemperature")
    overtemperatureTag.setAlarm("temp", "value>0.5", priority='error')
    overtemperatureTagClaim = overtemperatureTag.claim(0, "HWSensor")

    @scheduling.scheduler.everyMinute
    def checkPiFlags():
        global undervoltageDuringBootPosted
        global overTempDuringBootPosted
        try:
            # This is a trusted system util! Eval is fine here!
            x = subprocess.check_output(["vcgencmd", "get_throttled"])
            x = eval(x.decode('utf8').split("=")[1])

            # https://github.com/raspberrypi/documentation/blob/JamesH65-patch-vcgencmd-vcdbg-docs/raspbian/applications/vcgencmd.md
            if x & (2**0):
                undervoltageTagClaim.set(1)
            else:
                undervoltageTagClaim.set(0)

            if x & (2**3):
                overtemperatureTagClaim.set(1)
            else:
                overtemperatureTagClaim.set(0)

            # These are persistent flags. We check to see if something happened before Kaithem started,
            # But we don't actually need to do repeatedly spam the message

            if x & (2**16):
                if not undervoltageDuringBootPosted:
                    messagebus.post_message(
                        "/system/notifications/errors", "A low input voltage condition has occurred at some point on this system")
                    undervoltageDuringBootPosted = True

            if x & (2**19):
                if not overTempDuringBootPosted:
                    messagebus.post_message(
                        "/system/notifications/errors", "An overtemperature condition has occurred at some point on this system")
                    overTempDuringBootPosted = True

        except Exception:
            logging.exception("err")
    checkPiFlags()



ledDefaults: dict[str, str] = {}

refs = []
ledtags = {}


def makeLedTagIfNonexistant(f, n):
    if n in ledtags:
        return

    if os.path.exists(f):
        def setLedWithSudo(v, *x):
            if v > 0.5:
                v = 255
            elif v < 0:
                v = ledDefaults[n]
            else:
                v = 0

            os.system('sudo bash -c  "echo ' + str(v) + ' > ' + f + '"')
        refs.append(setLedWithSudo)

        with open(f) as f2:
            ledDefaults[n] = f2.read()
        t = tagpoints.Tag(n)
        t.default = -1
        t.min = -1
        t.max = 1
        t.subtype = "tristate"
        t.subscribe(setLedWithSudo)
        ledtags[n] = t

        try:
            setLedWithSudo(t.value)
        except Exception:
            logging.exception("Error setting up LED state")

makeLedTagIfNonexistant(
    "/sys/class/leds/led1/brightness", "/system/board/leds/pwr")
makeLedTagIfNonexistant("/sys/class/leds/PWR/brightness",
                        "/system/board/leds/pwr")

makeLedTagIfNonexistant(
    "/sys/class/leds/led0/brightness", "/system/board/leds/act")
makeLedTagIfNonexistant("/sys/class/leds/ACT/brightness",
                        "/system/board/leds/act")


errtag = tagpoints.Tag("/system/io_error_flag")
errtag.setAlarm("An IO Error was detected that could indicate a failing disk or bad cable. This could also indicate an issue with an external device.", "value>0", "error")
errtag.min=0
errtag.max=1
errtag.subtype = 'bool'

@scheduling.scheduler.everyHour
def checkDmesg():
    t = subprocess.check_output(['journalctl', '-k']).decode()
    if "i/o error" in t.lower():
        errtag.value = 1

checkDmesg()
