from . import messagebus
import os
import importlib
import traceback
import logging
from . import pathsetup

logger = logging.getLogger("system")
logger.setLevel(logging.INFO)

plugins = {}

def load_plugins():
    try:
        for i in os.listdir(pathsetup.startupPluginsPath):
            try:
                plugins[i] = importlib.import_module(i)
                logger.info("Loaded plugin " + i)
            except Exception:
                logger.exception("Error loading plugin " + i)
                messagebus.post_message(
                    "/system/notifications/errors",
                    "Error loading plugin " + i + "\n" + traceback.format_exc(),
                )
    except Exception:
        messagebus.post_message("/system/notifications/errors", "Error loading plugins")
        logger.exception("Error loading plugins")
