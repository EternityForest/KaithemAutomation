# Copyright Daniel Dunn 2019
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

from scullery.mqtt import Connection as BaseConnection
import scullery.mqtt
from . import tagpoints, messagebus, alerts, util, workers
import threading, weakref

allConnections = {}
allConnectionsLock = threading.Lock()

def listConnections():
    with allConnectionsLock:
        #Filter dead references
        return {i:allConnections[i] for i in allConnections if allConnections[i]()}

        
class EnhancedConnection(BaseConnection):
    def __init__(self, server, port=1883, password=None, *, alertPriority="warning", alertAck=True, messageBusName=None,**kw):
        self.statusTag = tagpoints.StringTag(
            "/system/mqtt/"+(messageBusName or server+":"+str(port))+"/status")
        self.statusTagClaim = self.statusTag.claim(
            "disconnected", "status", 90)
        BaseConnection.__init__(self, server=server, password=password, port=port,
                                alertPriority=alertPriority, alertAck=True, messageBusName=messageBusName,**kw)

        with allConnectionsLock:
            torm = []
            for i in allConnections:
                if not allConnections[i]():
                    torm.append(i)
            for i in torm:
                allConnections.pop(i)
            allConnections[messageBusName]=weakref.ref(self)

    def onStillConnected(self):
        self.statusTagClaim.set("connected")

    def onDisconnected(self):
        self.statusTagClaim.set("disconnected")

    def configureAlert(self, alertPriority, alertAck):
        self.statusTag.setAlarm("disconnected", "value != 'connected'",
                                priority=alertPriority, autoAck="yes" if alertAck else 'no', tripDelay=5)


scullery.mqtt.Connection = EnhancedConnection
