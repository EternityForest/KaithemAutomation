# SPDX-FileCopyrightText: Copyright 2019 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


from scullery.fluidsynth import *
from . import directories
import os
import logging
import weakref

# https://musical-artifacts.com/artifacts/639


from scullery import fluidsynth

# Babyfont is small enough to include but doesn't sound as good.
if not os.path.isfile("/usr/share/sounds/sf2/FluidR3_GM.sf2"):
    DEFAULT_SOUNDFONT = os.path.join(directories.datadir, "sounds/babyfont.sf3")
    fluidsynth.FluidSynth.defaultSoundfont = DEFAULT_SOUNDFONT


class MidiAPI:
    instrumentSearch = get_gm_instruments
    FluidSynth = FluidSynth

    @property
    def numbersToGM(self):
        return get_gm_instruments()
