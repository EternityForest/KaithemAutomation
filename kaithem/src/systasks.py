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

import newevt,messagebus,time,unitsofmeasure,util,messagelogging,atexit,cherrypy
from kaithemobj import kaithem
from config import config

#Can't think of anywhere else to put this thing.
systemStarted = time.time()


lastsaved = time.time()
if not config['autosave-all'] == 'never':
    saveinterval = unitsofmeasure.timeIntervalFromString(config['autosave-all'])

lastdumpedlogs = time.time()
if not config['autosave-logs'] == 'never':
    dumplogsinterval = unitsofmeasure.timeIntervalFromString(config['autosave-logs'])

lastgotip = time.time()

def everyminute():
    global lastsaved, lastdumpedlogs
    if not config['autosave-all'] == 'never':
        if (time.time() -lastsaved) > saveinterval:
            lastsaved = time.time()
            util.SaveAllState()
            
    if not config['autosave-logs'] == 'never':
        if (time.time() -lastdumpedlogs) > dumplogsinterval:
            lastdumpedlogs = time.time()
            messagelogging.dumpLogFile()
        
    messagebus.postMessage("/system/perf/FPS" , round(newevt.averageFramesPerSecond,2))
    
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
    