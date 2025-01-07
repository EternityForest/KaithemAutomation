# SPDX-FileCopyrightText: Copyright 2017 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later


import io
import logging
import os
import re
from collections import deque

import quart
from scullery import ratelimits, workers

from . import directories, pages, quart_app, util, widgets

syslogwidget = widgets.ScrollingWindow(2500)
syslogwidget.require("view_admin_info")

buffer = deque(maxlen=1000)

ratelimiter = ratelimits.RateLimiter(1, 60)


def _strip_ansi_colour(text: str):
    """Strip ANSI colour sequences from a string.

    Args:
        text (str): Text string to be stripped.

    Returns:
        iter[str]: A generator for each returned character. Note,
        this will include newline characters.

    """
    buff = io.StringIO(text)
    while b := buff.read(1):
        if b == "\x1b":
            while (b := buff.read(1)) != "m":
                continue
        else:
            yield b


def strip_ansi_colour(text: str) -> str:
    return "".join(_strip_ansi_colour(text))


def f():
    record: logging.LogRecord = buffer.popleft()
    t = strip_ansi_colour(handler.format(record))
    if record.levelname in ["ERROR", "CRITICAL"]:
        syslogwidget.write('<pre class="danger">' + t + "</pre>")
    elif record.levelname in ["WARNING"]:
        syslogwidget.write('<pre class="danger">' + t + "</pre>")
    elif record.name == "system.notifications.important":
        syslogwidget.write('<pre class="highlight">' + t + "</pre>")
    else:
        syslogwidget.write("<pre>" + t + "</pre>")


class WebHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        if ratelimiter.limit():
            if len(buffer) > 1024:
                buffer.popleft()
            buffer.append(record)
            workers.do(f)
        else:
            print("Web log window rate limit exceeded, dropping")


handler = WebHandler()
handler.setLevel(logging.INFO)
rootlogger = logging.getLogger()
rootlogger.addHandler(handler)


def listlogdumps():
    where = os.path.join(directories.logdir, "dumps")
    logz = []
    r = re.compile(r"^.+_([0-9]*\.[0-9]*)\.log(\.gz|\.bz2)?$")
    for i in util.get_files(where):
        m = r.match(i)
        if m is not None:
            # Make time,fn,ext,size tuple
            # I have no clue how this line is suppoed to work.
            logz.append(
                (
                    float(m.groups("")[0]),
                    i,
                    m.groups("Uncompressed")[1],
                    os.path.getsize(os.path.join(where, i)),
                )
            )
    return logz


@quart_app.app.route("/syslog")
def logindex():
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("syslog/index.html").render()


@quart_app.app.route("/syslog/servelog/<filename>")
async def servelog(filename):
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    # Make sure the user can't acess any file on the server like this

    # First security check, make sure there's no obvious special chars
    if ".." in filename:
        raise RuntimeError("Security Violation")
    if "/" in filename:
        raise RuntimeError("Security Violation")
    if "\\" in filename:
        raise RuntimeError("Security Violation")
    if "~" in filename:
        raise RuntimeError("Security Violation")
    if "$" in filename:
        raise RuntimeError("Security Violation")

    filename = os.path.join(directories.logdir, "dumps", filename)
    filename = os.path.normpath(filename)
    # Second security check, normalize the abs path and make sure it is what we think it is.
    if not filename.startswith(
        os.path.normpath(
            os.path.abspath(os.path.join(directories.logdir, "dumps"))
        )
    ):
        raise RuntimeError("Security Violation")
    return await quart.send_file(
        filename,
        as_attachment=True,
        attachment_filename=os.path.split(filename)[1],
    )


@quart_app.app.route("/syslog/archive")
def logarchive():
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("syslog/archive.html").render(
        files=listlogdumps()
    )
