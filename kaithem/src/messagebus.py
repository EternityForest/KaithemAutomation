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

from scullery.messagebus import *
import scullery.messagebus
import traceback,cherrypy

def handleMsgbusError(f,topic,message):
    scullery.messagebus.log.exception("Error in subscribed function for "+topic)
    try:
        from . import newevt
        if f.__module__ in newevt.eventsByModuleName:
            newevt.eventsByModuleName[f.__module__]._handle_exception()

        #If we can't handle it whence it came
        else:
            try:
                x = hasattr(f,"_kaithemAlreadyPostedNotificatonError")
                f._kaithemAlreadyPostedNotificatonError=True
                if x:
                    messagebus.postMessage("First message bus subscriber error in: " +str(f))
            except:
                pass
    except Exception as e:
        print(traceback.format_exc())
        del f


def _shouldReRaiseAttrErr():
    "Check if we actually need to notify about errors during cherrypy shutdown, to avoid annoyance "
    return cherrypy.engine.state == cherrypy.engine.states.STARTED

scullery.messagebus.subscriberErrorHandlers = [handleMsgbusError]
scullery.messagebus._shouldReRaiseAttrErr = _shouldReRaiseAttrErr