# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import weakref
from . import workers
import time
import json
import logging
import cherrypy
import os
import threading
from . import messagebus, pages, auth, widgets, persist, directories, scheduling
from .unitsofmeasure import strftime
from .config import config

mlogger = logging.getLogger("system.msgbuslog")

logger = logging.getLogger("system.notifications")
ilogger = logging.getLogger("system.notifications.important")

notificationslog = []


notificationsfn = os.path.join(
    directories.vardir, "core.settings", "pushnotifications.toml"
)

pushsettings = persist.getStateFile(notificationsfn)


class API(widgets.APIWidget):
    def on_new_subscriber(self, user, cid, **kw):
        self.send(["all", notificationslog])


api = API()
api.require("view_status")


toolbarapi = widgets.APIWidget()
toolbarapi.require("view_status")
toolbarapi.echo = False


def f(u, v, id):
    if v[0] == "countsince":
        toolbarapi.sendTo(json.dumps(countnew(v[1])), id)


toolbarapi.attach2(f)


def countnew(since):
    normal = 0
    errors = 0
    warnings = 0
    total = 0
    x = list(notificationslog)
    x.reverse()
    for i in x:
        if not i[0] > since:
            break
        else:
            if "warning" in i[1]:
                warnings += 1
            elif "error" in i[1]:
                errors += 1
            else:
                normal += 1
            total += 1
    return [total, normal, warnings, errors]


class WI:
    @cherrypy.expose
    def countnew(self, **kwargs):
        pages.require("view_status")
        return json.dumps(countnew(float(kwargs["since"])))

    @cherrypy.expose
    def mostrecent(self, **kwargs):
        pages.require("view_status")
        return json.dumps(notificationslog[-int(kwargs["count"]) :])


epochAndRemaining = [0, 15]

pending_notifications = []

apprise_lock = threading.RLock()


@scheduling.scheduler.everyHour
def apprise():
    if apprise_lock.acquire(blocking=False):
        try:
            while pending_notifications:
                f = pending_notifications.pop(0)
                try:
                    f()
                    time.sleep(5)
                except Exception:
                    # There's still room!  We can just keep retrying!
                    if len(pending_notifications) < 35:
                        pending_notifications.append(f)

                    logging.error("Error pushing AppRise notification")
                    # If one fails, retry all of them later.
                    return
        finally:
            apprise_lock.release()


def subscriber(topic, message):
    global notificationslog
    notificationslog.append((time.time(), topic, message))
    # Delete all but the most recent N notifications, where N is from the config file.
    notificationslog = notificationslog[-config["notifications-to-keep"] :]

    # TODO:
    # Not threadsafe. But it is still better than the old polling based system.
    try:
        toolbarapi.send(["newmsg"])
    except Exception:
        logging.exception("Error pushing notifications")

    api.send(["notification", [time.time(), topic, message]])

    if "error" in topic or "warning" in topic or "important" in topic:
        # Add allowed notifications at a rate of  under 1 per miniute up to 15 "stored credits"
        epochAndRemaining[1] = max(
            (time.monotonic() - epochAndRemaining[0]) / 240 + epochAndRemaining[1], 15
        )
        epochAndRemaining[0] = time.monotonic()

        if epochAndRemaining[1] > 1:
            epochAndRemaining[1] -= 1

            ts = strftime(time.time())
            if len(pending_notifications) > 35:
                pending_notifications.pop(0)

            def f():
                if pushsettings.get("apprise_target", None):
                    import apprise

                    # Create an Apprise instance
                    apobj = apprise.Apprise()

                    # Add all of the notification services by their server url.
                    # A sample email notification:
                    apobj.add(pushsettings.get("apprise_target", None))

                    # Then notify these services any time you desire. The below would
                    # notify all of the services loaded into our Apprise object.
                    apobj.notify(
                        body=str(message),
                        title=("Notification" if not "error" in topic else "Error")
                        + " "
                        + ts,
                    )

            pending_notifications.append(f)

            workers.do(apprise)


messagebus.subscribe("/system/notifications/#", subscriber)


def printer(t, m):
    if "error" in t:
        logger.error(f"{t}:{m}")
    elif "warning" in t:
        logger.warning(f"{t}:{m}")
    elif "important" in t:
        ilogger.info(f"{t}:{m}")
    else:
        logger.info(f"{t}:{m}")


messagebus.subscribe("/system/notifications/#", printer)


def mprinter(t, m):
    if "error" in t:
        mlogger.error(f"{t}:{m}")
    elif "warning" in t:
        mlogger.warning(f"{t}:{m}")
    elif "important" in t:
        mlogger.info(f"{t}:{m}")
    else:
        mlogger.info(f"{t}:{m}")


for i in config["print-topics"]:
    messagebus.subscribe(i, mprinter)
