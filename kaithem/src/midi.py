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


from . import directories
import os, yaml,logging,weakref

#https://musical-artifacts.com/artifacts/639
DEFAULT_SOUNDFONT = os.path.join(directories.datadir, "sounds/babyfont.sf3")

from scullery import fluidsynth
fluidsynth.FluidSynth.defaultSoundfont = DEFAULT_SOUNDFONT

from scullery.fluidsynth import *

class MidiAPI():
    instrumentSearch = getGMInstruments
    FluidSynth = FluidSynth
    @property
    def numbersToGM(self):
        return getGMInstruments()

    