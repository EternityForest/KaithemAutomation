from src import statemachines, registry, sound,scheduling,workers,pages,messagebus,virtualresource,unitsofmeasure

import logging,threading,time, random, weakref
logger = logging.getLogger("system.alerts")

lock = threading.Lock()

#This is a dict of all alerts that have not yet been acknowledged.
#It is immutable and only ever atomically replaces
unacknowledged = {}
#Same as above except may be mutated under lock
_unacknowledged = {}

#see above, but for active alarms not just for unacknowledged
active ={}
_active ={}

all = weakref.WeakValueDictionary()

priorities  ={
    'debug': 10,
    'info':20,
    'warning': 30,
    'error':40,
    'critical': 50
}




nextbeep = 10**10
sfile = "alert.ogg"

def calcNextBeep():
    global nextbeep
    global sfile
    x = _highestUnacknowledged()
    if not x:
        x=0
    else:
        x = priorities.get(x,40)
    if x>=30 and x<40:
            nextbeep = registry.get("system/alerts/warning/soundinterval",60*25) +time.time()
            sfile = registry.get("system/alerts/warning/soundfile","alert.ogg")
    elif x>=40 and x<50:
            nextbeep = registry.get("system/alerts/error/soundinterval",120)* ((random.random()/5.0)+0.9) + time.time()
            sfile = registry.get("system/alerts/error/soundfile","error.ogg")
            
    elif x>=50:
            nextbeep = registry.get("system/alerts/critical/soundinterval",12.6) * ((random.random()/2.0)+0.75) + time.time()
            sfile = registry.get("system/alerts/critical/soundfile","error.ogg")               
    else:
        nextbeep = 10**10
        sfile = None
    
    return sfile


#A bit of randomness makes important alerts seem more important
@scheduling.scheduler.everySecond
def alarmBeep():
    if time.time() > nextbeep:
        calcNextBeep()
        s = sfile
        beepDevice = registry.get("system/alerts/soundcard",None)
        if s:
            sound.playSound(s,handle="kaithem_sys_main_alarm",output=beepDevice)





def highestUnacknowledged():
    #Pre check outside lock for efficiency. 
    if not unacknowledged:
        return
    with lock:
        l = -1
        for i in unacknowledged.values():
            i = i()
            if i:
                if (priorities[i.priority] if not i.sm.state=="error" else 40) > l:
                    l = i.priority
        return l


def _highestUnacknowledged():
    #Pre check outside lock for efficiency. 
    if not unacknowledged:
        return
    l = -1
    for i in unacknowledged.values():
        i = i()
        if i:
            #Handle the priority upgrading
            if (priorities[i.priority] if not i.sm.state=="error" else 40) > l:
                l = i.priority
    return l


def cleanup():
    global active
    global unacknowledged
    for i in _active.keys():
        if active[i]()==None:
            del active[i]
    for i in _unacknowledged.keys():
        if _unacknowledged[i]()==None:
            del _unacknowledged[i]

class Alert(virtualresource.VirtualResource):
    def __init__(self, name, priority="info", zone=None, tripDelay=0, autoAck=False,
                permissions=[], ackPermissions=[], id=None
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
        virtualresource.VirtualResource.__init__(self)

        self.permissions    = permissions + ['/users/alarms.view']
        self.ackPermissions = ackPermissions + ['users/alarms.acknowledge']

        self.priority = priority
        self.zone = zone
        self.name = name
        self._tripDelay = tripDelay
    
        #Last trip time
        self.trippedAt = 0
        
        self.sm = statemachines.StateMachine("normal")

        self.sm.addState("normal")
        self.sm.addState("tripped")
        self.sm.addState("active", enter=self._onActive)
        self.sm.addState("acknowledged", enter=self._onAck)
        self.sm.addState("cleared")
        self.sm.addState("error")

        #After N seconds in the trip state, we go active
        self.sm.setTimer("tripped", tripDelay, "active")

        #Automatic acknowledgement makes an alarm go away when it's cleared.
        if autoAck:
            if autoAck is True:
                autoAck = 10
            self.sm.setTimer("cleared",autoAck,"normal")
        
        self.sm.addRule("normal", "trip","tripped")
        self.sm.addRule("active","acknowledge","acknowledged")
        self.sm.addRule("active","release","cleared")
        self.sm.addRule("acknowledged","release","normal")
        self.sm.addRule("error","acknowledge","normal")
        self.description = ""

        self.id = id or str(time.time())
        all[self.id]=self


    def __html_repr__(self):
        return """<small>State machine object at %s<br></small>
            <b>State:</b> %s<br>
            <b>Entered</b> %s ago at %s<br>
            %s"""%(
        hex(id(self)),
        self.sm.state,
        unitsofmeasure.formatTimeInterval(time.time()-self.sm.enteredState,2),
        unitsofmeasure.strftime(self.sm.enteredState),
        ('\n' if self.description else '')+self.description
        )
    
    def handoff(self,other):
        #The underlying state machine handles the handoff
        self.sm.handoff(other.sm)
        virtualresource.VirtualResource.handoff(self,other)

    def API_ack(self):
        pages.require(self.ackPermissions)
        self.acknowledge()
    
    @property
    def tripDelay(self):
        return self._tripDelay

    #I don't like the undefined thread aspec of __del__. Change this?    
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
            sound.playSound(s,handle="kaithem_sys_main_alarm")
        if self.priority in ("error, critical"):
            logger.error("Alarm "+self.name +" ACTIVE")
            messagebus.postMessage("/system/notifications/errors", "Alarm "+self.name+" is active")
        if self.priority in ("warning"):
            logger.warning("Alarm "+self.name +" ACTIVE")
        else:
            logger.info("Alarm "+self.name +" active")


           
    def _onAck(self):
        "Called both when acknowledged, and when released."
        global unacknowledged
        with lock:
            cleanup()
            if self.id in _unacknowledged:
                del _unacknowledged[self.id]
            unacknowledged = _unacknowledged.copy()
        calcNextBeep()

    def trip(self):
        self.sm.event("trip")
        self.trippedAt = time.time()
        if self.priority in ("error, critical"):
            logger.error("Alarm "+self.name +" tripped")
        if self.priority in ("warning"):
            logger.warning("Alarm "+self.name +" tripped")
        else:
            logger.info("Alarm "+self.name +" tripped")

    def clear(self):
        global active
        with lock:
            cleanup()
            if self.id in _active:
                del _active[self.id]
            active = _active.copy()
        self.sm.event("release")
        logger.info("Alarm "+self.name +" cleared")


    def __del__(self):
        self.acknowledge()
        self.clear()
    
    def acknowledge(self,by="unknown"):
        self.sm.event("acknowledge")
        logger.info("Alarm "+self.name +" acknowledged by" + by)
        if self.priority in ("error, critical","warnings"):
            messagebus.postMessage("/system/notifications", "Alarm "+self.name+" acknowledged by "+ by)

    def error(self):
        global unacknowledged
        self.sm.goto("error")
        with lock:
            if self.id in _unacknowledged:
                del _unacknowledged[self.id]
                unacknowledged = unacknowledged.copy()

