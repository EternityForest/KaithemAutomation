# GPIO Zero: a library for controlling the Raspberry Pi's GPIO pins
# Copyright (c) 2016-2019 Dave Jones <dave@waveform.org.uk>
# Copyright (c) 2016-2019 Andrew Scheller <github@loowis.durge.org>
# Copyright (c) 2019 Ben Nuttall <ben@bennuttall.com>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its contributors
#   may be used to endorse or promote products derived from this software
#   without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import (
    unicode_literals,
    print_function,
    absolute_import,
    division,
)
str = type('')


class GPIOZeroError(Exception):
    "Base class for all exceptions in GPIO Zero"

class DeviceClosed(GPIOZeroError):
    "Error raised when an operation is attempted on a closed device"

class BadEventHandler(GPIOZeroError, ValueError):
    "Error raised when an event handler with an incompatible prototype is specified"

class BadWaitTime(GPIOZeroError, ValueError):
    "Error raised when an invalid wait time is specified"

class BadQueueLen(GPIOZeroError, ValueError):
    "Error raised when non-positive queue length is specified"

class BadPinFactory(GPIOZeroError, ImportError):
    "Error raised when an unknown pin factory name is specified"

class ZombieThread(GPIOZeroError, RuntimeError):
    "Error raised when a thread fails to die within a given timeout"

class CompositeDeviceError(GPIOZeroError):
    "Base class for errors specific to the CompositeDevice hierarchy"

class CompositeDeviceBadName(CompositeDeviceError, ValueError):
    "Error raised when a composite device is constructed with a reserved name"

class CompositeDeviceBadOrder(CompositeDeviceError, ValueError):
    "Error raised when a composite device is constructed with an incomplete order"

class CompositeDeviceBadDevice(CompositeDeviceError, ValueError):
    "Error raised when a composite device is constructed with an object that doesn't inherit from :class:`Device`"

class EnergenieSocketMissing(CompositeDeviceError, ValueError):
    "Error raised when socket number is not specified"

class EnergenieBadSocket(CompositeDeviceError, ValueError):
    "Error raised when an invalid socket number is passed to :class:`Energenie`"

class EnergenieBadInitialValue(CompositeDeviceError, ValueError):
    "Error raised when an invalid initial value is passed to :class:`Energenie`"

class SPIError(GPIOZeroError):
    "Base class for errors related to the SPI implementation"

class SPIBadArgs(SPIError, ValueError):
    "Error raised when invalid arguments are given while constructing :class:`SPIDevice`"

class SPIBadChannel(SPIError, ValueError):
    "Error raised when an invalid channel is given to an :class:`AnalogInputDevice`"

class SPIFixedClockMode(SPIError, AttributeError):
    "Error raised when the SPI clock mode cannot be changed"

class SPIInvalidClockMode(SPIError, ValueError):
    "Error raised when an invalid clock mode is given to an SPI implementation"

class SPIFixedBitOrder(SPIError, AttributeError):
    "Error raised when the SPI bit-endianness cannot be changed"

class SPIFixedSelect(SPIError, AttributeError):
    "Error raised when the SPI select polarity cannot be changed"

class SPIFixedWordSize(SPIError, AttributeError):
    "Error raised when the number of bits per word cannot be changed"

class SPIInvalidWordSize(SPIError, ValueError):
    "Error raised when an invalid (out of range) number of bits per word is specified"

class GPIODeviceError(GPIOZeroError):
    "Base class for errors specific to the GPIODevice hierarchy"

class GPIODeviceClosed(GPIODeviceError, DeviceClosed):
    "Deprecated descendent of :exc:`DeviceClosed`"

class GPIOPinInUse(GPIODeviceError):
    "Error raised when attempting to use a pin already in use by another device"

class GPIOPinMissing(GPIODeviceError, ValueError):
    "Error raised when a pin specification is not given"

class InputDeviceError(GPIODeviceError):
    "Base class for errors specific to the InputDevice hierarchy"

class OutputDeviceError(GPIODeviceError):
    "Base class for errors specified to the OutputDevice hierarchy"

class OutputDeviceBadValue(OutputDeviceError, ValueError):
    "Error raised when ``value`` is set to an invalid value"

class PinError(GPIOZeroError):
    "Base class for errors related to pin implementations"

class PinInvalidFunction(PinError, ValueError):
    "Error raised when attempting to change the function of a pin to an invalid value"

class PinInvalidState(PinError, ValueError):
    "Error raised when attempting to assign an invalid state to a pin"

class PinInvalidPull(PinError, ValueError):
    "Error raised when attempting to assign an invalid pull-up to a pin"

class PinInvalidEdges(PinError, ValueError):
    "Error raised when attempting to assign an invalid edge detection to a pin"

class PinInvalidBounce(PinError, ValueError):
    "Error raised when attempting to assign an invalid bounce time to a pin"

class PinSetInput(PinError, AttributeError):
    "Error raised when attempting to set a read-only pin"

class PinFixedPull(PinError, AttributeError):
    "Error raised when attempting to set the pull of a pin with fixed pull-up"

class PinEdgeDetectUnsupported(PinError, AttributeError):
    "Error raised when attempting to use edge detection on unsupported pins"

class PinUnsupported(PinError, NotImplementedError):
    "Error raised when attempting to obtain a pin interface on unsupported pins"

class PinSPIUnsupported(PinError, NotImplementedError):
    "Error raised when attempting to obtain an SPI interface on unsupported pins"

class PinPWMError(PinError):
    "Base class for errors related to PWM implementations"

class PinPWMUnsupported(PinPWMError, AttributeError):
    "Error raised when attempting to activate PWM on unsupported pins"

class PinPWMFixedValue(PinPWMError, AttributeError):
    "Error raised when attempting to initialize PWM on an input pin"

class PinUnknownPi(PinError, RuntimeError):
    "Error raised when gpiozero doesn't recognize a revision of the Pi"

class PinMultiplePins(PinError, RuntimeError):
    "Error raised when multiple pins support the requested function"

class PinNoPins(PinError, RuntimeError):
    "Error raised when no pins support the requested function"

class PinInvalidPin(PinError, ValueError):
    "Error raised when an invalid pin specification is provided"

class GPIOZeroWarning(Warning):
    "Base class for all warnings in GPIO Zero"

class DistanceSensorNoEcho(GPIOZeroWarning):
    "Warning raised when the distance sensor sees no echo at all"

class SPIWarning(GPIOZeroWarning):
    "Base class for warnings related to the SPI implementation"

class SPISoftwareFallback(SPIWarning):
    "Warning raised when falling back to the SPI software implementation"

class PWMWarning(GPIOZeroWarning):
    "Base class for PWM warnings"

class PWMSoftwareFallback(PWMWarning):
    "Warning raised when falling back to the PWM software implementation"

class PinWarning(GPIOZeroWarning):
    "Base class for warnings related to pin implementations"

class PinFactoryFallback(PinWarning):
    "Warning raised when a default pin factory fails to load and a fallback is tried"

class PinNonPhysical(PinWarning):
    "Warning raised when a non-physical pin is specified in a constructor"

class ThresholdOutOfRange(GPIOZeroWarning):
    "Warning raised when a threshold is out of range specified by min and max values"

class CallbackSetToNone(GPIOZeroWarning):
    "Warning raised when a callback is set to None when its previous value was None"

class AmbiguousTone(GPIOZeroWarning):
    "Warning raised when a Tone is constructed with an ambiguous number"
