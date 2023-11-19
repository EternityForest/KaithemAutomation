import os
from scullery import persist
from . import directories
from . import statemachines, widgets, scheduling, workers, pages, messagebus, unitsofmeasure
from typeguard import typechecked
from typing import Union, Dict, Optional, Any
import logging
import threading
import time
import random
import weakref
logger = logging.getLogger("system.alerts")
lock = threading.RLock()


fn = os.path.join(directories.vardir, "core.settings", "alertsounds.toml")

if os.path.exists(fn):
    file = persist.load(fn)
else:
    file = {
        "all": {
            "soundcard": "__disable__"
        },
        "critical": {
            "file": "error.ogg",
            "interval": 36.0
        },
        "error": {
            "file": "",
            "interval": 3600.0
        },
        "warning": {
            "file": "",
            "interval": 3600.0
        }
    }


def saveSettings(*a, **k):
    persist.save(file, fn, private=True)
    persist.unsavedFiles.pop(fn, "")


# This is a dict of all alerts that have not yet been acknowledged.
# It is immutable and only ever atomically replaces
unacknowledged = {}
# Same as above except may be mutated under lock
_unacknowledged = {}

# see above, but for active alarms not just for unacknowledged
active = {}
_active = {}


# Added on trip, removed on normal
tripped = {}
_tripped = {}

all = weakref.WeakValueDictionary()

priorities = {
    None: 0,
    'none': 0,
    'debug': 10,
    'info': 20,
    'warning': 30,
    'error': 40,
    'critical': 50
}

# _ and . and / allowed
illegalCharsInName = "[]{}|\\<>,?-=+)(*&^%$#@!~`\n\r\t\0"


nextbeep = 10**10
sfile = "alert.ogg"


def formatAlerts():
    return {i: active[i]().format() for i in active if active[i]() and pages.canUserDoThis(active[i]().permissions)}


class API(widgets.APIWidget):
    def onNewSubscriber(self, user, cid, **kw):
        with lock:
            self.send(['all', formatAlerts()])


api = API()
api.require("/users/alerts.view")


def handleApiCall(u: str, v: list):
    if v[0] == "ack":
        if pages.canUserDoThis(all[v[1]].ackPermissions, u):
            all[v[1]].acknowledge()


api.attach(handleApiCall)


def calcNextBeep():
    global nextbeep
    global sfile
    x = _highestUnacknowledged(excludeSilent=True)
    if not x:
        x = 0
    else:
        x = priorities.get(x, 40)
    if x >= 30 and x < 40:
        nextbeep = file['warning']['interval'] + \
            time.time() + (random.random()*3)
        sfile = file['warning']['file']

    elif x >= 40 and x < 50:
        nextbeep = file['error']['interval'] + \
            time.time() + (random.random()*3)
        sfile = file['error']['file']

    elif x >= 50:
        nextbeep = file['critical']['interval'] + \
            time.time() + (random.random()*3)
        sfile = file['critical']['file']
    else:
        nextbeep = 10**10
        sfile = None

    return sfile


# A bit of randomness makes important alerts seem more important
@scheduling.scheduler.everySecond
def alarmBeep():
    if time.time() > nextbeep:
        calcNextBeep()
        s = (sfile or '').strip()
        beepDevice = file['all']['soundcard']
        if beepDevice == "__disable__":
            return
        if s:
            try:
                # Ondemand to avoid circular import
                from . import sound
                sound.play_sound(
                    s, handle="kaithem_sys_main_alarm", output=beepDevice)
            except Exception:
                logger.exception("ERROR PLAYING ALERT SOUND")


def _highestUnacknowledged(excludeSilent=False):
    # Pre check outside lock for efficiency.
    if not unacknowledged:
        return
    level = 'debug'
    for i in unacknowledged.values():
        i = i()
        if i:
            if excludeSilent:
                if i.silent:
                    continue

            if (priorities[i.priority] > priorities[level]):
                level = i.priority
    return level


def sendMessage():
    x = _highestUnacknowledged()
    messagebus.postMessage("/system/alerts/level", x)


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


class Alert():
    @typechecked
    def __init__(self, name: str, priority: str = "info", zone=None, tripDelay: Union[int, float] = 0, autoAck: Union[bool, float, int] = False,
                 permissions: list = [], ackPermissions: list = [], id=None, description: str = "", silent: bool = False
                 ):
        """
        Create a new Alert object. An alert is a persistant notification 
        implemented as a state machine.

        Alerts begin in the "normal" state, and if tripped enter the "tripped"
        state. An alert remaining in the tripped state for more than "tripDelay"
        enters the active state and will show in notifications, trigger automated actions
        etc.

        An alert may be manually acknowledged at which point it will become "acknowledged"
        and may stop sounding alarms, etc. An alarm that is "cleared" but 
        not acknowledged, meaning the issue that caused the alarm is no longer present
        will will still show up until acknowledged.

        An alarm that is tripped while in the cleared state enters the "retripped" state, which
        can return to active, like tripped, but otherwise acts like cleared.

        Alarms can self-acknowledge after a certain delay after being cleared, set this
        delay using autoAck. False or 0 disables autoAck.

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
                name = name.replace(i, ' ')

        self.permissions = permissions + ['/users/alerts.view']
        self.ackPermissions = ackPermissions + ['users/alerts.acknowledge']
        self.silent = silent

        self.priority = priority
        self.zone = zone
        self.name = name
        self._tripDelay = tripDelay

        # Tracks any a associated tag point
        self.tagpoint_name: str = ''
        self.tagpoint_config_data: Optional[Dict[str, Any]] = None


        # Last trip time
        self.trippedAt = 0

        self.sm = statemachines.StateMachine("normal")

        self.sm.add_state("normal", enter=self._onNormal)
        self.sm.add_state("tripped", enter=self._onTrip)
        self.sm.add_state("active", enter=self._onActive)
        self.sm.add_state("acknowledged", enter=self._onAck)
        self.sm.add_state("cleared", enter=self._onClear)
        self.sm.add_state("retripped", enter=self._onTrip)
        self.sm.add_state("error")

        # After N seconds in the trip state, we go active
        self.sm.set_timer("tripped", tripDelay, "active")
        self.sm.set_timer("retripped", tripDelay, "active")

        # Automatic acknowledgement makes an alarm go away when it's cleared.
        if autoAck:
            if autoAck is True:
                autoAck = 10
            self.sm.set_timer("cleared", autoAck, "normal")

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
        return """<small>State machine object at %s<br></small>
            <b>State:</b> %s<br>
            <b>Entered</b> %s ago at %s<br>
            %s""" % (
            hex(id(self)),
            self.sm.state,
            unitsofmeasure.formatTimeInterval(
                time.time()-self.sm.entered_state, 2),
            unitsofmeasure.strftime(self.sm.entered_state),
            ('\n' if self.description else '')+self.description
        )

    def format(self):
        return {
            'id': self.id,
            'description': self.description,
            'state': self.sm.state,
            'name': self.name,
            'zone': self.zone
        }

    def API_ack(self):
        pages.require(self.ackPermissions)
        pages.postOnly()
        self.acknowledge()

    @property
    def tripDelay(self):
        return self._tripDelay

    # I don't like the undefined thread aspec of __del__. Change this?
    def _onActive(self):
        global unacknowledged
        global active
        with lock:
            cleanup()
            _unacknowledged[self.id] = weakref.ref(self)
            unacknowledged = _unacknowledged.copy()

            _active[self.id] = weakref.ref(self)
            active = _active.copy()
            s = calcNextBeep()
        if s:
            # Sound drivers can actually use tagpoints, this was causing a
            # deadlock with the tag's lock in the __del__ function GCing some
            # other tag. I don't quite understand it but this should break the loop
            def f():
                # Ondemand to avoid circular import
                from . import sound
                beepDevice = file['all']['soundcard']
                sound.play_sound(
                    s, handle="kaithem_sys_main_alarm", output=beepDevice)
                api.send(['shouldRefresh'])

            workers.do(f)

        if self.priority in ("error", "critical"):
            logger.error("Alarm "+self.name + " ACTIVE")
            messagebus.postMessage(
                "/system/notifications/errors", "Alarm "+self.name+" is active")
        if self.priority in ("warning"):
            messagebus.postMessage(
                "/system/notifications/warnings", "Alarm "+self.name+" is active")
            logger.warning("Alarm "+self.name + " ACTIVE")
        else:
            logger.info("Alarm "+self.name + " active")

        if self.priority in ("info"):
            messagebus.postMessage(
                "/system/notifications", "Alarm "+self.name+" is active")
        sendMessage()

    def _onAck(self):
        global unacknowledged
        with lock:
            cleanup()
            if self.id in _unacknowledged:
                del _unacknowledged[self.id]
            unacknowledged = _unacknowledged.copy()
        calcNextBeep()
        api.send(['shouldRefresh'])
        sendMessage()

    def _onNormal(self):
        "Mostly defensivem but also cleans up if the autoclear occurs and we skio the acknowledged state"
        global unacknowledged, active, tripped
        if not self.sm.prev_state == 'tripped':
            if self.priority in ("info", "warning", "error", "critical"):
                messagebus.postMessage(
                    "/system/notifications", "Alarm "+self.name+" returned to normal")

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
        calcNextBeep()
        api.send(['shouldRefresh'])
        sendMessage()

    def _onTrip(self):
        global tripped

        with lock:
            cleanup()
            _tripped[self.id] = weakref.ref(self)
            tripped = _tripped.copy()

        if self.priority in ("error", "critical"):
            logger.error("Alarm "+self.name + " tripped:\n "+self.trip_message)
        if self.priority in ("warning"):
            logger.warning("Alarm "+self.name +
                           " tripped:\n"+self.trip_message)
        else:
            logger.info("Alarm "+self.name + " tripped:\n"+self.trip_message)

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

    def _onClear(self):
        if self.priority in ("error", "critical", "warning"):
            if self.sm.state == 'active':
                messagebus.postMessage(
                    "/system/notifications", "Alarm "+self.name+" condition cleared, waiting for ACK")

        logger.info("Alarm "+self.name + " cleared")
        api.send(['shouldRefresh'])
        sendMessage()

    def __del__(self):
        self.acknowledge("<DELETED>")
        self.clear()
        cleanup()
        sendMessage()

    def acknowledge(self, by="unknown", notes=""):
        notes = notes[:64]
        if notes.strip():
            notes = ':\n'+notes
        else:
            notes = ''

        self.sm.event("acknowledge")
        if not by == "<DELETED>":
            logger.info("Alarm "+self.name + " acknowledged by" + by+notes)

            if self.priority in ("error", "critical", "warning"):
                messagebus.postMessage(
                    "/system/notifications", "Alarm "+self.name+" acknowledged by " + by+notes)

    def error(self, msg=""):
        global unacknowledged
        self.sm.goto("error")
        self.trip_message = msg
