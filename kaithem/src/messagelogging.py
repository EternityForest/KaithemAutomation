# Copyright Daniel Dunn 2013, 2015
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
import time
import threading
import os
import bz2
import gzip
import re
import collections
import traceback
import logging
import cherrypy
from . import unitsofmeasure, messagebus, directories, workers, util, pages, config
from .messagebus import normalize_topic

from .config import config
from collections import defaultdict, deque, OrderedDict
# this flag tells if we need to save the list of what to log
loglistchanged = False

approxtotallogentries = 0

savelock = threading.RLock()

toSave = set()
try:
    if os.path.isfile(os.path.join(directories.logdir, "whattosave.txt")):
        with open(os.path.join(directories.logdir, "whattosave.txt"), 'r') as f:
            x = f.read()
        for line in x.split('\n'):
            toSave.add(normalize_topic(line.strip()))
        del x
    else:
        for i in config['log-topics']:
            toSave.add(normalize_topic(i))
except:
    messagebus.postMessage("/system/notifications/errors",
                           "Error loading logged topics list. using defaults:\n"+traceback.format_exc(6))

log = {}


def saveLogList():
    global loglistchanged
    if loglistchanged:
        # Save the list of things to dump
        with open(os.path.join(directories.logdir, "whattosave.txt"), 'w') as f:
            util.chmod_private_try(os.path.join(
                directories.logdir, "whattosave.txt"))
            for i in toSave:
                f.write(i+'\n')
        loglistchanged = False


# Dict beieng used as ordered set, it's a cache of topics that are known not to be logged.
known_unsaved = collections.OrderedDict()


def isSaved(topic):
    "Determine of logging is set up for a given topic"
    if topic in known_unsaved:
        return False
    if messagebus.MessageBus.parseTopic(topic).isdisjoint(toSave):
        known_unsaved[topic] = True
        if len(known_unsaved) > 1200:
            known_unsaved.pop(last=False)
        return False
    else:
        return True


logger = logging.getLogger("system.msgbus")


def messagelistener(topic, message):
    global log
    global approxtotallogentries

    if isSaved(topic):
        if 'error' in topic:
            logger.error(topic+" "+str(message))
        elif 'warning' in topic:
            logger.warning(topic+" "+str(message))
        else:
            logger.info(topic+" "+str(message))

    if not topic in log:
        log[topic] = deque()

    # Default dicts are *not* good here like I thought
    log[topic].append((time.time(), message))

    # Only keep recent messages.
    try:
        if len(log[topic]) > config['non-logged-topic-limit']:
            log[topic].popleft()
            approxtotallogentries -= 1
    except Exception as e:
        print(e)


messagebus.subscribe('/#', messagelistener)


class WebInterface(object):
    @cherrypy.expose
    def index(self, *args, **kwargs):
        pages.require('/users/logs.view')
        return pages.get_template('logging/index.html').render()

    @cherrypy.expose
    def startlogging(self, topic):
        global known_unsaved
        global loglistchanged
        pages.require('/admin/logging.edit')
        # Invalidate the cache of non-logged topics
        known_unsaved = OrderedDict()
        topic = topic.encode("latin-1").decode("utf-8")
        topic = topic[:]
        loglistchanged = True
        toSave.add(normalize_topic(topic))
        return pages.get_template('logging/index.html').render()

    @cherrypy.expose
    def stoplogging(self, topic):
        global loglistchanged
        pages.require('/admin/logging.edit')
        topic = topic.encode("latin-1").decode("utf-8")
        topic = topic[1:]
        loglistchanged = True
        toSave.discard(normalize_topic(topic))
        return pages.get_template('logging/index.html').render()

    @cherrypy.expose
    def setlogging(self, txt):
        global known_unsaved
        pages.require('/admin/logging.edit')
        pages.postOnly()
        # Invalidate the cache of non-logged topics
        global loglistchanged
        loglistchanged = True
        global toSave
        toSave = set()
        for line in txt.split("\n"):
            line = line.strip()
            if line.startswith("/"):
                line = line[1:]
            if line:
                toSave.add(normalize_topic(line))
        known_unsaved = OrderedDict()
        return pages.get_template('logging/index.html').render()

    @cherrypy.expose
    def viewall(self, topic, page=1):
        pages.require('/users/logs.view')
        return pages.get_template('logging/topic.html').render(topicname=normalize_topic(topic), page=int(page))
