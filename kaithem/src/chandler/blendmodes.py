
import numpy
import time
import random
import math
import weakref

from ..kaithemobj import kaithem
from . import core


def getUniverse(u):
    "Get strong ref to universe if it exists, else get none."
    try:
        oldUniverseObj = universes.universes[u]()
    except KeyError:
        oldUniverseObj = None
    return oldUniverseObj


if not hasattr(core, "blendmodes"):
    blendmodes = weakref.WeakValueDictionary()
else:
    blendmodes = core.blendmodes


def getblenddesc(mode):
    if mode == "gel" or mode == "multiply":
        return "Values in this scene act as a virtual gel filter over the layers below it, the final value is produced by multiplying the values together"
    if mode == "inhibit":
        return "Values in this scene act to limit the max value, the final value is the lower of the value in this scene and the rendered value below it"
    if mode == "HTP":
        return "The highest of the this scene's values and the values below it take effect, as in a traditional HTP lighting console"
    if mode == "monitor":
        return "This scene's values are set to the value just below it, to assist with debugging."

    try:
        return blendmodes[mode].description
    except:
        try:
            return blendmodes[mode].__doc__
        except:
            return ""


class BlendMode():
    autoStop = True


core.getblenddesc = getblenddesc
core.BlendMode = BlendMode
core.blendmodes = blendmodes


def makeBlankArray(l, v=0):
    x = [v] * l
    return numpy.array(x, dtype="f4")


class flicker_blendmode(BlendMode):
    "Blend mode based on physical model flickering"
    parameters = {"gustiness": ("Gustiness", "number", "", 0.2),
                  "lowpass": ("Lowpass", "number", "", 0.06),
                  "topple_chance": ("Windiness", "number", "", 0.1),
                  "agility": ("Flame agility", "number", "", 0.15),
                  "group": ("Group", "number", "Groups of this many channels flicker together, e.g. to make RGB look right", 3),

                  }
    description = """Effects layer that simulate a natural flame-like flickering effect. Channel value determines how much flicker to apply to that channel.
To use this, add a layer below containing the base colors. The flicker layer will randomly darken them according to it's simulation algorithm."""

    def __init__(self, scene):
        self.scene = scene

        self.wind = 1
        self.wind_gust_chance = 0.01
        self.topple_chance = 0.1
        self.riserate = 0.04
        self.last = time.time()
        self.last_per = {}

        # dicts of np arrays by universe name
        # Don't worry about garbage collection, this all gets reset when a scene is stopped and started
        self.heights = {}
        self.heights_lp = {}

    def frame(self, u, old, values, alphas, alpha):
        # It's always changing so always rerender
        self.scene.rerender = True

        uobj = getUniverse(u)

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
        t60 = (time.time() - self.last) * 60
        self.last = time.time()
        lp = t60 * 0.05
        self.wind = 1 * lp + self.wind * (1 - lp)

        if random.random() < self.scene.blendArgs['gustiness'] * t60:
            self.wind = max(random.normalvariate(1.3, 1), 1.2)
        if random.random() < 0.08:
            rr = self.scene.blendArgs['agility']
            self.riserate = random.normalvariate(rr, rr / (4.0))

        # Get the per-universe time interval
        t60 = (time.time() - self.last_per[u]) * 60
        self.last_per[u] = time.time()

        ctr = 0
        tc = self.scene.blendArgs['topple_chance']
        lps = self.scene.blendArgs['lowpass']

        # This algorithm is pretty tricky and I'm not sure how to properly implement it in numpy.
        # So we're doing it one pixel at a time in python

        lastk = 0
        heights = self.heights[u]
        heights_lp = self.heights_lp[u]

        group = int(self.scene.blendArgs['group'])
        for k in numpy.nonzero(values)[0]:
            k = int(k)
            # Detect RGB groups of N, put them all together.
            # Reset group on finding a gap to account for typical DMX layouts
            if ((not (ctr % group)) or k - lastk > 1):
                t = random.random()
                ctr = 0
                nv = random.triangular(0, 1, 0.35)
                # lowpass filtering constant for this set of 3
                lp = t60 * random.triangular(0, lps, lps / 2.0)
                rise = random.random() * self.riserate * t60
            ctr += 1

            lastk = k
            if t < (tc * self.wind * t60):
                heights[k] = min(
                    1 - (nv * (values[k] / 255.0)), heights[k] + 0.1)
            else:
                if heights[k] < 1 and values[k] > 0:
                    heights[k] += rise * t60
                else:
                    heights[k] = 1

            f = min(1, lp * t60)
            heights_lp[k] = heights_lp[k] * (1 - f) + heights[k] * (f)

        old *= (alphas * alpha * numpy.minimum(heights_lp, 1)) + \
            1 - (alpha * alphas)
        return old


blendmodes['flicker'] = flicker_blendmode


class vary_blendmode_np(BlendMode):
    "Ads random variation, basically a random time varying gel"
    parameters = {"interval": ("Change Interval", "number", "How many seconds between changes", 1.2),
                  "rinterval": ("Randomize Interval", "number", "Amount to randmoly vary change interval", 0.5),
                  "speed": ("Speed", "number", "How fast to change", 0.015),
                  "mode": ("Mode", "number", "Mode value for the triangular distribution that defines the random values", 0.8),
                  }

    def __init__(self, scene):
        self.vals = {}
        self.vals_lp = {}
        self.scene = scene
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

        # Time in 60ths of a second since last frame, so we can keep a consistant frame rate
        t60 = (time.time() - self.last_per[u]) * 60
        self.last = time.time()
        self.last_per[u] = time.time()

        # It's always changing so always rerender
        self.scene.rerender = True
        if time.time() > self.ntt:
            interval = self.scene.blendArgs['interval']
            rnd = self.scene.blendArgs['rinterval']
            avg = self.scene.blendArgs['mode']
            nv = numpy.random.triangular(
                0, max(min(1, 1 - avg), 0), 1, values.shape)
            self.vals[u] = 1 - (nv * (values / 255.0))
            self.ntt = time.time() + random.triangular(interval -
                                                           rnd, interval + rnd, interval)

        lp = t60 * self.scene.blendArgs['speed']
        if uobj:
            if not uobj.localFading:
                lp = 1
                uobj.interpolationTime = (
                    1 / 60) / self.scene.blendArgs['speed']

        self.vals_lp[u] = self.vals_lp[u] * (1 - lp) + self.vals[u] * lp
        old *= numpy.minimum((self.scene.alpha *
                             self.vals_lp[u]) + 1 - self.scene.alpha, 255)
        return old


blendmodes['vary'] = vary_blendmode_np


class exp_blendmode_np(BlendMode):
    "Ads random variation, basically a random time varying gel"
    default_channel_value = 165

    def __init__(self, scene):
        self.scene = scene
        # for i in self.scene.values:
        #     self.affect[i] = sorted(self.scene.values[i].keys())
        self.last = time.time()

    def frame(self, u, below, values, alphas, alpha):
        return (((below**(values / 100.0)) / 255.0**(values / 100.0)) * 255) * (alphas * alpha) + below * (1 - alphas * alpha)


blendmodes['gamma'] = exp_blendmode_np


class sparks_blendmode(BlendMode):
    "Randomly jump to some of the values in this scene then fade back to what they were. Works in groups of 3 channels"
    parameters = {
        "fadetime": ("Fade Time", "number", "How fast to fade out again.", 1),
        "interval": ("Interval", "number", "How often to do a spark", 3),
        "variation": ("Variation", "number", "How much to vary the spark intensity", 0.3),
        "group": ("Group", "number", "Detect groups of channels to connect, e.g. to make RGB look right", 3),

    }

    def __init__(self, scene):
        self.vals_lp = {}
        self.sparktimes = {}
        self.scene = scene
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

        # It's always changing so always rerender
        self.scene.rerender = True

        lastk = ctr = 0
        x = False
        t = time.time()
        group = self.scene.blendArgs['group']
        # Groups of 3 are supposed to come on at the same time because of RGB triples.
        for k in numpy.nonzero(alphas)[0]:
            if ((not (ctr % group)) or k - lastk > 1):
                ctr = 0
                nv = random.triangular(
                    1 - self.scene.blendArgs['variation'], 1)
                if t > self.sparktimes.get(k, 0):
                    c = self.scene.blendArgs['interval']
                    x = True
                    self.sparktimes[k] = t + \
                        random.uniform(max(c / 3.0, 0.35), c * 2)
                else:
                    x = False
            if x:
                self.vals_lp[u][k] = max(nv, self.vals_lp[u][k])
            ctr += 1
            lastk = k

        # Supposed to be a first order lowpass filter to handle the fade out
        t = (time.time() - self.last_per[u])
        self.last = time.time()
        # Calculate the decay constant
        k = 1 / self.scene.blendArgs['fadetime']
        y = math.e**-(k * t)
        # Exponential decay equation.
        self.vals_lp[u] *= y

        # The vals_lp are actually alphas that spark up and then fade out and control how much of the scene shows up
        # in that channel
        return values * (self.vals_lp[u] * alpha * alphas) + old * (1 - (self.vals_lp[u] * alpha * alphas))


blendmodes['sparks'] = sparks_blendmode