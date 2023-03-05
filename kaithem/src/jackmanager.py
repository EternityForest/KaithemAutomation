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


def onFail():
    messagebus.postMessage("/system/notifications/errors",
                           "JACK server has failed")


def onStart():
    messagebus.postMessage(
        "/system/notifications/important", "JACK server connected")
    messagebus.postMessage("/system/sound/jackstart", "JACK server connected")


scullery.jacktools.onJackFailure = onFail
scullery.jacktools.onJackStart = onStart



def checkIfProcessRunning(processName):
    '''
    Check if there is any running process that contains the given name processName, but only if it is OUR process
    '''
    try:
        import psutil
    except:
        return False

    # Iterate over the all the running process
    for proc in psutil.process_iter():
        try:
            # Check if process name contains the given name string.
            if processName.lower() in proc.name().lower():
                if proc.uids()[0] == os.geteuid():
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False


pipewireprocess1 = None
pipewireprocess2 = None

jackWasRuning = [0]

# Assume pipewire is good enough to be jack
if checkIfProcessRunning("pipewire"):
    messagebus.postMessage("/system/jack/started", "Actually, it's pipewire")


def reloadSettings():
    global pipewireprocess1, pipewireprocess2

    # Let pipewire do it all for us!!
    scullery.jacktools.useAdditionalSoundcards = "no"
    scullery.jacktools.usePulse = True
    scullery.jacktools.dummy = False

    scullery.jacktools.manageJackProcess = False

    if checkIfProcessRunning("jackd"):
        messagebus.postMessage("/system/jack/started", "External JACK")
        jackWasRuning[0] = 1

    elif checkIfProcessRunning("pipewire"):
        messagebus.postMessage("/system/jack/started", "External JACK")
        jackWasRuning[0] = 1


scullery.jacktools.settingsReloader = reloadSettings

reloadSettings()
