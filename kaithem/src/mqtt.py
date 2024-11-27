# SPDX-FileCopyrightText: Copyright 2019 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import threading
import weakref

from scullery import mqtt
from scullery.mqtt import Connection as BaseConnection

from . import tagpoints

allConnections = {}
allConnectionsLock = threading.Lock()


def listConnections():
    with allConnectionsLock:
        # Filter dead references
        return {
            i: allConnections[i] for i in allConnections if allConnections[i]()
        }


class EnhancedConnection(BaseConnection):
    def __init__(
        self,
        server,
        port=1883,
        password=None,
        *,
        alert_priority="warning",
        alert_ack=True,
        message_bus_name=None,
        **kw,
    ):
        self.statusTag = tagpoints.StringTag(
            "/system/mqtt/"
            + (message_bus_name or server + ":" + str(port))
            + "/status"
        )
        self.statusTagClaim = self.statusTag.claim("disconnected", "status", 90)
        BaseConnection.__init__(
            self,
            server=server,
            password=password,
            port=port,
            alert_priority=alert_priority,
            alert_ack=True,
            message_bus_name=message_bus_name,
            **kw,
        )

        with allConnectionsLock:
            to_rm = []
            for i in allConnections:
                if not allConnections[i]():
                    to_rm.append(i)
            for i in to_rm:
                allConnections.pop(i)
            allConnections[message_bus_name] = weakref.ref(self)

    def on_still_connected(self):
        BaseConnection.on_still_connected(self)
        self.statusTagClaim.set("connected")

    def on_disconnected(self):
        BaseConnection.on_disconnected(self)
        self.statusTagClaim.set("disconnected")

    def configure_alert(self, alert_priority, alert_ack):
        self.statusTag.set_alarm(
            "disconnected",
            "value != 'connected'",
            priority=alert_priority,
            auto_ack="yes" if alert_ack else "no",
            trip_delay=10,
        )


mqtt.Connection = EnhancedConnection
