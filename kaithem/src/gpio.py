
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


from . import tagpoints, messagebus, widgets, pages, alerts
import weakref
import threading
import time
import logging
import cherrypy

log = logging.getLogger("system")

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
    def index(self, **kwargs):
        pages.require("/admin/settings.edit")
        return pages.get_template("settings/gpio.html").render(api=api)


def formatPin(p):
    return{
        'v': p.tag.value,
        'c': p.comment,
        'm': p.gpio == p.fakeGpio,
        'p': p.pin,
        "a_s": p.activeState
    }


def formatOutputPin(p):
    return{
        'v': bool(p.gpio.value),
        'c': p.comment,
        'm': p.forced,
        'p': p.pin,
        "a_s": p.activeState

    }


def handleApiCall(u, v):
    if v[0] == "refresh":
        with lock:
            api.send(["inputs", {i: formatPin(inputs[i]()) for i in inputs}])
            api.send(
                ["outputs", {i: formatOutputPin(outputs[i]()) for i in outputs}])

    elif v[0] == 'mock':
        inputs[v[1]]().mock_alert.trip()
        inputs[v[1]]().set_raw_mock_value(v[2])

    elif v[0] == 'unmock':
        try:
            inputs[v[1]]().release_mocking()
        except NoRealGPIOError:
            api.send(['norealgpio'])

    elif v[0] == 'unforce':
        try:
            outputs[v[1]]().unforce()
        except NoRealGPIOError:
            api.send(['norealgpio'])

    elif v[0] == 'force':
        outputs[v[1]]().force(v[2])
    else:
        raise ValueError("Unrecognized command "+str(v[0]))


api.attach(handleApiCall)

# Only send one warning about no real GPIO to the front page
alreadySentMockWarning = False


class GPIOTag():
    def __init__(self, name, pin, comment=""):
        self.tag = tagpoints.Tag(name)
        self.tag.max = 1
        self.tag.min = 0
        self.pin = pin
        if pin in inUsePins:
            messagebus.postMessage("/system/notifications/warnings",
                                   "Pin already in use, old connection closed. The old pin will no longer correctly. If the old connection is unwanted, ignore this.")
            try:
                inUsePins[pin].mock_alert.clear()
            except Exception:
                pass
            inUsePins[pin].close()

        inUsePins[pin] = self

        # We can have 2 gpios, one real and one for testing
        self.realGpio = None
        self.fakeGpio = None

        # This is what we actually use.
        self.gpio = None
        self.lock = threading.RLock()

    def close(self):
        try:
            self.realGpio.close()
        except Exception:
            pass

        try:
            self.fakeGpio.close()
        except Exception:
            pass

    def connect_to_pin(self, withclass, pin, *args, mock=None, **kwargs):
        global globalMockFactory

        from gpiozero import Device
        import gpiozero

        kwargs = kwargs.copy()
        # Rename because this was very confusing
        if "pull" in kwargs:
            kwargs['pull_up'] = kwargs['pull']
            del kwargs['pull']

        if mock:
            if self.realGpio:
                try:
                    self.realGpio.close()
                except Exception:
                    pass
                self.realGpio = None

            if not self.fakeGpio:
                from gpiozero.pins.mock import MockFactory
                if not globalMockFactory:
                    globalMockFactory = MockFactory()
                if not globalMockFactory:
                    raise RuntimeError("problem")
                self.fakeGpio = withclass(
                    pin, *args, **kwargs, pin_factory=globalMockFactory)
            self.gpio = self.fakeGpio
        else:
            if self.fakeGpio:
                try:
                    self.fakeGpio.close()
                except Exception:
                    pass
                self.fakeGpio = None
            try:
                if not self.realGpio:
                    self.gpio = withclass(pin, *args, **kwargs)
                self.realGpio = self.gpio

            except gpiozero.exc.BadPinFactory:
                global alreadySentMockWarning
                if not alreadySentMockWarning:
                    messagebus.postMessage(
                        "/system/notifications/warnings", "No real GPIO found, using mock pins")

                # Redo in mock mode
                self.connect_to_pin(withclass, pin, *args, mock=True, **kwargs)
                alreadySentMockWarning = True


class NoRealGPIOError(RuntimeError):
    pass


class DigitalOutput(GPIOTag):
    PWM = False

    def __init__(self, pin, *args, comment="", mock=None, **kwargs):
        log.info("Claiming pin "+str(pin)+" as functionoutput")

        GPIOTag.__init__(self, "/system/gpio/"+str(pin), pin, comment=comment)
        from gpiozero import LED, PWMLED
        self.pin = pin
        self.comment = comment

        def pinSwitchFunc(doMock):
            # Switch to the appropriate mock or real pin
            self.connect_to_pin(PWMLED if self.PWM else LED, pin, mock=doMock, *args, **kwargs)
        self.pinSwitchFunc = pinSwitchFunc
        self.pinSwitchFunc(mock)

        self.activeState = kwargs.get('active_high', True)

        self.lastPushed = 0

        self.overrideAlert = alerts.Alert("Pin"+str(pin)+"override")
        self.overrideAlert.description = "Output pin overridden manually and ignoring changes to it's tagpoint"

        self.forced = False

        def tagHandler(val, ts, annotation):
            if self.forced:
                return

            if self.PWM:
                self.gpio.val = val
            else:
                self.gpio.value = val > 0.5

            t = time.time()
            # We show the actual pin value not the tag point value
            if t-self.lastPushed > .2:
                api.send(['o', self.pin, self.gpio.value > (0.5 if not self.PWM else 0.0001)])
            self.lastPushed = time.time()

        self.tagHandler = tagHandler
        self.tag.setHandler(tagHandler)

        with lock:
            outputs[self.pin] = weakref.ref(self)

        # Tag may have gotten here before we did!
        self.setState(self.tag.value > 0.5)

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
    def value(self, v):
        self.setState(v)

    def force(self, v):
        with lock:
            self.forced = True
            if v:
                self.gpio.on()
            else:
                self.gpio.off()
        api.send(["opin", self.pin, formatOutputPin(self)])

    def unforce(self):
        with lock:
            self.forced = False
            self.gpio.value = self.tag.value > 0.5
        api.send(["opin", self.pin, formatOutputPin(self)])

    def __del__(self):
        try:
            with lock:
                del outputs[self.pin]
        except Exception:
            pass

        try:
            self.realGpio.close()
        except Exception:
            pass

        try:
            self.fakeGpio.close()
        except Exception:
            pass
        
class PWMOutput(DigitalOutput):
    PWM=True

class DigitalInput(GPIOTag):
    def __init__(self, pin, *args, comment="", mock=None, **kwargs):

        log.info("Claiming pin "+str(pin)+" as input")
        GPIOTag.__init__(self, "/system/gpio/"+str(pin), pin, comment=comment)
        from gpiozero import Button, Device
        from gpiozero.pins.mock import MockFactory
        import gpiozero
        self.lastInactive = time.monotonic()
        self.holdWaiter = None

        self.pin = pin
        self.comment = comment

        def pinSwitchFunc(doMock):
            # Switch to the appropriate mock or real pin
            self.connect_to_pin(Button, pin, mock=doMock, *args, **kwargs)
        self.pinSwitchFunc = pinSwitchFunc
        self.pinSwitchFunc(mock)

        if not mock:
            self._setInputCallbacks()
        self.phyclaim = self.tag.claim(self.gpio.value, "gpio", 60)
        self.lastPushed = 0

        # Only trip this alert if it's manually mocked. If it starts out
        # Mocled that isn't news most likely.
        self.mock_alert = alerts.Alert("Pin"+str(pin)+"mock", autoAck=True)
        self.mock_alert.description = "Input pin is mocked and ignoring the physical iput pin"

        if 'active_state' in kwargs:
            if kwargs['active_state']:
                self.activeState = True
            else:
                self.activeState = False
        else:
            if kwargs.get("pull", kwargs.get('pull_up', True)):
                self.activeState = False
            else:
                self.activeState = True

        if mock:
            if self.activeState:
                globalMockFactory.pin(self.pin).drive_low()
            else:
                globalMockFactory.pin(self.pin).drive_high()

        with lock:
            inputs[self.pin] = weakref.ref(self)

    @property
    def value(self):
        return self.tag.value

    def _setInputCallbacks(self):
        self.gpio.when_activated = self._onActive
        self.gpio.when_deactivated = self._onInactive
        self.gpio.when_held = self._onHold

    def __del__(self):
        try:
            with lock:
                del inputs[self.pin]
        except Exception:
            pass

        try:
            self.realGpio.close()
        except Exception:
            pass

        try:
            self.fakeGpio.close()
        except Exception:
            pass

    def set_raw_mock_value(self, value):
        "Sets the pin to fake mode, and then sets a specific high or low mock val"
        # Dynamic import, we just accept that this one is slow because it's just for testing
        import gpiozero

        self._selectFake(value)

        api.send(["ipin", self.pin, formatPin(self)])

    def release_mocking(self):
        "Returns to reak GPIO mode"
        self._selectReal()
        api.send(["ipin", self.pin, formatPin(self)])

    def _onActive(self):

        # Now was the last time it WAS inactive, this is the moment it starts being active
        self.lastInactive = time.monotonic()

        messagebus.postMessage("/system/gpio/change/"+str(self.pin), True)
        messagebus.postMessage("/system/gpio/active/"+str(self.pin), True)

        self.phyclaim.set(1)

        # Push all changes, but ratelimit. The UI will catch them later with
        # Polling. This is just for debugging and actual users will
        # Have their own thing, so a little lag is ok.
        t = time.time()
        if t-self.lastPushed > .2:
            api.send(['v', self.pin, True])
        self.lastPushed = time.time()

    def _onInactive(self):
        self.lastInactive = time.monotonic()
        messagebus.postMessage("/system/gpio/change/"+str(self.pin), False)
        messagebus.postMessage("/system/gpio/inactive/"+str(self.pin), False)

        self.phyclaim.set(0)
        t = time.time()
        if t-self.lastPushed > .2:
            api.send(['v', self.pin, False])
        self.lastPushed = time.time()

    def _onHold(self):
        messagebus.postMessage("/system/gpio/hold/"+str(self.pin), True)

    def on_active(self, f):
        return messagebus.subscribe("/system/gpio/active/"+str(self.pin), f)

    def on_inactive(self, f):
        return messagebus.subscribe("/system/gpio/inactive/"+str(self.pin), f)

    def on_change(self, f):
        return messagebus.subscribe("/system/gpio/change/"+str(self.pin), f)

    def on_hold(self, f):
        return messagebus.subscribe("/system/gpio/hold/"+str(self.pin), f)

    def _selectReal(self):
        with self.lock:

            wasReal = self.gpio and self.gpio == self.realGpio
            if wasReal:
                return

            oldValue = self.gpio.value

            self.pinSwitchFunc(False)
            if not self.realGpio:
                raise NoRealGPIOError("Object has no real GPIO")
            if self.holdWaiter:
                self.holdWaiter.join()
            self.holdWaiter = None
            self.mock_alert.clear()

            if self.fakeGpio:
                self.fakeGpio.when_activated = None
                self.fakeGpio.when_deactivated = None
                self.fakeGpio.when_deactivated = None

            self.gpio = self.realGpio
            self.gpio.when_activated = self._onActive
            self.gpio.when_deactivated = self._onInactive
            self.gpio.when_held = self._onHold

            if self.gpio.value:
                self.phyclaim.set(1)
                if not oldValue:
                    self._onActive()
            else:
                self.phyclaim.set(0)
                if oldValue:
                    self._onInactive()

    def _selectFake(self, rawv):
        with self.lock:

            if self.realGpio:
                self.realGpio.when_activated = None
                self.realGpio.when_deactivated = None
                self.realGpio.when_deactivated = None

                oldValue = self.gpio.value
            else:
                oldValue = self.phyclaim.value

            self.pinSwitchFunc(True)

            # Set the claim as if the new value was the thing, don't use the builtin
            # Mock stuff
            if self.activeState:
                self.phyclaim.set(1 if rawv else 0)
            else:
                self.phyclaim.set(0 if rawv else 1)

            self.gpio = self.fakeGpio

            if not oldValue == self.phyclaim.value:
                if self.phyclaim.value:
                    self._onActive()

                    def f():
                        # Wait until it's been long enough
                        while (time.monotonic()-self.lastInactive < self.fakeGpio.hold_time):
                            if self.realGpio:
                                return
                            if self.phyclaim.value < 0.5:
                                return
                            time.sleep(0.01)
                        self._onHold()

                    self.holdWaiter = threading.Thread(target=f, daemon=True)
                    self.holdWaiter.start()
                else:
                    self.lastInactive = time.monotonic()
                    self.phyclaim.set(0)
                    self._onInactive()
                    # Wait for stop
                    if self.holdWaiter:
                        self.holdWaiter.join()
                    self.holdWaiter = None
