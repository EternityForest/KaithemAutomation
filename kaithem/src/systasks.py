#Copyright Daniel Black 2013
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

import time,atexit
import cherrypy
from . import newevt,messagebus,unitsofmeasure,util,messagelogging
from .kaithemobj import kaithem
from .config import config

#Can't think of anywhere else to put this thing.
systemStarted = time.time()


lastsaved = time.time()
if not config['autosave-state'] == 'never':
    saveinterval = unitsofmeasure.timeIntervalFromString(config['autosave-state'])

lastdumpedlogs = time.time()
if not config['autosave-logs'] == 'never':
    dumplogsinterval = unitsofmeasure.timeIntervalFromString(config['autosave-logs'])

lastgotip = time.time()

pageviewsthisminute = 0

def aPageJustLoaded():
    global pageviewsthisminute
    pageviewsthisminute = pageviewsthisminute +1

pageviewcountsmoother = util.LowPassFiter(0.3)

def everyminute():
    global pageviewsthisminute
    global lastsaved, lastdumpedlogs
    if not config['autosave-state'] == 'never':
        if (time.time() -lastsaved) > saveinterval:
            lastsaved = time.time()
            #This does not dump the log files. The log files change often.
            #It would suck to have tons of tiny log files so we let the user configure
            #Them separately
            util.SaveAllStateExceptLogs()
            
    if not config['autosave-logs'] == 'never':
        if (time.time() -lastdumpedlogs) > dumplogsinterval:
            lastdumpedlogs = time.time()
            messagelogging.dumpLogFile()
        
    messagebus.postMessage("/system/perf/FPS" , round(newevt.averageFramesPerSecond,2))
    pageviewcountsmoother.sample(pageviewsthisminute)
    pageviewsthisminute = 0
    
    
def onminute():
    
    return kaithem.time.second() == 0

e = newevt.PolledInternalSystemEvent(onminute,everyminute,{},priority=20)
e.register()

#let the user choose to have the server save everything before a shutdown
if config['save-before-shutdown']:
    def save():
        util.SaveAllState()
    atexit.register(save)
    cherrypy.engine.subscribe("exit",save)
    