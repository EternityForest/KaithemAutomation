
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


from . import tagpoints,messagebus,widgets,pages
import weakref,threading,time
import cherrypy

inUsePins = weakref.WeakValueDictionary()

globalMockFactory = None


api = widgets.APIWidget()
api.require("/admin/settings.edit")

inputs = {}

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
        'p': p.pin
    }

def handleApiCall(u,v):
    if v[0]=="refresh":
        with lock:
            api.send(["inputs", {i:formatPin(inputs[i]()) for i in inputs}])

api.attach(handleApiCall)

class GPIOTag():
    def __init__(self,name, pin, comment=""):
        self.tag = tagpoints.Tag(name)
        self.pin=pin
        inUsePins[pin]=self

        #We can have 2 gpios, one real and one for testing
        self.realGpio=None
        self.fakeGpio=None

        #This is what we actually use.
        self.gpio=None
        self.lock=threading.RLock()

   

    def connectToPin(self,withclass,pin, *args,mock=None,**kwargs):
        global globalMockFactory

        from gpiozero import Device
        import gpiozero

        #Always keep a fake GPIO port for testing purposes
        from gpiozero.pins.mock import MockFactory
        if not globalMockFactory:
            globalMockFactory = MockFactory()
        self.fakeGpio = withclass(pin, *args,**kwargs,pin_factory=globalMockFactory)
        
        if not mock:
            try:
                self.gpio = withclass(pin, *args,**kwargs)
                self.realGpio = self.gpio

            except gpiozero.exc.BadPinFactory:
                messagebus.postMessage("/system/notifications/warnings", "No real GPIO found, using mock pins")
                self.gpio = self.fakeGpio
        else:
            self.gpio=self.fakeGpio
        self.gpio.when_activated = self._onActive
        self.gpio.when_deactivated = self._onInactive
        self.gpio.when_held = self._onHold

class DigitalInput(GPIOTag):
    def __init__(self, pin, *args,comment="",mock=None, **kwargs):

        GPIOTag.__init__(self, "/system/gpio/"+str(pin), pin,comment=comment)
        from gpiozero import Button,Device
        from gpiozero.pins.mock import MockFactory
        import gpiozero
        self.pin=pin
        self.comment=comment
        self.connectToPin(Button, pin, mock=mock,*args,**kwargs)
        self.phyclaim = self.tag.claim(self.gpio.value,"gpio", 60)
        self.lastPushed = 0
        

        if isinstance(gpiozero.Device.pin_factory,MockFactory):        
                if 'active_state' in kwargs:
                    if kwargs['active_state']:
                        active = True
                    else:
                        active=False
                else:
                    if  kwargs.get('pull_up',True):
                        active = False
                    else:
                        active=True
                if active:
                    Device.pin_factory.pin(pin).drive_low()
                else:
                    Device.pin_factory.pin(pin).drive_high()
        with lock:
            inputs[self.pin]=weakref.ref(self)
       


    def __del__(self):
        try:
            with lock:
                del inputs[self.pin]
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

    def releaseMocking(self):
        "Returns to reak GPIO mode"
        self._selectReal()

    def _onActive(self):
        messagebus.postMessage("/system/gpio/change"+str(self.pin),True)
        self.phyclaim.set(1)

        #Push all changes, but ratelimit. The UI will catch them later with
        #Polling. This is just for debugging and actual users will
        #Have their own thing, so a little lag is ok.
        t=time.time()
        if t-self.lastPushed>.2:
            api.send(['v',self.pin,True])
        self.lastPushed = time.time()

    def _onInactive(self):
        messagebus.postMessage("/system/gpio/change"+str(self.pin),False)
        self.phyclaim.set(0)
        t=time.time()
        if t-self.lastPushed>.2:
            api.send(['v',self.pin,False])
        self.lastPushed = time.time()

    def _onHold(self):
        messagebus.postMessage("/system/gpio/hold"+str(self.pin),True)
        self.phyclaim.set(0)
    
    def onChange(self, f):
        return messagebus.subscribe("/system/gpio/change"+str(self.pin),f)

    def onHold(self, f):
        return messagebus.subscribe("/system/gpio/hold/"+str(self.pin),f)

    def _selectReal(self):
        with self.lock:
            oldGpio = self.gpio
            if not self.realGpio:
                raise RuntimeError("Object has no real GPIO")
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