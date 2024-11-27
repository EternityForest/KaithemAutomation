from __future__ import annotations

import threading
import time
import weakref
from typing import Any

import structlog
from beartype import beartype
from scullery import statemachines

from . import (
    messagebus,
    pages,
    unitsofmeasure,
    widgets,
)

logger = structlog.get_logger(__name__)
lock = threading.RLock()

system_shutdown = threading.Event()


def shutdown(*a: tuple[Any], **k: dict[str, Any]):
    system_shutdown.set()


messagebus.subscribe("/system/shutdown", shutdown)


# This is a dict of all alerts that have not yet been acknowledged.
# It is immutable and only ever atomically replaces
unacknowledged: dict[str, weakref.ref[Alert]] = {}
# Same as above except may be mutated under lock
_unacknowledged: dict[str, weakref.ref[Alert]] = {}

# see above, but for active alarms not just for unacknowledged
active: dict[str, weakref.ref[Alert]] = {}
_active: dict[str, weakref.ref[Alert]] = {}


# Added on trip, removed on normal
tripped: dict[str, weakref.ref[Alert]] = {}
_tripped: dict[str, weakref.ref[Alert]] = {}

all = weakref.WeakValueDictionary()

priority_to_class = {
    "critical": {"danger": 1},
    "error": {"danger": 1},
    "warning": {"danger": 1},
    "info": {},
    "debug": {"danger": 1},
}


def getAlertState() -> dict[str, str | dict[str, Any]]:
    try:
        with lock:
            d: dict[str, str | dict[str, Any]] = {}

            for i in (active, unacknowledged):
                for j in i:
                    alert = i[j]()
                    if not alert:
                        continue

                    d[alert.name] = {
                        "state": alert.sm.state,
                        "priority": alert.priority,
                        "description": alert.description,
                        "barrel-class": priority_to_class.get(
                            alert.priority, {"warning": 1}
                        ),
                        "message": alert.trip_message,
                    }
            return d

    except Exception:
        logger.exception("Error pushing alert state on msg bus")
        return {
            "Alerts": {"priority": "error", "state": "active"},
            "unacknowledged_level": highest_unacknowledged_alert_level(),
        }


def pushAlertState():
    messagebus.post("/system/alerts/state", getAlertState())


priorities = {
    None: 0,
    "": 0,
    "none": 0,
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
    "critical": 50,
}

# _ and . and / allowed
illegalCharsInName = "[]{}|\\<>,?-=+)(*&^%$#@!~`\n\r\t\0"


def formatAlerts():
    return {
        i: active[i]().format()
        for i in active
        if active[i]() and pages.canUserDoThis(active[i]().permissions)
    }


class API(widgets.APIWidget):
    def on_new_subscriber(self, user, connection_id, **kw):
        with lock:
            self.send(["all", formatAlerts()])


api = API()
api.require("view_status")


def handleApiCall(u: str, v: list):
    if v[0] == "ack":
        if pages.canUserDoThis(all[v[1]].ackPermissions, u):
            all[v[1]].acknowledge()


api.attach(handleApiCall)


def highest_unacknowledged_alert_level(excludeSilent=False) -> str:
    # Pre check outside lock for efficiency.
    if not unacknowledged:
        return ""
    level = "debug"
    for i in unacknowledged.values():
        i = i()
        if i:
            if excludeSilent:
                if i.silent:
                    continue

            if priorities[i.priority] > priorities[level]:
                level = i.priority
    return level


def sendMessage():
    x = highest_unacknowledged_alert_level()
    messagebus.post_message("/system/alerts/level", x)


def cleanup():
    "Cleans up the mutable lists, call only under lock"
    global active
    global unacknowledged
    for i in list(_active.keys()):
        if _active[i]() is None:
            try:
                del _active[i]
            except KeyError:
                pass
        active = _active.copy()
    for i in list(_unacknowledged.keys()):
        if _unacknowledged[i]() is None:
            try:
                del _unacknowledged[i]
            except KeyError:
                pass


class Alert:
    @beartype
    def __init__(
        self,
        name: str,
        priority: str = "info",
        zone=None,
        trip_delay: int | float = 0,
        auto_ack: bool | float | int = False,
        permissions: list = [],
        ackPermissions: list = [],
        id=None,
        description: str = "",
        silent: bool = False,
    ):
        """
        Create a new Alert object. An alert is a persistant notification
        implemented as a state machine.

        Alerts begin in the "normal" state, and if tripped enter the "tripped"
        state. An alert remaining in the tripped state for more than "trip_delay"
        enters the active state and will show in notifications, trigger automated actions
        etc.

        An alert may be manually acknowledged at which point it will become "acknowledged"
        and may stop sounding alarms, etc. An alarm that is "cleared" but
        not acknowledged, meaning the issue that caused the alarm is no longer present
        will will still show up until acknowledged.

        An alarm that is tripped while in the cleared state enters the "retripped" state, which
        can return to active, like tripped, but otherwise acts like cleared.

        Alarms can self-acknowledge after a certain delay after being cleared, set this
        delay using auto_ack. False or 0 disables auto_ack.

        Finally, alarms can be in the "error" state, which is an error with the alarm
        triggering logic itself. The priority of errored alarms is always
        temporarily upgraded to error.

        Errored alarms return to the "normal" state when acknowledged and otherwise
        remain in the error state.

        The zone parameter is a hierarchal location specified used to indicate
        it's physical location.

        There is no cleanup action required when deleting an alarm, nor
        is there any need for unique names. However ID
        """

        if name == "":
            raise ValueError("Alert with empty name")

        for i in illegalCharsInName:
            if i in name:
                name = name.replace(i, " ")

        self.permissions = permissions + ["view_status"]
        self.ackPermissions = ackPermissions + ["users/alerts.acknowledge"]
        self.silent = silent

        self.priority = priority
        self.zone = zone
        self.name = name
        self._trip_delay = trip_delay

        # Tracks any a associated tag point
        self.tagpoint_name: str = ""
        self.tagpoint_config_data: dict[str, Any] | None = None

        # Last trip time
        self.trippedAt = 0

        self.sm = statemachines.StateMachine("normal")

        self.sm.add_state("normal", enter=self._on_normal)
        self.sm.add_state("tripped", enter=self._on_trip)
        self.sm.add_state("active", enter=self._on_active)
        self.sm.add_state("acknowledged", enter=self._on_ack)
        self.sm.add_state("cleared", enter=self._on_clear)
        self.sm.add_state("retripped", enter=self._on_trip)
        self.sm.add_state("error")

        # After N seconds in the trip state, we go active
        self.sm.set_timer("tripped", trip_delay, "active")
        self.sm.set_timer("retripped", trip_delay, "active")

        # Automatic acknowledgement makes an alarm go away when it's cleared.
        if auto_ack:
            if auto_ack is True:
                auto_ack = 10
            self.sm.set_timer("cleared", auto_ack, "normal")

        self.sm.add_rule("normal", "trip", "tripped")
        self.sm.add_rule("tripped", "release", "normal")

        self.sm.add_rule("cleared", "trip", "retripped")
        self.sm.add_rule("retripped", "release", "cleared")

        self.sm.add_rule("active", "acknowledge", "acknowledged")
        self.sm.add_rule("active", "release", "cleared")
        self.sm.add_rule("acknowledged", "release", "normal")
        self.sm.add_rule("error", "acknowledge", "normal")

        self.sm.add_rule("cleared", "acknowledge", "normal")

        self.description = description

        self.id = id or str(time.time())
        all[self.id] = self

        def notificationHTML():
            return ""

        self.notificationHTML = notificationHTML

    def __html_repr__(self):
        return """<small>State machine object at {}<br></small>
            <b>State:</b> {}<br>
            <b>Entered</b> {} ago at {}<br>
            {}""".format(
            hex(id(self)),
            self.sm.state,
            unitsofmeasure.format_time_interval(
                time.time() - self.sm.entered_state, 2
            ),
            unitsofmeasure.strftime(self.sm.entered_state),
            ("\n" if self.description else "") + self.description,
        )

    def format(self):
        return {
            "id": self.id,
            "description": self.description,
            "state": self.sm.state,
            "name": self.name,
            "zone": self.zone,
        }

    def API_ack(self):
        try:
            pages.require(self.ackPermissions)
        except PermissionError:
            return pages.loginredirect(pages.geturl())
        pages.postOnly()
        self.acknowledge()

    @property
    def trip_delay(self):
        return self._trip_delay

    # I don't like the undefined thread aspect of __del__. Change this?
    def _on_active(self):
        global unacknowledged
        global active

        with lock:
            cleanup()
            _unacknowledged[self.id] = weakref.ref(self)
            unacknowledged = _unacknowledged.copy()

            _active[self.id] = weakref.ref(self)
            active = _active.copy()

        if self.priority in ("error", "critical", "important"):
            logger.error(f"Alarm {self.name} ACTIVE")
            messagebus.post_message(
                "/system/notifications/errors", f"Alarm {self.name} is active"
            )
        elif self.priority in ("warning"):
            messagebus.post_message(
                "/system/notifications/warnings", f"Alarm {self.name} is active"
            )
            logger.warning(f"Alarm {self.name} ACTIVE")
        else:
            logger.info(f"Alarm {self.name} active")

        if self.priority in ("info"):
            messagebus.post_message(
                "/system/notifications", f"Alarm {self.name} is active"
            )
        sendMessage()
        pushAlertState()

    def _on_ack(self):
        global unacknowledged
        with lock:
            cleanup()
            if self.id in _unacknowledged:
                del _unacknowledged[self.id]
            unacknowledged = _unacknowledged.copy()

        api.send(["shouldRefresh"])
        sendMessage()
        pushAlertState()

    def _on_normal(self):
        "Mostly defensive but also cleans up if the autoclear occurs and we skip the acknowledged state"
        global unacknowledged, active, tripped
        if not self.sm.prev_state == "tripped":
            if self.priority in (
                "info",
                "warning",
                "error",
                "critical",
                "important",
            ):
                if self.priority in (
                    "warning",
                    "error",
                    "critical",
                    "important",
                ):
                    messagebus.post_message(
                        "/system/notifications/important",
                        f"Alarm {self.name} returned to normal",
                    )
                else:
                    messagebus.post_message(
                        "/system/notifications",
                        f"Alarm {self.name} returned to normal",
                    )

        with lock:
            cleanup()
            if self.id in _unacknowledged:
                del _unacknowledged[self.id]
            unacknowledged = _unacknowledged.copy()

            if self.id in _tripped:
                del _tripped[self.id]
            tripped = _tripped.copy()

            if self.id in _active:
                del _active[self.id]
            active = _active.copy()

        api.send(["shouldRefresh"])
        sendMessage()
        pushAlertState()

    def _on_trip(self):
        global tripped
        with lock:
            cleanup()
            _tripped[self.id] = weakref.ref(self)
            tripped = _tripped.copy()

        if self.priority in ("error", "critical", "important"):
            logger.error(f"Alarm {self.name} tripped:\n {self.trip_message}")
        if self.priority in ("warning"):
            logger.warning(f"Alarm {self.name} tripped:\n{self.trip_message}")
        else:
            logger.info(f"Alarm {self.name} tripped:\n{self.trip_message}")
        pushAlertState()

    def trip(self, message=""):
        self.trip_message = str(message)[:4096]
        self.sm.event("trip")
        self.trippedAt = time.time()

    def release(self):
        self.clear()

    def clear(self):
        global active
        with lock:
            cleanup()
            if self.id in _active:
                del _active[self.id]
            active = _active.copy()
        self.sm.event("release")

    def _on_clear(self):
        if self.priority in ("error", "critical", "warning", "important"):
            if self.sm.state == "active":
                messagebus.post_message(
                    "/system/notifications",
                    f"Alarm {self.name} condition cleared, waiting for ACK",
                )

        logger.info(f"Alarm {self.name} cleared")
        api.send(["shouldRefresh"])
        sendMessage()
        pushAlertState()

    def __del__(self):
        if not system_shutdown.is_set():
            self.acknowledge("<DELETED>")
            self.clear()
            cleanup()
            sendMessage()
            pushAlertState()

    def acknowledge(self, by="unknown", notes=""):
        notes = notes[:64]
        if notes.strip():
            notes = f":\n{notes}"
        else:
            notes = ""

        self.sm.event("acknowledge")
        if not by == "<DELETED>":
            logger.info(f"Alarm {self.name} acknowledged by{by}{notes}")

            if self.priority in ("error", "critical", "warning", "important"):
                messagebus.post_message(
                    "/system/notifications",
                    f"Alarm {self.name} acknowledged by {by}{notes}",
                )

    def error(self, msg=""):
        global unacknowledged
        self.sm.goto("error")
        self.trip_message = msg
