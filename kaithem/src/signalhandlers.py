import os
import signal
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
    import cherrypy
    import tornado

    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.add_callback(ioloop.stop)
    cherrypy.bus.exit()


signal.signal(signal.SIGQUIT, sigquit)
signal.signal(signal.SIGUSR1, dumpThreads)


def stop(*args):
    import cherrypy

    icemedia.sound_player.stop_all_sounds()
    messagebus.post_message("/system/notifications/shutdown", "Recieved SIGINT or SIGTERM.")
    messagebus.post_message("/system/shutdown", "Recieved SIGINT or SIGTERM.")

    import tornado

    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.add_callback(ioloop.stop)
    cherrypy.engine.exit()


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
