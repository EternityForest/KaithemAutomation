# Copyright Daniel Dunn 2013
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

import weakref
from . import workers
from ws4py.websocket import WebSocket
import time
import json
import logging
import cherrypy
from . import messagebus, pages, auth, widgets
from .unitsofmeasure import strftime
from .config import config

mlogger = logging.getLogger("system.msgbuslog")

logger = logging.getLogger("system.notifications")
ilogger = logging.getLogger("system.notifications.important")

notificationslog = []




class API(widgets.APIWidget):
    def onNewSubscriber(self, user, cid, **kw):
        self.send(['all', notificationslog])


api = API()
api.require("/admin/mainpage.view")


toolbarapi=widgets.APIWidget()
toolbarapi.require("/admin/mainpage.view")
toolbarapi.echo=False

def f(u,v,id):
    if v[0]=='countsince':
        toolbarapi.sendTo(json.dumps(countnew(v[1])),id)


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
            if 'warning' in i[1]:
                warnings += 1
            elif 'error' in i[1]:
                errors += 1
            else:
                normal += 1
            total += 1
    return [total, normal, warnings, errors]






class WI():
    @cherrypy.expose
    def countnew(self, **kwargs):
        pages.require('/admin/mainpage.view')
        return json.dumps(countnew(float(kwargs['since'])))

    @cherrypy.expose
    def mostrecent(self, **kwargs):
        pages.require('/admin/mainpage.view')
        return json.dumps(notificationslog[-int(kwargs['count']):])




def doPlyer(t,m):
    try:
        try:
            from plyer import notification
        except ImportError:
            return
        n=notification

        n.notify(title='Kaithem '+t, message=m[:140], ticker='')
    except Exception:
        logger.exception("Could not do the notification")



epochAndRemaining = [0,15]

def subscriber(topic, message):
    global notificationslog
    notificationslog.append((time.time(), topic, message))
    # Delete all but the most recent N notifications, where N is from the config file.
    notificationslog = notificationslog[-config['notifications-to-keep']:]

    # TODO:
    # Not threadsafe. But it is still better than the old polling based system.
    try:
        toolbarapi.send(["newmsg"])
    except:
        logging.exception("Error pushing notifications")

    api.send(['notification', [time.time(), topic, message]])


    if 'error' in topic or 'warning' in topic:

        # Add allowed notifications at a rate of  under 1 per miniute up to 15 "stored credits"
        epochAndRemaining[1] = max((time.monotonic()-epochAndRemaining[0])/240 + epochAndRemaining[1], 15)
        epochAndRemaining[0]=time.monotonic()

        if epochAndRemaining[1] > 1:
            epochAndRemaining[1] -= 1

            def f():
                doPlyer(topic.split("/")[-1],message)
            workers.do(f)




messagebus.subscribe('/system/notifications/#', subscriber)


def printer(t, m):
    if 'error' in t:
        logger.error(t+':'+m)
    elif 'warning' in t:
        logger.warning(t+':'+m)
    elif 'important' in t:
        ilogger.info(t+':'+m)
    else:
        logger.info(t+':'+m)


messagebus.subscribe('/system/notifications/#', printer)


def mprinter(t, m):
    if 'error' in t:
        mlogger.error(t+':'+m)
    elif 'warning' in t:
        mlogger.warning(t+':'+m)
    elif 'important' in t:
        mlogger.info(t+':'+m)
    else:
        mlogger.info(t+':'+m)


for i in config['print-topics']:
    messagebus.subscribe(i, mprinter)
