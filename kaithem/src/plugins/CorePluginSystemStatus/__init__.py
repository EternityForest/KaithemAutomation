import logging
import os
import random
import re
import subprocess
import threading
import time

from scullery import scheduling, workers

from kaithem.src import alerts, messagebus, tagpoints, util

from . import log_environment

t = threading.Thread(target=log_environment.go, daemon=True)
t.start()

battery = None


ports_ever_seen: dict[str, bool] = {}


def getConnectedDisplays():
    """Return the status of the display ports."""
    # format
    # Connector 0 (32) HDMI-A-1 (connected)
    # Encoder 0 (31) TMDS
    # Connector 1 (42) HDMI-A-2 (disconnected)
    # Encoder 1 (41) TMDS
    displays = {}

    if util.which("kmsprint"):
        data = subprocess.check_output("kmsprint", shell=True)
        for line in data.splitlines():
            match = re.search(
                r"Connector \d+ \((\d+)\) (.+) \((connected|disconnected)\)",
                line.decode("utf-8"),
            )
            if match:
                _connector_id = match.group(1)
                display_name = match.group(2)
                status = match.group(3) == "connected"
                displays[display_name] = status

    elif util.which("xrandr"):
        data = subprocess.check_output("xrandr", shell=True)
        for line in data.splitlines():
            match = re.search(r"(.+?) connected", line.decode("utf-8"))
            if match:
                display_name = match.group(1)
                displays[display_name] = True

    for i in displays:
        ports_ever_seen[i] = False

    for i in ports_ever_seen:
        if i not in displays:
            displays[i] = False

    return displays


display_tags: dict[str, tagpoints.NumericTagPointClass] = {}


@scheduling.scheduler.every_minute
def displaysToTags():
    displays = getConnectedDisplays()

    for i in displays:
        if i not in display_tags:
            name = (
                i.replace(" ", "_")
                .replace("-", "_")
                .replace(".", "_")
                .replace(":", "_")
                .lower()
            )

            display_tags[i] = tagpoints.Tag(
                "/system/display_ports/" + name + ".connected"
            )
            display_tags[i].expose("view_status")
            display_tags[i].min = 0
            display_tags[i].max = 1
            display_tags[i].subtype = "bool"
            # I think it doesn't need auto ack, to catch transients?
            display_tags[i].set_alarm(
                "disconnected", "value==0", priority="warning"
            )

        # Leave them marked as default till the first time we see them
        # So they don't trigger alarms on headless systems, only alarm
        # When there is a change
        if displays[i] or display_tags[i].timestamp:
            display_tags[i].value = 1 if displays[i] else 0


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
                # Bind mounts making noise
                if os.path.isfile(p.mountpoint):
                    continue

                if p.device.startswith("/dev") or p.device == "tmpfs":
                    if "rw" in p.opts.split(","):
                        id = p.device + " at " + p.mountpoint
                        found[id] = True

                        if id not in diskAlerts:
                            diskAlerts[id] = alerts.Alert(
                                f"Low remaining space on {id} at {p.mountpoint}",
                                priority="warning",
                                description="This alert may take a while to go away once the root cause is fixed.",
                            )
                        try:
                            full = psutil.disk_usage(p.mountpoint).percent
                            space = psutil.disk_usage(p.mountpoint).free
                        except OSError:
                            continue
                        if (full > 91 and space < (10**9 * 20)) or full > 95:
                            diskAlerts[id].trip(f"{full}% full, {space} free")
                        if full < 85:
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


# Human readable descriptions for the cryptic hwmon alarm file names.
# Keys are regexes matched against the alarm file name.
hwmon_alarm_descriptions: dict[str, str] = {
    r"in\d+_lcrit_alarm": "Low voltage on input or rail",
    r"in\d+_crit_alarm": "Input or rail voltage outside critical range",
    r"in\d+_min_alarm": "Input or rail voltage below minimum",
    r"in\d+_max_alarm": "Input or rail voltage above maximum",
    r"temp\d+_crit_alarm": "Temperature exceeded the critical threshold",
    r"temp\d+_max_alarm": "Temperature exceeded the maximum threshold",
    r"temp\d+_emergency_alarm": "Temperature reached the emergency threshold",
    r"fan\d+_alarm": "Cooling fan stopped or running too slowly",
    r"fan\d+_fault": "Cooling fan reported a fault",
    r"curr\d+_crit_alarm": "Current exceeded the critical threshold",
    r"curr\d+_max_alarm": "Current exceeded the maximum threshold",
    r"power\d+_crit_alarm": "Power exceeded the critical threshold",
    r"power\d+_max_alarm": "Power exceeded the maximum threshold",
    r"power\d+_alarm": "Power reading outside the allowed range",
    r"humidity\d+_alarm": "Humidity outside the allowed range",
}


def getHwmonAlarmDescription(alarm_name: str) -> str:
    """Map a cryptic hwmon alarm file name to a human readable description."""
    for pattern, description in hwmon_alarm_descriptions.items():
        if re.match(pattern, alarm_name):
            return description
    return "Hardware alarm condition detected"


hwmon_alarm_tags: dict[str, tagpoints.Tag] = {}
hwmon_alarm_claims: dict[str, tagpoints.Claim] = {}


# Every minute, check every hwmon device for *_alarm flags.
# We name the tag after the hwmon "name" file rather than the path,
# so e.g. /sys/hwmon/coretemp/temp4_crit_alarm
@scheduling.scheduler.every_minute
def checkHwmonAlarms():
    base = "/sys/class/hwmon"
    try:
        entries = os.listdir(base)
    except OSError:
        return

    for entry in entries:
        hwmon_dir = os.path.join(base, entry)
        try:
            with open(os.path.join(hwmon_dir, "name")) as f:
                name = f.read().strip()
        except OSError:
            continue

        if not name:
            continue

        try:
            files = os.listdir(hwmon_dir)
        except OSError:
            continue

        for file in files:
            if not file.endswith("_alarm"):
                continue

            tag_name = tagpoints.normalize_tag_name(
                "/sys/hwmon/" + name + "/" + file, "_"
            )

            # Multiple hwmon devices can share a name, in which case we
            # reuse the existing tag rather than clobbering it.
            if tag_name not in hwmon_alarm_tags:
                tag = tagpoints.Tag(tag_name)
                tag.subtype = "bool"
                tag.min = 0
                tag.max = 1
                tag.set_alarm(file, "value>0.5", priority="warning")
                tag.description = getHwmonAlarmDescription(file)
                tag.expose("view_status")
                hwmon_alarm_tags[tag_name] = tag
                hwmon_alarm_claims[tag_name] = tag.claim(0, "HWSensor")

            try:
                with open(os.path.join(hwmon_dir, file)) as f:
                    value = 1 if f.read().strip() == "1" else 0
                hwmon_alarm_claims[tag_name].set(value)
            except OSError:
                pass


checkHwmonAlarms()


ledDefaults: dict[str, str] = {}

refs = []
ledtags = {}


def makeLedTagIfNonexistant(f, n):
    if n in ledtags:
        return

    if os.path.exists(f):

        def setLed(v, *x):
            if v > 0.5:
                v = 255
            elif v < 0:
                v = ledDefaults[n]
            else:
                v = 0

            os.system('bash -c  "echo ' + str(v) + " > " + f + '"')

        refs.append(setLed)

        with open(f) as f2:
            ledDefaults[n] = f2.read()
        t = tagpoints.Tag(n)
        t.expose("view_status")

        t.default = -1
        t.min = -1
        t.max = 1
        t.subtype = "tristate"
        t.subscribe(setLed)
        ledtags[n] = t


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


def quick_ram_test():
    for i in range(16):
        checkBitErrors()
        time.sleep(1)


workers.do(quick_ram_test)
