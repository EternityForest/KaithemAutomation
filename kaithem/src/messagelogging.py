import messagebus
import cherrypy
import pages
import time
import threading
import directories
import json
import os
import util

from config import config
from collections import defaultdict

approxtotalloggenentries = 0


toSave = set()
with open(os.path.join(directories.logdir,"whattosave.txt"),'r') as f:
    x = f.read()
    
for line in x.split('\n'):
    toSave.add(line.strip())

del x
log = defaultdict(list)

def dumpLogFile():
    global log
    temp = log
    log = defaultdict(list)
    #Get rid of anything that is not in the list of things to dump to the log
    temp2 = {}
    for i in toSave:
        if i in temp:
            temp2[i] = temp[i]
    temp = temp2
    
            
    #Save the list of things to dump
    with open(os.path.join(directories.logdir,"whattosave.txt"),'w') as f:
        for i in toSave:
            f.write(i+'\n')
            
            
    where =os.path.join(directories.logdir,'dumps')
    #Actually dump the log.
    with open(os.path.join(where,str(time.time())+'.json'),'w') as f:
        json.dump(temp,f,sort_keys=True)
    
    
    asnumbers = {}
    for i in util.get_files(where):
            try:
                asnumbers[float(i[:-5])] = i
            except ValueError:
                pass
    
    for i in sorted(asnumbers.keys())[0:-config['keep-log-dumps']]:
        os.remove(os.path.join(where,asnumbers[i]))

    
        
   

def messagelistener(topic,message):
    global log
    if topic not in log:
        log[topic] = []
    
    log[topic].append((time.time(),message))
    #This is not threadsafe. Hence the approx.
    approxtotalloggenentries +=1
    if approxtotalloggenentries>config['log-dump-size']:
        workers.do(dumpLogFile())


messagebus.subscribe('/',messagelistener)

class WebInterface(object):
    @cherrypy.expose
    def index(self, ):
        pages.require('/users/logs.view')
        return pages.get_template('logging/index.html').render()
    
    @cherrypy.expose
    def startlogging(self,topic):
        pages.require('/admin/logging.edit')
        toSave.add(topic)
        return pages.get_template('logging/index.html').render()
    
    @cherrypy.expose
    def stoplogging(self,topic):
        pages.require('/admin/logging.edit')
        toSave.discard(topic)
        return pages.get_template('logging/index.html').render()
    
    @cherrypy.expose
    def setlogging(self, txt):
        pages.require('/admin/logging.edit')
        global toSave
        for line in txt.split('\n'):
            toSave = set()
            toSave.add(line.strip())
            
    @cherrypy.expose
    def viewall(self, topic):
        pages.require('/users/logs.view')
        return pages.get_template('logging/topic.html').render(topicname=topic)
    
    @cherrypy.expose
    def clearall(self,topic):
        pages.require('/admin/logging.edit')
        log.pop(topic)
        return pages.get_template('logging/index.html').render()  
    
            
    
