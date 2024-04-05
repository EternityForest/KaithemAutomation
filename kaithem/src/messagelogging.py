# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
import time
import threading
import os
import collections
import traceback
import logging
import cherrypy
from . import messagebus, directories, util, pages
from .messagebus import normalize_topic

from .config import config
from collections import deque, OrderedDict

# this flag tells if we need to save the list of what to log
loglistchanged = False

approxtotallogentries = 0

savelock = threading.RLock()

toSave = set()
try:
    if os.path.isfile(os.path.join(directories.logdir, "whattosave.txt")):
        with open(os.path.join(directories.logdir, "whattosave.txt"), "r") as f:
            x = f.read()
        for line in x.split("\n"):
            toSave.add(normalize_topic(line.strip()))
        del x
    else:
        for i in config["log-topics"]:
            toSave.add(normalize_topic(i))
except Exception:
    messagebus.post_message(
        "/system/notifications/errors",
        "Error loading logged topics list. using defaults:\n" + traceback.format_exc(6),
    )

log = {}


def saveLogList():
    global loglistchanged
    if loglistchanged:
        # Save the list of things to dump
        with open(os.path.join(directories.logdir, "whattosave.txt"), "w") as f:
            util.chmod_private_try(os.path.join(directories.logdir, "whattosave.txt"))
            for i in toSave:
                f.write(i + "\n")
        loglistchanged = False


# Dict beieng used as ordered set, it's a cache of topics that are known not to be logged.
known_unsaved = collections.OrderedDict()


def isSaved(topic):
    "Determine of logging is set up for a given topic"
    if topic in known_unsaved:
        return False
    if messagebus.MessageBus.parse_topic(topic).isdisjoint(toSave):
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
        if "error" in topic:
            logger.error(topic + " " + str(message))
        elif "warning" in topic:
            logger.warning(topic + " " + str(message))
        else:
            logger.info(topic + " " + str(message))

    if topic not in log:
        log[topic] = deque()

    # Default dicts are *not* good here like I thought
    log[topic].append((time.time(), message))

    # Only keep recent messages.
    try:
        if len(log[topic]) > config["non-logged-topic-limit"]:
            log[topic].popleft()
            approxtotallogentries -= 1
    except Exception as e:
        print(e)


messagebus.subscribe("/#", messagelistener)


class WebInterface(object):
    @cherrypy.expose
    def index(self, *args, **kwargs):
        pages.require("view_admin_info")
        return pages.get_template("logging/index.html").render()

    @cherrypy.expose
    def startlogging(self, topic):
        global known_unsaved
        global loglistchanged
        pages.require("system_admin")
        pages.postOnly()
        # Invalidate the cache of non-logged topics
        known_unsaved = OrderedDict()
        topic = topic.encode("latin-1").decode("utf-8")
        topic = topic[:]
        loglistchanged = True
        toSave.add(normalize_topic(topic))
        saveLogList()
        return pages.get_template("logging/index.html").render()

    @cherrypy.expose
    def stoplogging(self, topic):
        global loglistchanged
        pages.require("system_admin")
        pages.postOnly()
        topic = topic.encode("latin-1").decode("utf-8")
        topic = topic[1:]
        loglistchanged = True
        toSave.discard(normalize_topic(topic))
        saveLogList()
        return pages.get_template("logging/index.html").render()

    @cherrypy.expose
    def setlogging(self, txt):
        global known_unsaved
        pages.require("system_admin")
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
        saveLogList()
        return pages.get_template("logging/index.html").render()

    @cherrypy.expose
    def viewall(self, topic, page=1):
        pages.require("view_admin_info")
        return pages.get_template("logging/topic.html").render(
            topicname=normalize_topic(topic), page=int(page)
        )
