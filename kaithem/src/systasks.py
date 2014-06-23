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

import time,atexit,sys,platform,re
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
lastfpd=0
lastram=0
lastpageviews =0
pageviewsthisminute = 0
pageviewpublishcountdown = 1
tenminutepagecount = 0

#This gets called when an HTML request is made.
def aPageJustLoaded():
    global pageviewsthisminute
    pageviewsthisminute = pageviewsthisminute +1

#Acessed by stuff outide this file
pageviewcountsmoother = util.LowPassFiter(0.3)

frameRateWasTooLowLastMinute = False
MemUseWasTooHigh = False
firstrun = True

def everyminute():
    global pageviewsthisminute,firstrun
    global pageviewpublishcountdown,lastpageviews
    global lastsaved, lastdumpedlogs,lastfpd,lastram,tenminutepagecount
    global frameRateWasTooLowLastMinute
    global MemUseWasTooHigh
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
    
    if (newevt.averageFramesPerSecond < config['max-frame-rate']*0.95) or time.time()>lastfpd+(60*10):    
        messagebus.postMessage("/system/perf/FPS" , round(newevt.averageFramesPerSecond,2))
        lastfpd = time.time()
            
    tenminutepagecount += pageviewsthisminute
            
    pageviewcountsmoother.sample(pageviewsthisminute)
    pageviewsthisminute = 0
    
    if (time.time()>lastpageviews+600) and tenminutepagecount>0:
        messagebus.postMessage("/system/perf/requestsperminute" , tenminutepagecount/10)
        lastpageviews = time.time()
        tenminutepagecount = 0

    
    #The frame rate is not valid for the first few seconds because of the average
    if not firstrun:
        #Hysteresis to avoid flooding
        if newevt.averageFramesPerSecond < config['max-frame-rate']*0.50:
            if not frameRateWasTooLowLastMinute:
                messagebus.postMessage("/system/notifications/warnings" , "Warning: Frame rate below 50% of maximum")
                frameRateWasTooLowLastMinute = True

        if newevt.averageFramesPerSecond < config['max-frame-rate']*0.8:
            frameRateWasTooLowLastMinute = False
            
    firstrun == False   
    if platform.system()=="Linux":
            try:
                f = util.readfile("/proc/meminfo")
                total = int(re.search("MemTotal.*?([0-9]+)",f).group(1))
                free = int(re.search("MemFree.*?([0-9]+)",f).group(1))
                cache = int(re.search("Cached.*?([0-9]+)",f).group(1))
                
                used = round(((total - (free+cache))/1000.0),2)
                usedp = round((1-(free+cache)/float(total)),3)
                total = round(total/1024.0,2)
                if (time.time()-lastram>600) or usedp>0.8:
                    messagebus.postMessage("/system/perf/memuse",usedp)
                    lastram=time.time()
                #No hysteresis here, mem use should change slower and is more important IMHO than cpu
                if usedp > config['mem-use-warn']:
                    if not MemUseWasTooHigh:
                        MemUseWasTooHigh = True
                        messagebus.postMessage("/system/notifications/warnings" , "Total System Memory Use rose above "+str(int(config['mem-use-warn']*100))+"%")
                else:
                    MemUseWasTooHigh = False
            except Exception as e:
                raise e
            
    
#This is a polled trigger returning true at the top of every minute.
def onminute():  
    return kaithem.time.second() == 0

#newevt provides a special type of trigger just for system internal events
e = newevt.PolledInternalSystemEvent(onminute,everyminute,{},priority=20)
e.module = "<Internal System Polling>"
e.resource = "EveryMinute"
e.register()

#let the user choose to have the server save everything before a shutdown
if config['save-before-shutdown']:
    def save():
        print("saving before shutting down")
        util.SaveAllState()
    atexit.register(save)
    cherrypy.engine.subscribe("exit",save)
    
    
def sd():
    messagebus.postMessage('/system/shutdown',"System about to shut down or restart")
    
sd.priority = 25
atexit.register(sd)
cherrypy.engine.subscribe("exit",sd)   
    