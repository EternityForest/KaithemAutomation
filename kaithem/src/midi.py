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


from scullery.fluidsynth import *
from . import directories
import os
import yaml
import logging
import weakref

# https://musical-artifacts.com/artifacts/639


from scullery import fluidsynth

# Babyfont is small enough to include but doesn't sound as good.
if not os.path.isfile("/usr/share/sounds/sf2/FluidR3_GM.sf2"):
    DEFAULT_SOUNDFONT = os.path.join(
        directories.datadir, "sounds/babyfont.sf3")
    fluidsynth.FluidSynth.defaultSoundfont = DEFAULT_SOUNDFONT


class MidiAPI():
    instrumentSearch = getGMInstruments
    FluidSynth = FluidSynth
    @property
    def numbersToGM(self):
        return getGMInstruments()
