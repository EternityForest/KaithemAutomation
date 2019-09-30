#Copyright Daniel Dunn 2013
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

import time,json,logging
import cherrypy
from . import messagebus,pages, auth,widgets
from .unitsofmeasure import strftime
from .config import config

logger = logging.getLogger("system.notifications")
ilogger = logging.getLogger("system.notifications.important")

notificationslog =   []


class API(widgets.APIWidget):
    def onNewSubscriber(self, user, cid, **kw):
        self.send(['all', notificationslog])

api = API()
api.require("/admin/mainpage.view")


def makenotifier():
    if not 'LastSawMainPage' in cherrypy.response.cookie:
        t = float(cherrypy.request.cookie["LastSawMainPage"].value)
    else:
        t = float(cherrypy.response.cookie["LastSawMainPage"].value)

    b = countnew(t)
    if b[2]:
        c = 'warning'
    if b[3]:
        c = 'error'
    else:
         c = ""

    if b[0]:
        s = "<span class='%s'>(%d)</span>" %(c,b[0])
    else:
        s = ''
    return s


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
                    warnings +=1
                elif 'error' in i[1]:
                    errors += 1
                else:
                    normal += 1
                total +=1
        return [total,normal,warnings,errors]
import weakref

handlers = weakref.WeakValueDictionary()
handlersmp = weakref.WeakValueDictionary()

from ws4py.websocket import WebSocket
class websocket(WebSocket):
    def opened(self):
        self.send(json.dumps(countnew(self.since)))
    def closed(self,*a,**k):
        del handlers[self.id]

class WI():
    @cherrypy.expose
    def countnew(self,**kwargs):
        pages.require('/admin/mainpage.view')
        return json.dumps(countnew(float(kwargs['since'])))

    @cherrypy.expose
    def mostrecent(self,**kwargs):
        pages.require('/admin/mainpage.view')
        return json.dumps(notificationslog[-int(kwargs['count']):])

    @cherrypy.expose
    def ws(self,since=0):
        # you can access the class instance through
        if not config['enable-websockets']:
            raise RuntimeError("Websockets disabled in server config")
        pages.require('/admin/mainpage.view')
        handler = cherrypy.request.ws_handler
        handler.user=  pages.getAcessingUser()
        handler.since=float(since)
        handler.id = time.monotonic()
        handlers[handler.id]=handler

    def ws_mp(self,since=0):
        # you can access the class instance through
        if not config['enable-websockets']:
            raise RuntimeError("Websockets disabled in server config")
        pages.require('/admin/mainpage.view')
        handler = cherrypy.request.ws_handler
        handler.user=  pages.getAcessingUser()
        handler.since=float(since)
        handler.id = time.monotonic()
        handlersmp[handler.id]=handler



def subscriber(topic,message):
    global notificationslog
    notificationslog.append((time.time(),topic,message))
    #Delete all but the most recent N notifications, where N is from the config file.
    notificationslog = notificationslog[-config['notifications-to-keep']:]
    
    #TODO:
    #Not threadsafe. But it is still better than the old polling based system.
    try:
        for i in handlers:
            if auth.canUserDoThis(handlers[i].user,'/admin/mainpage.view'):
                handlers[i].send(json.dumps(countnew(handlers[i].since)))
                handlersmp[i].send([time.time(),topic,message])
    except:
        logging.exception("Error pushing notifications")

    api.send(['notification',[time.time(),topic,message]])

messagebus.subscribe('/system/notifications/',subscriber)

def printer(t,m):
    if 'error' in t:
        logger.error(m)
    elif 'warning' in t:
        logger.warning(m)
    elif 'important' in t:
        ilogger.info(m)
    else:
        logger.info(m)

for i in config['print-topics']:
    messagebus.subscribe(i,printer)
