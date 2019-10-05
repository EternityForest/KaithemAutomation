
#Copyright Daniel Dunn 2019
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


from . import tagpoints,messagebus,widgets,pages, alerts
import weakref,threading,time,logging
import cherrypy

log =logging.getLogger("system")

inUsePins = weakref.WeakValueDictionary()

globalMockFactory = None


api = widgets.APIWidget()
api.require("/admin/settings.edit")

inputs = {}
outputs = {}

lock = threading.Lock()

lastPushedValue = 0


class WebInterface():
    @cherrypy.expose
    def index(self,**kwargs):
        pages.require("/admin/settings.edit")
        return pages.get_template("settings/gpio.html").render(api=api)

def formatPin(p):
    return{
        'v':p.tag.value,
        'c':p.comment,
        'm': p.gpio==p.fakeGpio,
        'p': p.pin,
        "a_s":p.activeState
    }


def formatOutputPin(p):
    return{
        'v':bool(p.gpio.value),
        'c':p.comment,
        'm': p.gpio==p.fakeGpio,
        'p': p.pin
    }


def handleApiCall(u,v):
    if v[0]=="refresh":
        with lock:
            api.send(["inputs", {i:formatPin(inputs[i]()) for i in inputs}])
            api.send(["outputs", {i:formatOutputPin(outputs[i]()) for i in outputs}])
    
    if v[0]=='mock':
        inputs[v[1]]().mockAlert.trip()
        inputs[v[1]]().setRawMockValue(v[2])

    if v[0]=='unmock':
        inputs[v[1]]().releaseMocking()

    if v[0]=='unforce':
        outputs[v[1]]().unforce()

    if v[0]=='force':
        outputs[v[1]]().force(v[2])

api.attach(handleApiCall)

#Only send one warning about no real GPIO to the front page
alreadySentMockWarning = False

class GPIOTag():
    def __init__(self,name, pin, comment=""):
        self.tag = tagpoints.Tag(name)
        self.pin=pin
        if pin in inUsePins:
            messagebus.postMessage("/system/notifications/warnings", "Pin already in use, old connection closed. The old pin will no longer correctly. If the old connection is unwanted, ignore this.")
            try:
                inUsePins[pin].mockAlert.clear()
            except:
                pass
            inUsePins[pin].close()


        inUsePins[pin]=self

        #We can have 2 gpios, one real and one for testing
        self.realGpio=None
        self.fakeGpio=None

        #This is what we actually use.
        self.gpio=None
        self.lock=threading.RLock()

    def close(self):
        try:
           self.realGpio.close()
        except:
            pass
        
        try:
            self.fakeGpio.close()
        except:
            pass

    def connectToPin(self,withclass,pin, *args,mock=None,**kwargs):
        global globalMockFactory

        from gpiozero import Device
        import gpiozero

        if not self.fakeGpio:
            #Always keep a fake GPIO port for testing purposes
            from gpiozero.pins.mock import MockFactory
            if not globalMockFactory:
                globalMockFactory = MockFactory()
            self.fakeGpio = withclass(pin, *args,**kwargs,pin_factory=globalMockFactory)

        if self.realGpio:
            raise RuntimeError("Already connected") 
        if not mock:
            try:
                self.gpio = withclass(pin, *args,**kwargs)
                self.realGpio = self.gpio

            except gpiozero.exc.BadPinFactory:
                global alreadySentMockWarning
                if not alreadySentMockWarning:
                    messagebus.postMessage("/system/notifications/warnings", "No real GPIO found, using mock pins")
                self.gpio = self.fakeGpio
                alreadySentMockWarning = True
        else:
            self.gpio=self.fakeGpio


class DigitalOutput(GPIOTag):
    requirePWM=False
    def __init__(self, pin, *args,comment="",mock=None, **kwargs):
        log.info("Claiming pin "+str(pin)+" as functionoutput")

        GPIOTag.__init__(self, "/system/gpio/"+str(pin), pin,comment=comment)
        from gpiozero import LED
        self.pin=pin
        self.comment=comment
        self.connectToPin(LED, pin, mock=mock,*args,**kwargs)

        # try:
        #     self.connectToPin(PWMLED, pin, mock=mock,*args,**kwargs)
        # except gpiozero.exc.PinPWMUnsupported:
        #     if not self.requirePWM:
        #         self.connectToPin(LED, pin, mock=mock,*args,**kwargs)
        #     else:
        #         raise
        self.lastPushed = 0

        self.overrideAlert = alerts.Alert("Pin"+str(pin)+"override")
        self.overrideAlert.description="Output pin overridden manually and ignoring changes to it's tagpoint"

        def tagHandler(val, ts, annotation):
            self.gpio.value = val>0.5

            t=time.time()
            #We show the actual pin value not the tag point value
            if t-self.lastPushed>.2:
                api.send(['o',self.pin,self.gpio.value > 0.5])
            self.lastPushed = time.time()

        self.tagHandler = tagHandler
        self.tag.setHandler(tagHandler)

        with lock:
            outputs[self.pin]=weakref.ref(self)
    
    def on(self):
        self.tag.value = 1

    def off(self):
        self.tag.value = 0

    def setState(self, val):
        self.tag.value = 1 if val else 0

    @property
    def value(self):
        return self.tag.value

    @value.setter
    def value(self,v):
        self.setState(v)

    def _on(self):
        self.gpio.on()

    def _off(self):
        self.gpio.off()

    
    def force(self,v):
        with lock:
            self.gpio=self.fakeGpio
            if v:
                self.realGpio.on()
            else:
                self.fakeGpio.off()
        api.send(["opin", self.pin, formatPin(self)])

    
    def unforce(self):
        with lock:
            if self.realGpio:
                self.gpio=self.realGpio
                self.gpio.value = self.tag.value>0.5
            else:
                raise RuntimeError("No real gpio")
        api.send(["opin", self.pin, formatPin(self)])


    def __del__(self):
        try:
            with lock:
                del outputs[self.pin]
        except:
            pass

        try:
            self.realGpio.close()
        except:
            pass

        
        try:
            self.fakeGpio.close()
        except:
            pass

class DigitalInput(GPIOTag):
    def __init__(self, pin, *args,comment="",mock=None, **kwargs):

        log.info("Claiming pin "+str(pin)+" as input")
        GPIOTag.__init__(self, "/system/gpio/"+str(pin), pin,comment=comment)
        from gpiozero import Button,Device
        from gpiozero.pins.mock import MockFactory
        import gpiozero
        self.pin=pin
        self.comment=comment
        self.connectToPin(Button, pin, mock=mock,*args,**kwargs)
        self._setInputCallbacks()
        self.phyclaim = self.tag.claim(self.gpio.value,"gpio", 60)
        self.lastPushed = 0

        #Only trip this alert if it's manually mocked. If it starts out
        #Mocled that isn't news most likely.
        self.mockAlert = alerts.Alert("Pin"+str(pin)+"mock",autoAck=True)
        self.mockAlert.description="Input pin is mocked and ignoring the physical iput pin"


        if 'active_state' in kwargs:
            if kwargs['active_state']:
                self.activeState = True
            else:
                self.activeState=False
        else:
            if  kwargs.get('pull_up',True):
                self.activeState = False
            else:
                self.activeState=True
            
        if isinstance(gpiozero.Device.pin_factory,MockFactory):        

                if  self.activeState:
                    Device.pin_factory.pin(pin).drive_low()
                else:
                    Device.pin_factory.pin(pin).drive_high()

        with lock:
            inputs[self.pin]=weakref.ref(self)
       
    @property
    def value(self):
        return self.tag.value

    def _setInputCallbacks(self):
        self.gpio.when_activated = self._onActive
        self.gpio.when_deactivated = self._onInactive
        self.gpio.when_held = self._onHold

    def _clearInputCallbacks(self):
        self.fakeGpio.when_activated=None
        self.fakeGpio.when_deactivated=None
        self.fakeGpio.when_deactivated=None


    def __del__(self):
        try:
            with lock:
                del inputs[self.pin]
        except:
            pass

        try:
            self.realGpio.close()
        except:
            pass

        try:
            self.fakeGpio.close()
        except:
            pass

    def setRawMockValue(self, value):
        "Sets the pin to fake mode, and then sets a specific high or low mock val"
        #Dynamic import, we just accept that this one is slow because it's just for testing
        import gpiozero
       
        self._selectFake()
        if value:
            globalMockFactory.pin(self.pin).drive_high()
        else:
            globalMockFactory.pin(self.pin).drive_low()
        
        api.send(["ipin", self.pin, formatPin(self)])

    def releaseMocking(self):
        "Returns to reak GPIO mode"
        self._selectReal()
        api.send(["ipin", self.pin, formatPin(self)])

    def _onActive(self):
        messagebus.postMessage("/system/gpio/change/"+str(self.pin),True)
        messagebus.postMessage("/system/gpio/active/"+str(self.pin),True)

        self.phyclaim.set(1)

        #Push all changes, but ratelimit. The UI will catch them later with
        #Polling. This is just for debugging and actual users will
        #Have their own thing, so a little lag is ok.
        t=time.time()
        if t-self.lastPushed>.2:
            api.send(['v',self.pin,True])
        self.lastPushed = time.time()

    def _onInactive(self):
        messagebus.postMessage("/system/gpio/change/"+str(self.pin),False)
        messagebus.postMessage("/system/gpio/inactive/"+str(self.pin),False)

        self.phyclaim.set(0)
        t=time.time()
        if t-self.lastPushed>.2:
            api.send(['v',self.pin,False])
        self.lastPushed = time.time()

    def _onHold(self):
        messagebus.postMessage("/system/gpio/hold/"+str(self.pin),True)
    
      
    def onActive(self, f):
        return messagebus.subscribe("/system/gpio/active/"+str(self.pin),f)
          
    def onInactive(self, f):
        return messagebus.subscribe("/system/gpio/inactive/"+str(self.pin),f)

    def onChange(self, f):
        return messagebus.subscribe("/system/gpio/change/"+str(self.pin),f)

    def onHold(self, f):
        return messagebus.subscribe("/system/gpio/hold/"+str(self.pin),f)

    def _selectReal(self):
        with self.lock:
            oldGpio = self.gpio
            if not self.realGpio:
                raise RuntimeError("Object has no real GPIO")
            self.mockAlert.clear()

            if self.gpio==self.realGpio:
                return
            self.fakeGpio.when_activated=None
            self.fakeGpio.when_deactivated=None
            self.fakeGpio.when_deactivated=None

            self.gpio = self.realGpio
            self.gpio.when_activated = self._onActive
            self.gpio.when_deactivated = self._onInactive
            self.gpio.when_held = self._onHold


            #The value may have effectively just changed
            if not oldGpio==self.realGpio:
                if self.gpio.value:
                    self.phyclaim.set(1)
                    if  not self.fakeGpio.value:
                        self._onActive()
                else:
                    self.phyclaim.set(0)
                    if not self.fakeGpio.value:
                        self._onInactive()

    def _selectFake(self):
        with self.lock:
            if self.gpio==self.fakeGpio:
                return
            oldGpio = self.gpio
            if self.realGpio:
                self.realGpio.when_activated=None
                self.realGpio.when_deactivated=None
                self.realGpio.when_deactivated=None
            
            self.gpio = self.fakeGpio
            self.gpio.when_activated = self._onActive
            self.gpio.when_deactivated = self._onInactive
            self.gpio.when_held = self._onHold

            if not oldGpio==self.fakeGpio:
                if self.gpio.value:
                    self.phyclaim.set(1)
                    if self.realGpio and not self.realGpio.value:
                        self._onActive()
                else:
                    self.phyclaim.set(0)
                    if self.realGpio and self.realGpio.value:
                        self._onInactive()
