from src import statemachines,widgets
import logging,threading

logger = logging.getLogger("system.alerts")

lock = threading.Lock()

#This is a dict of all alerts that have not yet been acknowledged.
#It is immutable and only ever atomically replaces
unacknowledged = {}

#Same as above except may be mutated under lock
_unacknowledged = {}

priorities  ={
    'debug': 10,
    'info':20,
    'warning': 30,
    'error':40,
    'critical': 50
}

def highestUnacknowledged():
    with lock:
    l = -1
    for i in unacknowledged:
        i = i()
        if i:
            if (priorities[i.priority] if not i.sm.state=="error" else 40) > l:
                l = i.priority
    return l



class Alert():
    def __init__(name, priority="normal", zone=None, tripDelay=0, autoAck=False,
                permissions=[], ackPermissions=[]
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
        is there any need for unique names.
        """

        permissions    = permissions + ['/users/alarms.view']
        ackPermissions = permissions + ['users/alarms.acknowledge']

        self.priority = priority
        self.zone = zone
        self.name = name
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
            self.sm.setTimer("cleared",ackOnClear,"normal")
        
        self.sm.addRule("normal", "trip","tripped")
        self.sm.addRule("active","acknowledge","acknowledge")
        self.sm.addRule("active","release","cleared")
        self.sm.addRule("acknowledged","release","normal")
        self.sm.addRule("error","release","normal")

        #Widget used to show alarm status.
        self.widget = AlarmWidget(self)

    #I don't like the undefined thread aspec of __del__. Change this?    
    def _onActive(self, machine):
        with lock:
            _unacknowledged[id(self)] = weakref.ref(self)
            unacknowledged = unacknowleged.copy()

    def _onAck(self, machine):
        "Called both when acknowledged, and when released."
        with lock:
            del _unacknowledged(self.id)
            unacknowledged = unacknowleged.copy()

    def trip(self):
        self.sm.event("trip")
    
    def clear(self):
        self.sm.event("release")
    
    def acknowledge(self):
        self.sm.event("acknowledge")
    
    def error(self):
        self.sm.goto("error")
        with lock:
            del _unacknowledged(self.id)
            unacknowledged = unacknowleged.copy()