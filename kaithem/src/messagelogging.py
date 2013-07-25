import messagebus
import cherrypy
import pages
import time
import threading
from config import config
from collections import defaultdict

approxtotalloggenentries = 0

toSave = set()
toSave_lock = threading.Lock()

log = defaultdict(list)


def messagelistener(topic,message):
    global log
    if topic not in log:
        log[topic] = []
    
    log[topic].append((time.time(),message))
    #This is not threadsafe. Hence the approx.
    approxtotalloggenentries +=1
    if approxtotalloggenentries>config['log-dump-size']:
        log = defaultdict(list)

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
    
            
    
