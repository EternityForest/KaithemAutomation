import os
import signal
import threading
import time
import traceback

import icemedia.sound_player
from scullery import messagebus


def dumpThreads(*a):
    from . import pages

    try:
        n = "/dev/shm/kaithemExitThreadsDump." + str(time.time()) + ".html"
        with open(n, "w") as f:
            f.write(pages.get_template("settings/threads.html").render())
        os.chmod(n, 0o600)
    except Exception:
        print(traceback.format_exc())


def sigquit(*a):
    from . import pages

    try:
        n = "/dev/shm/kaithemExitThreadsDump." + str(time.time()) + ".html"
        with open(n, "w") as f:
            f.write(pages.get_template("settings/threads.html").render())
        os.chmod(n, 0o600)

    except Exception:
        raise


signal.signal(signal.SIGQUIT, sigquit)
signal.signal(signal.SIGUSR1, dumpThreads)


def stop(*args):
    threading.Thread(
        target=icemedia.sound_player.stop_all_sounds, daemon=True
    ).start()
    messagebus.post_message(
        "/system/notifications/shutdown", "Recieved SIGINT or SIGTERM."
    )
    messagebus.post_message("/system/shutdown", "Recieved SIGINT or SIGTERM.")


# signal.signal(signal.SIGINT, stop)
# Called by asyncio
# signal.signal(signal.SIGTERM, stop)
