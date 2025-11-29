from __future__ import annotations

import copy
import typing

import numpy
import numpy.typing

if typing.TYPE_CHECKING:
    from .universes import Universe


class LightingLayer:
    def __init__(self, ll: LightingLayer | None = None):
        self.values: dict[str, numpy.typing.NDArray[numpy.float64]] = {}
        self.alphas: dict[str, numpy.typing.NDArray[numpy.float64]] = {}

        if ll:
            self.values = copy.deepcopy(ll.values)
            self.alphas = copy.deepcopy(ll.alphas)

    def clean(self):
        """Remove stuff where alphas are all zero"""

        for i in list(self.values):
            if numpy.all(self.alphas[i] < 0.00000001):
                del self.values[i]
                del self.alphas[i]

    def set_val(
        self,
        universe: str,
        channel: int,
        value: float,
        default_universe_count=512,
    ):
        if universe not in self.values:
            self.values[universe] = numpy.zeros(
                default_universe_count, dtype=numpy.float64
            )
            self.alphas[universe] = numpy.zeros(
                default_universe_count, dtype=numpy.float64
            )
        self.values[universe][channel] = value

    def update_from(self, other: LightingLayer):
        """Make self equal to highest alpha wins between self and other"""
        for i in other.values:
            if i not in self.values:
                self.values[i] = numpy.zeros(other.values[i].shape)
                self.alphas[i] = numpy.zeros(other.alphas[i].shape)

            mask = other.alphas[i] > self.alphas[i]

            self.values[i] += other.values[i] * mask
            self.alphas[i] += other.alphas[i] * mask

    def fade_in(
        self,
        new_other: LightingLayer,
        blend: float,
        universes_cache: dict[str, Universe],
    ):
        """Produce a new layer that is a blend between self and other.
        except that if a value is in the new but not the old,
        fade up the alpha but jump straight to val to avoid double fades.
        """
        op = {}
        op_a = {}
        for universename in new_other.values:
            if universename not in self.values:
                v = numpy.zeros(new_other.values[universename].shape)
                a = numpy.zeros(new_other.alphas[universename].shape)
            else:
                v = self.values[universename]
                a = self.alphas[universename]

            mask = a > 0

            b = blend
            if universename in universes_cache:
                if not universes_cache[universename].local_fading:
                    b = 1

            op[universename] = numpy.where(
                mask,
                b * new_other.values[universename] + (1 - b) * v,
                new_other.values[universename],
            )

            op_a[universename] = (
                b * new_other.alphas[universename] + (1 - b) * a
            )

        ll = LightingLayer()
        ll.values = op
        ll.alphas = op_a
        return ll

    def clear(self):
        self.values = {}
        self.alphas = {}
