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
import traceback
import os
from scullery import messagebus
from scullery import jacktools

# Used by other stuff, yes this really is supposed to be there
# as defensive fallback
from scullery.jacktools import *

from scullery.jacktools import Airwire, get_ports

from scullery import messagebus 

def exit(*a,**k):
    jacktools.stop_managing()

messagebus.subscribe('/system/shutdown', exit)


__doc__ = ""


def onFail():
    messagebus.post_message("/system/notifications/errors", "JACK server has failed")


def onStart():
    messagebus.post_message("/system/notifications/important", "JACK server connected")
    messagebus.post_message("/system/sound/jackstart", "JACK server connected")


jacktools.on_jack_failure = onFail
jacktools.on_jack_start = onStart


def checkIfProcessRunning(processName):
    """
    Check if there is any running process that contains the given name processName, but only if it is OUR process
    """
    try:
        import psutil
    except Exception:
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


try:
    jacktools.start_managing()
except Exception:
    messagebus.post_message(
        "/system/notifications/errors",
        "Failed to launch JACK integration. Maybe JACK is not installed\n"
        + traceback.format_exc(),
    )
