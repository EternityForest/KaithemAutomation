from src import util, alerts, scheduling, tagpoints, messagebus
import subprocess
import logging


undervoltageDuringBootPosted = False
overTempDuringBootPosted = False

# Every minute, we check for overtemperature or overvoltage problems
if util.which("vcgencmd"):
    undervoltageAlert = alerts.Alert(
        priority='warning', name="PiUndervoltageAlert", autoAck=False)
    tempAlert = alerts.Alert(
        priority='error', name="PiTemperatureAlert", autoAck=False)

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
                    messagebus.postMessage("/system/notifications/errors",
                                           description="A low input voltage condition has occurred at some point on this system")
                    undervoltageDuringBootPosted = True

            if x & (2**19):
                if not overTempDuringBootPosted:
                    messagebus.postMessage("/system/notifications/errors",
                                           description="An overtemperature condition has occurred at some point on this system")
                    overTempDuringBootPosted = True

        except Exception:
            logging.exception("err")
    checkPiFlags()
