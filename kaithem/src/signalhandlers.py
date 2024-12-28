import os
import signal
import time
import traceback

from . import shutdown


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
    shutdown.shutdown()


# signal.signal(signal.SIGINT, stop)
# Called by asyncio
# signal.signal(signal.SIGTERM, stop)
