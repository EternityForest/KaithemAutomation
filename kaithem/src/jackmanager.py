# Copyright Daniel Dunn 2019
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.
import scullery
import os
from scullery.jacktools import *
from scullery import messagebus
from scullery import jacktools
__doc__ = ''

# This is an acceptable dependamcy, it will be part of libkaithem if such a thing exists

from . import persist, directories
settingsFile = os.path.join(
    directories.vardir, "system.mixer", "jacksettings.yaml")


legacy_keys = {
    "usbPeriodSize": "/system/sound/jackusbperiod",
    "usbLatency": "/system/sound/jackusblatency",
    "jackPeriodSize": "/system/sound/jackperiodsize",
    "jackPeriods": "/system/sound/jackperiods"

}

default = {
    "usbPeriodSize": 2048,
    "usbPeriods": 3,
    "usbLatency": -1,
    "jackPeriods": 3,
    "jackPeriodSize": 512,
    "usbQuality": 0,
    "jackMode": "off",
}


def onFail():
    messagebus.postMessage("/system/notifications/errors",
                           "JACK server has failed")


def onStart():
    messagebus.postMessage(
        "/system/notifications/important", "JACK server connected")
    messagebus.postMessage("/system/sound/jackstart", "JACK server connected")


scullery.jacktools.onJackFailure = onFail
scullery.jacktools.onJackStart = onStart


settings = persist.getStateFile(settingsFile, default, legacy_keys)

settingsFile = os.path.join(
    directories.vardir, "system.mixer", "jacksettings.yaml")
settings = persist.getStateFile(settingsFile)


def checkIfProcessRunning(processName):
    '''
    Check if there is any running process that contains the given name processName.
    '''
    try:
        import psutil
    except:
        return False

    #Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            # Check if process name contains the given name string.
            if processName.lower() in proc.name().lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False;


def reloadSettings():
    scullery.jacktools.usbPeriodSize = settings.get("usbPeriodSize", -1)
    scullery.jacktools.usbLatency = settings.get("usbLatency", -1)
    scullery.jacktools.usbPeriods = settings.get("usbPeriods", -1)
    scullery.jacktools.usbQuality = settings.get("usbQuality", 0)

    scullery.jacktools.periodSize = settings.get("jackPeriodSize", 512)
    scullery.jacktools.jackPeriods = max(settings.get("jackPeriods", 3), 3)
    scullery.jacktools.sharePulse = settings.get("sharePulse", None)
    scullery.jacktools.jackDevice = settings.get("jackDevice", "hw:0,0")


    if not checkIfProcessRunning("pipewire"):
        scullery.jacktools.useAdditionalSoundcards = settings.get(
            "useAdditionalSoundcards", "yes")
    else:
        #Let pipewire do it all for us!!
        scullery.jacktools.useAdditionalSoundcards = "no"

    scullery.jacktools.usePulse = settings.get("sharePulse", None) != "disable"

    scullery.jacktools.dummy=False

    if checkIfProcessRunning("pipewire") or settings.get("jackMode", None) == "use":
        scullery.jacktools.manageJackProcess = False
    elif settings.get("jackMode", None) == "manage":
        scullery.jacktools.manageJackProcess = True
    elif settings.get("jackMode", None) == "dummy":
        scullery.jacktools.manageJackProcess = True
        scullery.jacktools.dummy=True
    


scullery.jacktools.settingsReloader = reloadSettings

reloadSettings()
