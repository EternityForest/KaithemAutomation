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
__doc__=''

#This is an acceptable dependamcy, it will be part of libkaithem if such a thing exists
from scullery import jack
from scullery.jack import *
import scullery


def reloadSettings():
    from . import registry
    scullery.jack.usbPeriodSize = registry.get("/system/sound/jackusbperiodsize",128)
    scullery.jack.usbLatency = max(registry.get("/system/sound/jackusblatency",384),scullery.jack.usbPeriodSize*2)
    scullery.jack.periodSize = registry.get("/system/sound/jackperiodsize",128)
    scullery.jack.jackPeriods = max(registry.get("/system/sound/jackperiods",2),2)

    scullery.jack.sharePulse = registry.get("/system/sound/sharepulse",None)

scullery.jack.settingsReloader= reloadSettings

reloadSettings()