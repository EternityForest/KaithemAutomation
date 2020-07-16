from src import util, alerts, scheduling, tagpoints, messagebus
import subprocess
import logging


undervoltageDuringBootPosted = False
overTempDuringBootPosted = False
try:
    import psutil
    psutil.sensors_temperatures()
    battery = psutil.sensors_battery()

    if battery:
        batteryTag = tagpoints.Tag("/system/power/batteryLevel")
        batteryTag.value=battery.percent
        batteryTag.unit="%"
        batteryTag.min=0
        batteryTag.max=100
        batteryTag.lo= 25

        batteryTime = tagpoints.Tag("/system/power/batteryTime")
        batteryTime.unit = 's'
        batteryTime.max=30*60*60
        batteryTime.lo = 40*60
        batteryTime.value = battery.secsleft if battery.secsleft > 0 else 9999999
        batteryTime.setAlarm("lowBatteryTimeRemaining", "value < 60*15")


        acPowerTag = tagpoints.Tag("/system/power/charging")
        acPowerTag.value=battery.power_plugged
        acPowerTag.setAlarm("runningOnBattery", "(not value) and (tv('/system/power/batteryLevel')< 80)", priority='info')



except ImportError:
    psutil=None

if psutil:
    tempTags = {}
    @scheduling.scheduler.everyMinute
    def doPsutil():
        temps = {}
        t= psutil.sensors_temperatures()
        for i in t:
            peak = 0
            negpeak = 100
            for j in t[i]:
                peak =  max(peak,j.current)
                negpeak =  min(peak,j.current)
            
            #If it is very cold we can report that too, basically we want to detect whatever the main problem is
            #But anything under -50 is probably a placeholder value
            if negpeak<0 and negpeak > -50:
                peak=negpeak

            if not i in tempTags:
                #Fix the name
                tempTags[i] = tagpoints.Tag(tagpoints.normalizeTagName("/system/sensors/temp/"+i,"_"))
                tempTags[i].setAlarm("temperature", "value>85")
                tempTags[i].unit='degC'
                tempTags[i].max = 150
                tempTags[i].min= -25
                tempTags[i].hi = 80
                tempTags[i].lo = -5
            tempTags[i].value= peak

        battery=psutil.sensors_battery()
        if battery:
            acPowerTag.value = battery.power_plugged
            batteryTag.value = battery.percent
            batteryTime.value = battery.secsleft if battery.secsleft > 0 else 9999999
    doPsutil()
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
                    messagebus.postMessage("/system/notifications/errors","A low input voltage condition has occurred at some point on this system")
                    undervoltageDuringBootPosted = True

            if x & (2**19):
                if not overTempDuringBootPosted:
                    messagebus.postMessage("/system/notifications/errors","An overtemperature condition has occurred at some point on this system")
                    overTempDuringBootPosted = True

        except Exception:
            logging.exception("err")
    checkPiFlags()
