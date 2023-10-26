
from . thirdparty import baresipy
import weakref
from . import jacktools
import time


def wrapFunction(f):
    f = weakref.ref(f)

    def f2(*a, **k):
        f(*a, **k)
    return f2


class LocalBareSIP(baresipy.BareSIP):
    def __init__(self, *a, jackSink=None, jackSource=None, **k):
        super().__init__(pwd='', gateway='', *a, **k)
        self.jackSink = jackSink
        self.jackSource = jackSource

        self.useJack = jackSink or jackSource
        self.mostRecentCall = ''
        self.jackName = "baresip-01"
        self.jackOutName = "baresip"

    def call(self, number):
        self.mostRecentCall = number
        super().call(self, number)

    def handle_incoming_call(self, number):
        time.sleep(0.1)
        self.controller().onIncomingCall(number)
        self.mostRecentCall = number

    def handle_call_established(self):
        if self.useJack:
            # Assume we don't know which one is which.
            jn1=self.jackNames[0]
            jn2= self.jackNames[1]

            if self.jackSource:
                self.controller().inJackAirwire = jacktools.Airwire(self.jackSource, jn1)
                self.controller().inJackAirwire2 = jacktools.Airwire(self.jackSource,jn2)
                self.controller().inJackAirwire.connect()
                self.controller().inJackAirwire2.connect()

            if self.jackSink:
                self.controller().outJackAirwire = jacktools.Airwire(jn1, self.jackSink)
                self.controller().outJackAirwire2 = jacktools.Airwire(jn2, self.jackSink)
                self.controller().outJackAirwire2.connect()
                self.controller().outJackAirwire.connect()

            self.controller().onIncomingCall(self.mostRecentCall)

            # Undo the system connection it will try to do.
            if not self.jackSink == 'system':
                outPorts = jacktools.getPorts(
                    jn1+":*", is_output=True, is_audio=True)
                outPorts += jacktools.getPorts(jn2 +
                                          ":*", is_output=True, is_audio=True)

                inPorts = jacktools.getPorts(
                    "system:*", is_input=True, is_audio=True)
                for i in outPorts:
                    for j in inPorts:
                        jacktools.disconnect(i.name, j.name)

            if not self.jackSource == 'system':
                inPorts = jacktools.getPorts(
                    jn1+":*", is_input=True, is_audio=True)
                inPorts += jacktools.getPorts(jn2+":*",
                                         is_input=True, is_audio=True)
                outPorts = jacktools.getPorts(
                    "system:*", is_output=True, is_audio=True)
                for i in outPorts:
                    for j in inPorts:
                        jacktools.disconnect(i.name, j.name)

    def onJackEstablished(self, name):
        if self.useJack:
            self.controller().inJackAirwire = jacktools.Airwire(
                self.controller().jackSource, self.jackName)
            self.controller().outJackAirwire = jacktools.Airwire(
                self.controller().jackSink, self.jackName)


class SipUserAgent():
    def __init__(self, username, audioDriver="alsa,default", port=5060, jackSource=None, jackSink=None):
        super().__init__()
        self.agent = LocalBareSIP(username, audiodriver=audioDriver,
                                  port=port, jackSource=jackSource, jackSink=jackSink, block=False)
        self.agent.controller = weakref.ref(self)

    def __del__(self):
        self.agent.quit()

    def call(self, number):
        self.agent.call(number)
    
    def hang(self):
        self.agent.hang()

    def onIncomingCall(self, number):
        print(number)
        self.accept()
        time.sleep(8)
        self.accept()

    def accept(self):
        self.agent.accept_call()

    def close(self):
        self.agent.quit()

