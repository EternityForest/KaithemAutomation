#Copyright Daniel Dunn 2013,2017
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

import time,atexit,sys,platform,re,datetime,threading,weakref,signal,logging
import cherrypy
from . import newevt,messagebus,unitsofmeasure,util,messagelogging,mail,scheduling
from .kaithemobj import kaithem
from .config import config

#Can't think of anywhere else to put this thing.
systemStarted = time.time()

logger = logging.getLogger("system")

lastsaved = time.time()
def getcfg():
    global saveinterval,dumplogsinterval,lastdumpedlogs
    if not config['autosave-state'] == 'never':
        saveinterval = unitsofmeasure.timeIntervalFromString(config['autosave-state'])

    lastdumpedlogs = time.time()
    if not config['autosave-logs'] == 'never':
        dumplogsinterval = unitsofmeasure.timeIntervalFromString(config['autosave-logs'])

getcfg()

lastgotip = time.time()

lastram=0
lastramwarn = 0
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

MemUseWasTooHigh = False
firstrun = True
checked = False


@scheduling.scheduler.everyHour
def check_mail_credentials():
        mail.check_credentials()


try: 
    monotonic = time.monotonic()
except:
    monotonic=lambda: "monotonic time not available"

time_last_minute = 0
rhistory=[]
@scheduling.scheduler.everyMinute
def check_scheduler():
    "This is a continual built in self test for the scheduler"
    global rhistory
    rhistory.append((time.time(),))
    rhistory = rhistory[-10:]
    global time_last_minute
    if time_last_minute:
        if time.time() - (time_last_minute) < 58:
            messagebus.postMessage("/system/notifications/warnings" , "Kaithem has detected a scheduled event running too soon? History:"+repr(rhistory))
    time_last_minute = time.time()


@scheduling.scheduler.everyMinute
def logstats():
    global pageviewsthisminute,firstrun,checked
    global pageviewpublishcountdown,lastpageviews
    global MemUseWasTooHigh
    global lastram,tenminutepagecount
    global lastramwarn
    pass
    #Do the page count
    tenminutepagecount += pageviewsthisminute

    pageviewcountsmoother.sample(pageviewsthisminute)
    pageviewsthisminute = 0

    #Only log page views every ten minutes
    if (time.time()>lastpageviews+600) and tenminutepagecount>0:
        logger.info("Requests per minute: "+ str(round(tenminutepagecount/10,2)))
        lastpageviews = time.time()
        tenminutepagecount = 0

    if platform.system()=="Linux":
            try:
                f = util.readfile("/proc/meminfo")
                total = int(re.search("MemTotal.*?([0-9]+)",f).group(1))
                free = int(re.search("MemFree.*?([0-9]+)",f).group(1))
                cache = int(re.search("Cached.*?([0-9]+)",f).group(1))

                used = round(((total - (free+cache))/1000.0),2)
                usedp = round((1-(free+cache)/float(total)),3)
                total = round(total/1024.0,2)
                if (time.time()-lastram>600) or ((time.time()-lastram>300) and usedp>0.8):
                    logger.info("Total ram usage: "+ str(round(usedp*100,1)))
                    lastram=time.time()

                if usedp > config['mem-use-warn']:
                    if not MemUseWasTooHigh:
                        MemUseWasTooHigh = True
                        if (time.time()-lastramwarn>600):
                            messagebus.postMessage("/system/notifications/warnings" , "Total System Memory Use rose above "+str(int(config['mem-use-warn']*100))+"%")
                            lastramwarn = time.time()

                if usedp < (config['mem-use-warn']-0.08):
                    MemUseWasTooHigh = False
            except Exception as e:
                raise e



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
    if config['save-before-shutdown']:
        messagebus.postMessage('/system/notifications/important/',"System saving before shutting down")
        util.SaveAllState()

#let the user choose to have the server save everything before a shutdown
if config['save-before-shutdown']:
    atexit.register(save)
    cherrypy.engine.subscribe("exit",save)


def sd():
    messagebus.postMessage('/system/shutdown',"System about to shut down or restart")
    messagebus.postMessage('/system/notifications/important',"System shutting down now")


sd.priority = 25
atexit.register(sd)
cherrypy.engine.subscribe("stop",sd)

def stop(*args):
    messagebus.postMessage('/system/notifications/shutdown',"Recieved SIGINT.")
    cherrypy.engine.exit()
signal.signal(signal.SIGINT,stop)
