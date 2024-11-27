# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
import time
from collections import deque

import structlog

from . import messagebus, pages, quart_app
from .config import config
from .messagebus import normalize_topic

approxtotallogentries = 0


log = {}


logger = structlog.get_logger(__name__)


def messagelistener(topic, message):
    global log
    global approxtotallogentries

    if topic not in log:
        log[topic] = deque()

    # Default dicts are *not* good here like I thought
    log[topic].append((time.time(), message))

    # Only keep recent messages.
    try:
        if len(log[topic]) > config["non_logged_topic_limit"]:
            log[topic].popleft()
            approxtotallogentries -= 1
    except Exception:
        logger.exception("Error in messagebus logger")


messagebus.subscribe("/#", messagelistener)


@quart_app.app.route("/logs")
def logs_index():
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("logging/index.html").render()


@quart_app.app.route("/logs/viewall")
def viewall(topic, page=1):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("logging/topic.html").render(
        topicname=normalize_topic(topic), page=int(page)
    )
