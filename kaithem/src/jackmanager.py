#Copyright Daniel Dunn 2019
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.
__doc__=''

#This is an acceptable dependamcy, it will be part of libkaithem if such a thing exists
from scullery import jack
from scullery import messagebus
from scullery.jack import *
import scullery

from . import persist,directories
settingsFile = os.path.join(directories.vardir, "system.mixer", "jacksettings.yaml")


legacy_keys ={
   "usbPeriodSize":"/system/sound/jackusbperiod",
   "usbLatency":"/system/sound/jackusblatency",
   "jackPeriodSize":"/system/sound/jackperiodsize",
   "jackPeriods":"/system/sound/jackperiods"

}

default={
    "usbPeriodSize": -1,
    "usbPeriods": -1,

    "usbLatency": -1,
    "jackPeriods": 3,
    "jackPeriodSize": 512,
    "usbQuality": 0,
    "jackMode": "off",
}

def onFail():
    messagebus.postMessage("/system/notifications/errors","JACK server has failed")

def onStart():
    messagebus.postMessage("/system/notifications/important","JACK server connected")
    messagebus.postMessage("/system/sound/jackstart","JACK server connected")

scullery.jack.onJackFailure = onFail
scullery.jack.onJackStart = onStart


settings = persist.getStateFile(settingsFile,default,legacy_keys)

settingsFile = os.path.join(directories.vardir, "system.mixer", "jacksettings.yaml")
settings = persist.getStateFile(settingsFile)



def reloadSettings():
    scullery.jack.usbPeriodSize = settings.get("usbPeriodSize",-1)
    scullery.jack.usbLatency = settings.get("usbLatency",-1)
    scullery.jack.usbPeriods = settings.get("usbPeriods",-1)
    scullery.jack.usbQuality = settings.get("usbQuality",0)

    scullery.jack.periodSize = settings.get("jackPeriodSize",512)
    scullery.jack.jackPeriods = max(settings.get("jackPeriods",3),3)
    scullery.jack.sharePulse = settings.get("sharePulse",None)
    scullery.jack.jackDevice = settings.get("jackDevice","hw:0,0")

    scullery.jack.useAdditionalSoundcards = settings.get("useAdditionalSoundcards","yes")


    scullery.jack.usePulse = settings.get("sharePulse",None) != "disable"

    if settings.get("jackMode",None)=="use":
        scullery.jack.manageJackProcess=False
    if settings.get("jackMode",None)=="manage":
         scullery.jack.manageJackProcess=True


    

scullery.jack.settingsReloader= reloadSettings

reloadSettings()