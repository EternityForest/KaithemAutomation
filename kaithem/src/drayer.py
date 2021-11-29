# This file deals with all hardline and drayer related features.

#Note that we do not handle actually setting up a drayer server.  There is no separate drayer server, it is a web socket API managed by the main cherrypy



import os
import threading
import logging


def loadDrayerSetup():
    def f():
        try:
            import hardline

            from . import config
            hardline.setP2PPort(config.config['drayer-p2p-port'])
            # Ensure stopped
            hardline.stop()

            #Start at the standard port on localhost.  This doesn't need to be configured,
            #If there is a system instance running we just won't start the local port part and use theirs.
            hardline.start(7009)
            # Unload them at exit
            for i in hardline.loadedServices:
                hardline.loadedServices[i].close()
        except:
            logging.exception("Fail to lauuch Hardline/Drayer")
            from src import messagebus
            messagebus.postMessage("/system/notifications/errors/","Error loading DrayerDB/HardlineP2P, these features are disabled.")
    t = threading.Thread(target=f, daemon=True)
    t.start()

