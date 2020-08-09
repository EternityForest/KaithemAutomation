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

from scullery import getConnection
from scullery import Connection as BaseConnection

from . import tagpoints, messagebus, alerts, util, workers


class EnhancedConnection(BaseConnection):
    def __init__(self, server, port=1883,*, alertPriority="warning", alertAck=True):
        self.statusTag = tagpoints.StringTag(
                    "/system/mqtt/"+n+"/status")
        self.statusTagClaim = self.statusTag.claim(
            "disconnected", "status", 90)
        BaseConnection.__init__(self,server,port, alertPriority=alertPriority,alertAck=True)

    def onStillConnected(self):
        self().statusTagClaim.set("connected")
        self().alert.clear()
    
    def onDisconnected(self):
        self().statusTagClaim.set("disconnected")
        self().alert.trip()

    def configureAlert(self, alertPriority, alertAck):
        self.alert.setAlarm("disconnected","status != 'connected'",priority=alertPriority, autoAck=alertAck, tripDelay=5)