# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
import logging
import time
from collections import deque

import cherrypy

from . import messagebus, pages
from .config import config
from .messagebus import normalize_topic

approxtotallogentries = 0


log = {}


logger = logging.getLogger("system.msgbus")


def messagelistener(topic, message):
    global log
    global approxtotallogentries

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


class WebInterface:
    @cherrypy.expose
    def index(self, *args, **kwargs):
        pages.require("view_admin_info")
        return pages.get_template("logging/index.html").render()

    @cherrypy.expose
    def viewall(self, topic, page=1):
        pages.require("view_admin_info")
        return pages.get_template("logging/topic.html").render(topicname=normalize_topic(topic), page=int(page))
