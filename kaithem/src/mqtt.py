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
from scullery import mqtt
from . import tagpoints, messagebus, alerts, util, workers
import threading, weakref

allConnections = {}
allConnectionsLock = threading.Lock()

def listConnections():
    with allConnectionsLock:
        #Filter dead references
        return {i:allConnections[i] for i in allConnections if allConnections[i]()}

        
class EnhancedConnection(BaseConnection):
    def __init__(self, server, port=1883, password=None, *, alert_priority="warning", alert_ack=True, message_bus_name=None,**kw):
        self.statusTag = tagpoints.StringTag(
            "/system/mqtt/"+(message_bus_name or server+":"+str(port))+"/status")
        self.statusTagClaim = self.statusTag.claim(
            "dis_connected", "status", 90)
        BaseConnection.__init__(self, server=server, password=password, port=port,
                                alert_priority=alert_priority, alert_ack=True, message_bus_name=message_bus_name,**kw)

        with allConnectionsLock:
            torm = []
            for i in allConnections:
                if not allConnections[i]():
                    torm.append(i)
            for i in torm:
                allConnections.pop(i)
            allConnections[message_bus_name]=weakref.ref(self)

    def on_still_connected(self):
        BaseConnection.on_still_connected(self)
        self.statusTagClaim.set("connected")

    def on_disconnected(self):
        BaseConnection.on_disconnected(self)
        self.statusTagClaim.set("dis_connected")

    def configure_alert(self, alert_priority, alert_ack):
        self.statusTag.setAlarm("dis_connected", "value != 'connected'",
                                priority=alert_priority, auto_ack="yes" if alert_ack else 'no', trip_delay=10)


mqtt.Connection = EnhancedConnection
