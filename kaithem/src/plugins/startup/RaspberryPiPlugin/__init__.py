from src import util, alerts, scheduling
import subprocess,logging

#Every minute, we check for overtemperature or overvoltage problems
if util.which("vcgencmd"):
    undervoltageAlert = alerts.Alert(priority='warning', name="PiUndervoltageAlert", autoAck=False)
    tempAlert = alerts.Alert(priority='error', name="PiTemperatureAlert", autoAck=False)

    @scheduling.scheduler.everyMinute
    def checkPiFlags():
        try:
            #This is a trusted system util! 
            x = subprocess.check_output(["vcgencmd", "get_throttled"])
            x = eval(x.decode('utf8').split("=")[1])

            #https://github.com/raspberrypi/documentation/blob/JamesH65-patch-vcgencmd-vcdbg-docs/raspbian/applications/vcgencmd.md
            if x&(2**0):
                undervoltageAlert.trip()
            else:
                undervoltageAlert.clear()

            if x&(2**3):
                tempAlert.trip()
            else:
                tempAlert.clear()
        except:
            logging.exception("err")
    checkPiFlags()