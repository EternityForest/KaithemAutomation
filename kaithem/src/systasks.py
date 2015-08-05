#Copyright Daniel Dunn 2013
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

import time,atexit,sys,platform,re,datetime,threading,weakref,signal
import cherrypy
from . import newevt,messagebus,unitsofmeasure,util,messagelogging,mail,scheduling
from .kaithemobj import kaithem
from .config import config

#Can't think of anywhere else to put this thing.
systemStarted = time.time()


lastsaved = time.time()
def getcfg():
    if not config['autosave-state'] == 'never':
        saveinterval = unitsofmeasure.timeIntervalFromString(config['autosave-state'])

    lastdumpedlogs = time.time()
    if not config['autosave-logs'] == 'never':
        dumplogsinterval = unitsofmeasure.timeIntervalFromString(config['autosave-logs'])

getcfg()

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
    if config["log-http"]:
        messagebus.postMessage("/system/http/access", {"ip":cherrypy.request.remote.ip, "req":cherrypy.request.request_line})

#Acessed by stuff outide this file
pageviewcountsmoother = util.LowPassFiter(0.3)

frameRateWasTooLowLastMinute = False
MemUseWasTooHigh = False
firstrun = True
checked = False

time_last_minute = 0

@scheduling.scheduler.everyMinute
def check_mail_credentials():
    if time.localtime().tm_min==0:
        mail.check_credentials()


@scheduling.scheduler.everyMinute
def check_time_set():
    global time_last_minute
    if time_last_minute:
        #This event is supposed to run every minute. So we add 60 to the last run's time. If the current time is more than 7 seconds off from that.
        #assume the time has been set. Use 30 seconds because maybe high CPU load could make it take longer than a minute.
        if abs(time.time() - (time_last_minute+60))>   30:
            messagebus.postMessage("/system/notifications/important" , "Kaithem has detected the system time was set.")
    time_last_minute = time.time()


@scheduling.scheduler.everyMinute
def logstats():
    global pageviewsthisminute,firstrun,checked
    global pageviewpublishcountdown,lastpageviews
    global frameRateWasTooLowLastMinute
    global MemUseWasTooHigh
    global lastfpd,lastram,tenminutepagecount,lastfpd

    pass
    #Do the page count
    tenminutepagecount += pageviewsthisminute

    pageviewcountsmoother.sample(pageviewsthisminute)
    pageviewsthisminute = 0

    if (time.time()>lastpageviews+600) and tenminutepagecount>0:
        messagebus.postMessage("/system/perf/requestsperminute" , tenminutepagecount/10)
        lastpageviews = time.time()
        tenminutepagecount = 0

#Frame rate and mem
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

                if usedp > config['mem-use-warn']:
                    if not MemUseWasTooHigh:
                        MemUseWasTooHigh = True
                        messagebus.postMessage("/system/notifications/warnings" , "Total System Memory Use rose above "+str(int(config['mem-use-warn']*100))+"%")

                if usedp < (config['mem-use-warn']-0.08):
                    MemUseWasTooHigh = False
            except Exception as e:
                raise e

    if (newevt.averageFramesPerSecond < config['max-frame-rate']*0.95) or time.time()>lastfpd+(60*10):
        messagebus.postMessage("/system/perf/FPS" , round(newevt.averageFramesPerSecond,2))
        lastfpd = time.time()


@scheduling.scheduler.everyMinute
def autosave():
    global lastsaved,lastdumpedlogs
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

def save():
    print("saving before shutting down")
    util.SaveAllState()

#let the user choose to have the server save everything before a shutdown
if config['save-before-shutdown']:
    atexit.register(save)
    cherrypy.engine.subscribe("exit",save)


def sd():
    messagebus.postMessage('/system/shutdown',"System about to shut down or restart")
    messagebus.postMessage('/system/notifications/shutdown',"System shutting down now")


sd.priority = 25
atexit.register(sd)
cherrypy.engine.subscribe("stop",sd)

def stop(*args):
    messagebus.postMessage('/system/notifications/shutdown',"Recieved SIGINT.")
    cherrypy.engine.exit()
signal.signal(signal.SIGINT,stop)
