import copy
from typing import Any, Dict, Iterable

import numpy
import numpy.typing

from . import universes


def makeBlankArray(size: int):
    """
    A function that creates a blank NumPy array of a specified size.

    :param size: An integer representing the size of the array to be created.
    :return: A NumPy array filled with zeros of data type "f4".
    """
    x = [0] * size
    return numpy.array(x, dtype="f4")


class FadeCanvas:
    def __init__(self):
        """Handles calculating the effect of one group over a background.
        This doesn't do blend modes, it just interpolates."""
        self.background_v: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.background_a: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.v2: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.a2: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.output = (self.v2, self.a2)

    def paint(
        self,
        fade: float | int,
        vals: Dict[str, numpy.typing.NDArray[Any]],
        alphas: Dict[str, numpy.typing.NDArray[Any]],
    ):
        """
        Makes v2 and a2 equal to the current background overlayed
        with values from group which is any object that has dicts of dicts of vals and and
        alpha.

        Should you have cached dicts of arrays vals and
        alpha channels(one pair of arrays per universe),
        put them in vals and arrays
        for better performance.

        fade is the fade amount from 0 to 1 (from background to the new)

        defaultValue is the default value for a universe. Usually 0.

        """

        # We assume a lot of these lists have the same set of universes. If it gets out of sync you
        # probably have to stop and restart the
        for i in vals:
            effectiveFade = fade
            obj = universes.getUniverse(i)
            # TODO: How to handle nonexistant
            if not obj:
                continue
            # Add existing universes to canvas, skip non existing ones
            if i not in self.background_v:
                size = len(obj.values)
                nv = copy.copy(self.v2)
                na = copy.copy(self.a2)

                self.background_v[i] = makeBlankArray(size)
                self.background_a[i] = makeBlankArray(size)
                nv[i] = makeBlankArray(size)
                na[i] = makeBlankArray(size)

                self.v2 = nv
                self.a2 = na
                self.output = (nv, na)

            # Some universes can disable local fading, like smart bulbs where we have remote fading.
            # And we would rather use that. Of course, the disadvantage is we can't properly handle
            # Multiple things fading all at once.
            if not obj.localFading:
                effectiveFade = 1

            # We don't want to fade any values that have 0 alpha in the group,
            # because that's how we mark "not present", and we want to track the old val.
            # faded = self.v[i]*(1-(fade*alphas[i]))+ (alphas[i]*fade)*vals[i]
            faded = self.background_v[i] * (1 - effectiveFade) + (
                effectiveFade * vals[i]
            )

            # We always want to jump straight to the value if alpha was previously 0.
            # That's because a 0 alpha would mean the last group released that channel, and there's
            # nothing to fade from, so we want to fade in from transparent not from black
            is_new = self.background_a[i] == 0
            self.v2[i] = numpy.where(is_new, vals[i], faded)

        # Now we calculate the alpha values. Including for
        # Universes the cue doesn't affect.
        for i in self.background_a:
            effectiveFade = fade
            obj = universes.getUniverse(i)
            # TODO ?
            if not obj:
                continue
            if not obj.localFading:
                effectiveFade = 1
            if i not in alphas:
                aset = 0
            else:
                aset = alphas[i]
            self.a2[i] = (
                self.background_a[i] * (1 - effectiveFade)
                + effectiveFade * aset
            )

    def save_current_as_background(self):
        self.background_v = copy.deepcopy(self.v2)
        self.background_a = copy.deepcopy(self.a2)

    def clean(self, affect: Iterable[str]):
        nv = copy.copy(self.v2)
        na = copy.copy(self.a2)

        for i in list(self.background_a.keys()):
            if i not in affect:
                del self.background_a[i]

        for i in list(na.keys()):
            if i not in affect:
                del na[i]

        for i in list(self.background_v.keys()):
            if i not in affect:
                del self.background_v[i]

        for i in list(nv.keys()):
            if i not in affect:
                del nv[i]

        self.v2 = nv
        self.a2 = na
        self.output = (nv, na)
