# SPDX-FileCopyrightText: Copyright 2019 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
import os
import traceback

# Used by other stuff, yes this really is supposed to be there
# as defensive fallback
from icemedia.jack_tools import *  # noqa
from icemedia.jack_tools import Airwire, get_ports  # noqa
from scullery import (
    jacktools,  # noqa
    messagebus,  # noqa
)


def exit(*a, **k):
    jacktools.stop_managing()


messagebus.subscribe("/system/shutdown", exit)


__doc__ = ""


def onFail():
    messagebus.post_message(
        "/system/notifications/errors", "JACK server has failed"
    )


def onStart():
    messagebus.post_message(
        "/system/notifications/important", "JACK server connected"
    )
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
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
        ):
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
