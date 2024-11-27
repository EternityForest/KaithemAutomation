import logging
import os
import random
import subprocess
import threading

from scullery import scheduling, workers

from kaithem.src import alerts, messagebus, tagpoints, util

from . import log_environment

t = threading.Thread(target=log_environment.go, daemon=True)
t.start()

undervoltageDuringBootPosted = False
overTempDuringBootPosted = False
battery = None


def getSDHealth():
    import json
    import os

    p = None
    if util.which("sdmon"):
        if os.path.exists("/dev/mmcblk0"):
            try:
                # Requires passwordless sudo.
                # Eventually we need a better solution.
                # TODO fix passwordless sudo requirement
                p = subprocess.check_output(
                    "sudo sdmon /dev/mmcblk0 -a", shell=True
                )
            except Exception:
                logging.exception("Failed to get SD health status")
                messagebus.post_message(
                    "/system/notifications/warnings",
                    "Sdmon is installed, but failed to get SD card health status. Probably an unsupported card ormissing passwordless sudo",
                )
                return None
    if p:
        try:
            d = json.load(p)
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
    logging.exception("Cant load psutil")
    psutil = None

if battery:
    batteryTag = tagpoints.Tag("/system/power/battery_level")
    batteryTag.value = battery.percent
    batteryTag.unit = "%"
    batteryTag.min = 0
    batteryTag.max = 100
    batteryTag.lo = 25
    batteryTag.expose("view_status")

    battery_time = tagpoints.Tag("/system/power/battery_time")
    battery_time.unit = "s"
    battery_time.max = 30 * 60 * 60
    battery_time.lo = 40 * 60
    battery_time.value = battery.secsleft if battery.secsleft > 0 else 9999999
    battery_time.set_alarm(
        "lowbattery_timeRemaining", "value < 60*15", priority="error"
    )
    battery_time.expose("view_status")

    acPowerTag = tagpoints.Tag("/system/power/charging")
    acPowerTag.value = battery.power_plugged or 0
    acPowerTag.subtype = "bool"
    acPowerTag.set_alarm(
        "runningOnBattery",
        "(not value) and (tv('/system/power/battery_level')< 80)",
        priority="warning",
    )
    acPowerTag.expose("view_status")


sdhealth = getSDHealth()


# EmberOS has the service needed to make this work
if sdhealth is not None:
    sdTag = tagpoints.Tag("/system/sdcard.health")
    sdTag.min = 0
    sdTag.max = 100
    sdTag.unit = "%"
    sdTag.lo = 50
    sdTag.expose("view_status")

    sdTag.set_alarm("SDCardWear", "value < 70", priority="info")
    sdTag.set_alarm("SDCardCloseToFailure", "value < 10", priority="error")
    sdTag.value = sdhealth

    @scheduling.scheduler.every_hour
    def doSD():
        s = getSDHealth()
        if s is not None:
            sdTag.value = s


diskAlerts = {}

spaceCheckLock = threading.RLock()

if psutil:

    @scheduling.scheduler.every_hour
    def doDiskSpaceCheck():
        with spaceCheckLock:
            import psutil

            partitions = psutil.disk_partitions(all=True)
            found = {}

            for p in partitions:
                if p.device.startswith("/dev") or p.device == "tmpfs":
                    if "rw" in p.opts.split(","):
                        id = p.device + " at " + p.mountpoint
                        found[id] = True

                        if id not in diskAlerts:
                            diskAlerts[id] = alerts.Alert(
                                "Low remaining space on " + id,
                                priority="warning",
                                description="This alert may take a while to go away once the root cause is fixed.",
                            )
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
                if i not in found:
                    diskAlerts[i].release()
                    del diskAlerts[i]

    doDiskSpaceCheck()

    tempTags = {}

    @scheduling.scheduler.every_minute
    def doPsutil():
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

            if i not in tempTags:
                # Fix the name
                tempTags[i] = tagpoints.Tag(
                    tagpoints.normalize_tag_name(
                        "/system/sensors/temp/" + i, "_"
                    )
                )
                tempTags[i].set_alarm(
                    "temperature",
                    "value>78",
                    release_condition="value<65",
                    priority="warning",
                )
                tempTags[i].set_alarm("lowtemperature", "value<5")
                tempTags[i].expose("view_status")

                tempTags[i].unit = "degC"
                tempTags[i].max = 150
                tempTags[i].min = -25
                tempTags[i].hi = 76
                tempTags[i].lo = -5
            tempTags[i].value = peak

        battery = psutil.sensors_battery()
        if battery:
            acPowerTag.value = battery.power_plugged or 0
            batteryTag.value = battery.percent
            battery_time.value = (
                battery.secsleft if battery.secsleft > 0 else 9999999
            )

    doPsutil()


# Every minute, we check for overtemperature or overvoltage problems
if util.which("vcgencmd"):
    undervoltageTag = tagpoints.Tag("/system/pi/undervoltage")
    undervoltageTag.set_alarm("undervoltage", "value>0.5")
    undervoltageTag.expose("view_status")

    undervoltageTagClaim = undervoltageTag.claim(0, "HWSensor")

    overtemperatureTag = tagpoints.Tag("/system/pi/overtemperature")
    overtemperatureTag.set_alarm("temp", "value>0.5", priority="error")
    overtemperatureTag.expose("view_status")

    overtemperatureTagClaim = overtemperatureTag.claim(0, "HWSensor")

    @scheduling.scheduler.every_minute
    def checkPiFlags():
        global undervoltageDuringBootPosted
        global overTempDuringBootPosted
        try:
            # This is a trusted system util! Eval is fine here!
            x = subprocess.check_output(["vcgencmd", "get_throttled"])
            x = eval(x.decode("utf8").split("=")[1])

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
                        "/system/notifications/errors",
                        "A low input voltage condition has occurred at some point on this system",
                    )
                    undervoltageDuringBootPosted = True

            if x & (2**19):
                if not overTempDuringBootPosted:
                    messagebus.post_message(
                        "/system/notifications/errors",
                        "An overtemperature condition has occurred at some point on this system",
                    )
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

            os.system('sudo bash -c  "echo ' + str(v) + " > " + f + '"')

        refs.append(setLedWithSudo)

        with open(f) as f2:
            ledDefaults[n] = f2.read()
        t = tagpoints.Tag(n)
        t.expose("view_status")

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
    "/sys/class/leds/led1/brightness", "/system/board/leds/pwr"
)
makeLedTagIfNonexistant(
    "/sys/class/leds/PWR/brightness", "/system/board/leds/pwr"
)

makeLedTagIfNonexistant(
    "/sys/class/leds/led0/brightness", "/system/board/leds/act"
)
makeLedTagIfNonexistant(
    "/sys/class/leds/ACT/brightness", "/system/board/leds/act"
)


errtag = tagpoints.Tag("/system/io_error_flag")
errtag.set_alarm(
    "An IO Error was detected that could indicate a failing disk or bad cable. This could also indicate an issue with an external device.",
    "value>0",
    "error",
)
errtag.min = 0
errtag.max = 1
errtag.subtype = "bool"
errtag.expose("view_status")

first_j = [True]


@scheduling.scheduler.every_hour
def checkDmesg():
    if first_j[0]:
        first_j[0] = False
        t = subprocess.check_output(
            ["journalctl", "-k", "--no-pager", "-p", "4"]
        ).decode()
    else:
        t = subprocess.check_output(
            ["journalctl", "-k", "--no-pager", "-e", "-p", "4"]
        ).decode()
    if "i/o error" in t.lower():
        errtag.value = 1


workers.do(checkDmesg)

ram_alert = alerts.Alert(
    "Bitflip Error Detected",
    priority="error",
    description="The server may have a bad RAM module",
)

# Allocate random chunks of memory, try to detect bit errors.
# We expect this to fire about once a year on normal systems.
# Randomize size so it can fit in fragmented places for max coverage, if ran for a very long time.
ramTestData = b""
lastRamTestValue = 0
bitErrorTestLock = threading.Lock()


@scheduling.scheduler.every_hour
def checkBitErrors():
    global ramTestData, lastRamTestValue
    with bitErrorTestLock:
        if not lastRamTestValue:
            for i in ramTestData:
                if not i == 0:
                    ram_alert.trip()
                    messagebus.post_message(
                        "/system/notifications/errors",
                        f"RAM Bitflip 0>1 detected: val{str(i)}",
                    )

            ramTestData = b"\xff" * int(1024 * 2048 * random.random())
            lastRamTestValue = 255

        else:
            for i in ramTestData:
                if not i == 255:
                    ram_alert.trip()
                    messagebus.post_message(
                        "/system/notifications/errors",
                        f"RAM Bitflip 1>0 detected: val{str(i)}",
                    )

            ramTestData = b"\0" * int(1024 * 2048 * random.random())
            lastRamTestValue = 0
