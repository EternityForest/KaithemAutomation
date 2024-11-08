# Math for the first order filter
# v is our state, k is a constant, and i is input.

# At each timestep of one, we do:
# v = v*(1-k) + i*k

# moving towards the input with sped determined by k.
# We can reformulate that as explicitly taking the difference, and moving along portion of it
# v = (v+((i-v)*k))

# We can show this reformulation is correct with XCas:
# solve((v*(1-k) + i*k) - (v+((i-v)*k)) =x,x)

# x is 0, because the two equations are always the same.

# Now we use 1-k instead, such that k now represents the amount of difference allowed to remain.
# Higher k is slower.
# (v+((i-v)*(1-k)))

# Twice the time means half the remaining difference, so we are going to raise k to the power of the number of timesteps
# at each round to account for the uneven timesteps we are using:
# v = (v+((i-v)*(1-(k**t))))

# Now we need k such that v= 1/e when starting at 1 going to 0, with whatever our value of t is.
# So we substitute 1 for v and 0 for i, and solve for k:
# solve(1/e = (1+((0-1)*(1-(k**t)))),k)

# Which gives us k=exp(-(1/t))

import math
import threading
import time

from kaithem.src.tagpoints import Tag


class Filter:
    pass


class LowpassFilter(Filter):
    def __init__(self, name, inputTag, timeConstant, priority=60, interval=-1):
        self.state = inputTag.value
        self.filtered = self.state
        self.lastRanFilter = time.monotonic()
        self.lastState = self.state

        # All math derived with XCas
        self.k = math.exp(-(1 / timeConstant))
        self.lock = threading.Lock()

        self.inputTag = inputTag
        inputTag.subscribe(self.doInput)

        self.tag = Tag(name)
        self.claim = self.tag.claim(
            self.getter, name=f"{inputTag.name}.lowpass", priority=priority
        )

        if interval is None:
            self.tag.interval = timeConstant / 2
        else:
            self.tag.interval = interval

    def doInput(self, val, ts, annotation):
        "On new data, we poll the output tag which also loads the input tag data."
        self.tag.poll()

    def getter(self):
        self.state = self.inputTag.value

        # Get the average state over the last period
        state = (self.state + self.lastState) / 2
        t = time.monotonic() - self.lastRanFilter
        self.filtered = self.filtered + (
            (state - self.filtered) * (1 - (self.k**t))
        )
        self.lastRanFilter += t

        self.lastState = self.state

        # Suppress extremely small changes that lead to ugly decimals and network traffic
        if abs(self.filtered - self.state) < (self.filtered / 1000000.0):
            return self.state
        else:
            return self.filtered


class HighpassFilter(LowpassFilter):
    def getter(self):
        self.state = self.inputTag.value

        # Get the average state over the last period
        state = (self.state + self.lastState) / 2
        t = time.monotonic() - self.lastRanFilter
        self.filtered = self.filtered + (
            (state - self.filtered) * (1 - (self.k**t))
        )
        self.lastRanFilter += t

        self.lastState = self.state

        s = self.state - self.filtered

        # Suppress extremely small changes that lead to ugly decimals and network traffic
        if abs(s) < (0.0000000000000001):
            return 0
        else:
            return s


# class HysteresisFilter(Filter):
#     def __init__(self, name, inputTag, hysteresis=0, priority=60):
#         self.state = inputTag.value

#         # Start at midpoint with the window centered
#         self.hysteresisUpper = self.state + hysteresis / 2
#         self.hysteresisLower = self.state + hysteresis / 2
#         self.lock = threading.Lock()

#         self.inputTag = inputTag
#         inputTag.subscribe(self.doInput)

#         self.tag = _NumericTagPoint(name)
#         self.claim = self.tag.claim(
#             self.getter, name=inputTag.name + ".hysteresis", priority=priority)

#     def doInput(self, val, ts, annotation):
#         "On new data, we poll the output tag which also loads the input tag data."
#         self.tag.poll()

#     def getter(self):
#         with self.lock:
#             self.lastState = self.state

#             if val >= self.hysteresisUpper:
#                 self.state = val
#                 self.hysteresisUpper = val
#                 self.hysteresisLower = val - self.hysteresis
#             elif val <= self.hysteresisLower:
#                 self.state = val
#                 self.hysteresisUpper = val + self.hysteresis
#                 self.hysteresisLower = val
#             return self.state
