# SPDX-FileCopyrightText: Copyright 2017 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


import logging
import os
import re
import textwrap

import quart
import structlog

from . import directories, pages, pylogginghandler, quart_app, util, widgets

syslogwidget = widgets.ScrollingWindow(2500)
syslogwidget.require("view_admin_info")


try:
    try:
        import html

        esc = html.escape
    except Exception:
        import cgi

        esc = cgi.escape
except Exception:

    def esc(t):
        return t


class WidgetHandler(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.widget = widgets.ScrollingWindow(2500)

    def handle(self, record):
        r = self.filter(record)
        if r:
            self.emit(record)
        return r

    def emit(self, r):
        if r:
            t = textwrap.fill(pylogginghandler.syslogger.format(r), 120)
            t = esc(t)
            if r.levelname in ["ERROR", "CRITICAL"]:
                self.widget.write('<pre class="danger">' + t + "</pre>")
            elif r.levelname in ["WARNING"]:
                self.widget.write('<pre class="danger">' + t + "</pre>")
            elif r.name == "system.notifications.important":
                self.widget.write('<pre class="highlight">' + t + "</pre>")
            else:
                self.widget.write("<pre>" + t + "</pre>")


dbg = WidgetHandler()

structlog.get_logger().addHandler(dbg)


def f(r):
    t = textwrap.fill(pylogginghandler.syslogger.format(r), 120)
    if r.levelname in ["ERROR", "CRITICAL"]:
        syslogwidget.write('<pre class="danger">' + t + "</pre>")
    elif r.levelname in ["WARNING"]:
        syslogwidget.write('<pre class="danger">' + t + "</pre>")
    elif r.name == "system.notifications.important":
        syslogwidget.write('<pre class="highlight">' + t + "</pre>")
    else:
        syslogwidget.write("<pre>" + t + "</pre>")


pylogginghandler.syslogger.callback = f


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
    if not filename.startswith(os.path.normpath(os.path.abspath(os.path.join(directories.logdir, "dumps")))):
        raise RuntimeError("Security Violation")
    return await quart.send_file(filename, as_attachment=True, attachment_filename=os.path.split(filename)[1])


@quart_app.app.route("/syslog/archive")
def logarchive():
    try:
        pages.require("view_admin_info")
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    return pages.get_template("syslog/archive.html").render(files=listlogdumps())
