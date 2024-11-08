# SPDX-FileCopyrightText: Copyright 2024 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import math
import random
import time
import weakref
from typing import Any, Dict, Tuple

import numpy
import numpy.typing

from . import universes

rand_table = [random.randint(0, 255) for i in range(1024)]
rand_counter = 0


# This takes 7us, random.randint takes like 80us,
# normal variates take 40us, so we use this to look up normal variates in
# a table
def fast_rand_255():
    global rand_counter
    rand_counter = (rand_counter + 1) % 1024
    if rand_counter == 0:
        rand_table[random.randint(0, 1023)] = random.randint(0, 255)
        rand_counter = random.randint(0, 1023)
    return rand_table[rand_counter]


def getUniverse(u: str):
    "Get strong ref to universe if it exists, else get none."
    try:
        oldUniverseObj = universes.universes[u]()
    except KeyError:
        oldUniverseObj = None
    return oldUniverseObj


def getblenddesc(mode: str):
    if mode == "gel" or mode == "multiply":
        return "The final value is produced by multiplying the values together"
    elif mode == "inhibit":
        return "The final value is the lower of the value in this group and the rendered value below it"
    elif mode == "HTP":
        return "The highest of the this group's values and the values below it take effect"

    try:
        return blendmodes[mode].description
    except Exception:
        try:
            return blendmodes[mode].__doc__
        except Exception:
            return ""


class BlendMode:
    default_channel_value = 0
    always_rerender = False
    parameters: Dict[str, Tuple[str, str, str, str | bool | float]] = {}
    autoStop = True

    def __init__(self, group) -> None:
        self.blend_args: Dict[str, int | float | str] = {}

        if hasattr(self.__class__, "parameters"):
            for i in self.__class__.parameters:
                if i not in self.blend_args:
                    self.blend_args[i] = self.__class__.parameters[i][3]

    def frame(self, u, old, values, alphas, alpha):
        return old


class HardcodedBlendMode(BlendMode):
    # True of blend mode is dynamic
    always_rerender = False
    "Indicates that the blend mode is hardcoded in applyLayer"


blendmodes: weakref.WeakValueDictionary[str, Any] = (
    weakref.WeakValueDictionary()
)


def makeBlankArray(count, v=0):
    x = [v] * count
    return numpy.array(x, dtype="f4")


class flicker_blendmode(BlendMode):
    "Blend mode based on physical model flickering"

    always_rerender = True
    parameters = {
        "gustiness": ("Gustiness", "number", "", 0.17),
        "lowpass": ("Lowpass", "number", "", 0.19),
        "topple_chance": ("Windiness", "number", "", 0.07),
        "agility": ("Flame agility", "number", "", 0.02),
        "group": (
            "Group",
            "number",
            "Groups of this many channels flicker together, e.g. to make RGB look right",
            3,
        ),
    }
    description = """Effects layer that simulate a natural flame-like flickering effect.
    Channel value determines how much flicker to apply to that channel.
    To use this, add a layer below containing the base colors.
    The flicker layer will randomly darken them according to it's simulation algorithm."""

    def __init__(self, group):
        BlendMode.__init__(self, group)
        self.group = group

        self.wind: float = 1
        self.wind_gust_chance: float = 0.01
        self.topple_chance: float = 0.1
        self.riserate: float = 0.04
        self.last: float = time.time()
        self.last_per = {}

        # dicts of np arrays by universe name
        # Don't worry about garbage collection,
        # this all gets reset when a group is stopped and started
        self.heights = {}
        self.heights_lp = {}

        self.rand = [random.triangular(0, 1, 0.35) for i in range(256)]

    def frame(
        self,
        u: str,
        old,
        values: numpy.typing.NDArray[numpy.float32],
        alphas: numpy.typing.NDArray[numpy.float32],
        alpha: float,
    ):
        uobj = getUniverse(u)
        assert uobj

        call_time = time.time()

        if u not in self.heights:
            if uobj:
                self.heights[u] = makeBlankArray(len(uobj.values), 1)
                self.heights_lp[u] = makeBlankArray(len(uobj.values), 1)
                self.last_per[u] = time.time() - (1 / 60)

            else:
                return

        if uobj:
            # Mark as interpolatable for smartbulb bulb purposes
            uobj.interpolationTime = 0.2

        # Time in 60ths of a second since last frame, so we can keep a consistant frame rate
        t60 = (call_time - self.last) * 60
        self.last = call_time
        lp = t60 * 0.05
        self.wind = 1 * lp + self.wind * (1 - lp)

        if random.random() < self.blend_args["gustiness"] * t60:
            self.wind = max(random.normalvariate(1.3, 1), 1.2)
        if random.random() < 0.08:
            rr = self.blend_args["agility"]
            self.riserate = random.normalvariate(rr, rr / (4.0))

        # Get the per-universe time interval
        t60 = (call_time - self.last_per[u]) * 60
        self.last_per[u] = call_time

        topple_chance_setting = float(self.blend_args["topple_chance"])
        lowpass_setting = float(self.blend_args["lowpass"])

        # This algorithm is pretty tricky and I'm not
        # sure how to properly implement it in numpy.
        # So we're doing it one pixel at a time in python

        lastk = 0
        heights = self.heights[u]
        heights_lp = self.heights_lp[u]

        group = int(self.blend_args["group"])

        # These are here to make linter happy,
        # it doesn't know there will always be at least
        # one group found.  Or maybe it knows something i don't.
        topple_randomizer = 0
        nv = 0
        rise = 0

        groups_ctr = 0
        for k in numpy.nonzero(values)[0]:
            k = int(k)
            # Detect RGB groups of N, put them all together.
            # Reset group on finding a gap to account for typical DMX layouts
            if (not (groups_ctr % group)) or k - lastk > 1:
                groups_ctr += 1
                topple_randomizer = random.random()
                groups_ctr = 0
                nv = self.rand[fast_rand_255()]

                rise = random.random() * self.riserate * t60
            groups_ctr += 1

            lastk = k
            if topple_randomizer < (topple_chance_setting * self.wind * t60):
                heights[k] = min(
                    1 - (nv * (values[k] / 255.0)), heights[k] + 0.1
                )
            else:
                if heights[k] < 1 and values[k] > 0:
                    heights[k] += rise * t60
                else:
                    heights[k] = 1

            f = min(1, lowpass_setting * t60)
            heights_lp[k] = heights_lp[k] * (1 - f) + heights[k] * (f)

        old *= (
            (alphas * alpha * numpy.minimum(heights_lp, 1))
            + 1
            - (alpha * alphas)
        )
        return old


blendmodes["flicker"] = flicker_blendmode


class vary_blendmode_np(BlendMode):
    "Ads random variation, basically a random time varying gel"

    always_rerender = True

    parameters = {
        "interval": (
            "Change Interval",
            "number",
            "How many seconds between changes",
            1.2,
        ),
        "rinterval": (
            "Randomize Interval",
            "number",
            "Amount to randmoly vary change interval",
            0.5,
        ),
        "speed": ("Speed", "number", "How fast to change", 0.015),
        "mode": (
            "Mode",
            "number",
            "Mode value for the triangular distribution that defines the random values",
            0.8,
        ),
    }

    def __init__(self, group):
        BlendMode.__init__(self, group)
        self.vals = {}
        self.vals_lp = {}
        self.group = group
        self.ntt = 0
        self.last = time.time()
        self.last_per = {}

    def frame(self, u, old, values, alphas, alpha):
        uobj = getUniverse(u)

        if u not in self.vals:
            if uobj:
                self.vals[u] = makeBlankArray(len(uobj.values))
                self.vals_lp[u] = makeBlankArray(len(uobj.values))
                self.last_per[u] = time.time() - (1 / 60)

            else:
                return old

        # Time in 60ths of a second since last frame, so
        # we can keep a consistant frame rate
        t60 = (time.time() - self.last_per[u]) * 60
        self.last = time.time()
        self.last_per[u] = time.time()

        if time.time() > self.ntt:
            interval = self.blend_args["interval"]
            rnd = self.blend_args["rinterval"]
            avg = self.blend_args["mode"]
            nv = numpy.random.default_rng().triangular(
                0, max(min(1, 1 - avg), 0), 1, values.shape
            )
            self.vals[u] = 1 - (nv * (values / 255.0))
            self.ntt = time.time() + random.triangular(
                interval - rnd, interval + rnd, interval
            )

        lp = t60 * self.blend_args["speed"]
        if uobj:
            if not uobj.localFading:
                lp = 1
                uobj.interpolationTime = (1 / 60) / self.blend_args["speed"]

        self.vals_lp[u] = self.vals_lp[u] * (1 - lp) + self.vals[u] * lp
        old *= numpy.minimum((alpha * self.vals_lp[u]) + 1 - alpha, 255)
        return old


blendmodes["vary"] = vary_blendmode_np


class exp_blendmode_np(BlendMode):
    default_channel_value = 165

    def __init__(self, group):
        BlendMode.__init__(self, group)
        self.group = group
        self.last = time.time()

    def frame(self, u, below, values, alphas, alpha):
        return (
            ((below ** (values / 100.0)) / 255.0 ** (values / 100.0)) * 255
        ) * (alphas * alpha) + below * (1 - alphas * alpha)


blendmodes["gamma"] = exp_blendmode_np


class sparks_blendmode(BlendMode):
    """Randomly jump to some of the values in this group then fade
    back to what they were. Works in groups of 3 channels"""

    always_rerender = True

    parameters = {
        "fadetime": ("Fade Time", "number", "How fast to fade out again.", 1),
        "interval": ("Interval", "number", "How often to do a spark", 3),
        "variation": (
            "Variation",
            "number",
            "How much to vary the spark intensity",
            0.3,
        ),
        "group": (
            "Group",
            "number",
            "Detect groups of channels to connect, e.g. to make RGB look right",
            3,
        ),
    }

    def __init__(self, group):
        BlendMode.__init__(self, group)
        self.vals_lp = {}
        self.sparktimes = {}
        self.group = group
        self.last = time.time()
        self.last_per = {}

    def frame(self, u, old, values, alphas, alpha):
        if u not in self.vals_lp:
            uobj = getUniverse(u)
            if uobj:
                self.sparktimes[u] = makeBlankArray(len(uobj.values))
                self.vals_lp[u] = makeBlankArray(len(uobj.values))
                self.last_per[u] = time.time() - (1 / 60)

            else:
                return old

        lastk = ctr = 0
        x = False
        t = time.time()
        group = self.blend_args["group"]
        # Groups of 3 are supposed to come on at the same time because of RGB triples.
        for k in numpy.nonzero(alphas)[0]:
            if (not (ctr % group)) or k - lastk > 1:
                ctr = 0
                nv = random.triangular(1 - self.blend_args["variation"], 1)
                if t > self.sparktimes.get(k, 0):
                    c = self.blend_args["interval"]
                    x = True
                    self.sparktimes[k] = t + random.uniform(
                        max(c / 3.0, 0.35), c * 2
                    )
                else:
                    x = False
            if x:
                self.vals_lp[u][k] = max(nv, self.vals_lp[u][k])
            ctr += 1
            lastk = k

        # Supposed to be a first order lowpass filter to handle the fade out
        t = time.time() - self.last_per[u]
        self.last = time.time()
        # Calculate the decay constant
        k = 1 / self.blend_args["fadetime"]
        y = math.e ** -(k * t)
        # Exponential decay equation.
        self.vals_lp[u] *= y

        # The vals_lp are actually alphas that spark up and then
        # fade out and control how much of the group shows up
        # in that channel
        return values * (self.vals_lp[u] * alpha * alphas) + old * (
            1 - (self.vals_lp[u] * alpha * alphas)
        )


blendmodes["sparks"] = sparks_blendmode
