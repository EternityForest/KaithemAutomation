# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import datetime
import getpass
import json
import os
import shutil
import socket
import sqlite3
import threading
import time
import traceback
import weakref
from typing import Callable
from urllib.parse import quote

import dateutil.parser
import pytz
import quart
import structlog
from scullery import scheduling

from kaithem.api import tags as tagsapi
from kaithem.src import (
    dialogs,
    directories,
    messagebus,
    modules_state,
    pages,
    quart_app,
    tagpoints,
)

oldlogdir = os.path.join(directories.vardir, "logs")
logdir = directories.logdir
ramdbfile = (
    "/dev/shm/"
    + socket.gethostname()
    + "-"
    + getpass.getuser()
    + "-taghistory.sqlite"
)


logger = structlog.get_logger(__name__)

if not os.path.exists(logdir):
    try:
        os.makedirs(logdir)
    except Exception:
        logger.exception("Can't make log dir")

# Build a filename including the hostname and user.   This is because SQLite may not be happy to be involved with SyncThing.
# For that reason, should someone get the bright idea to sync a kaithem vardir, we must keep the history databases single-writer.

# Plus, there is nothing in the DB itself to tell us who wrote it, so this is very convenient.
historyFilemame = (
    socket.gethostname() + "-" + getpass.getuser() + "-taghistory.sqlite"
)

newHistoryDBFile = os.path.join(logdir, historyFilemame)


def iso_now():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ts_to_iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.UTC).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


class TagLogger:
    """Base class for the object associated with one tag point for logging
    a specific type(min,max,avg,etc) of data from that tag"""

    accumType = "latest"
    defaultAccum = 0

    def __init__(
        self, tag, interval, history_length=3 * 30 * 24 * 3600, target="disk"
    ):
        # We can have purely ram file based logging
        if target == "disk":
            self.h = historian
            self.filename = newHistoryDBFile
        elif target == "ram":
            self.h = ramHistorian
            self.filename = ramdbfile
        else:
            raise ValueError("target not supported: " + target)

        self.target = target

        self.accumVal = self.defaultAccum
        self.accumCount = 0
        self.accumTime = 0
        self.history_length = history_length

        # To avoid extra lock calls, the historian actually briefly takes over the tag's lock.
        self.lock = tag.lock

        self.lastLogged = 0
        self.interval = interval

        self.getChannelID(tag)

        with historian.lock:
            historian.children[id(self)] = weakref.ref(self)

        tag.subscribe(self.accumulate)

        # Log immediately when we setup logger settings.  Helps avoid confusion for tags that never change.
        if tag.lock.acquire():
            try:
                self.accumulate(tag.value, tag.timestamp, tag.annotation)
            finally:
                tag.lock.release()

    def insertData(self, d):
        self.h.insertData(d)

    def clearOldData(self, force=False):
        "Only called by the historian, that's why we can reuse the connection and do everything in one transaction"
        if not self.history_length:
            return

        # Attempt to detect impossible times indicating the clock is wrong.
        if time.time() < 1597447271:
            return

        with self.h.lock:
            conn = sqlite3.Connection(self.filename)

            c = conn.cursor()
            c.execute(
                "SELECT count(*) FROM record WHERE channel=? AND time<?",
                (
                    self.chID,
                    ts_to_iso(time.time() - self.history_length),
                ),
            )
            count = c.fetchone()[0]

            # Only delete records in large blocks. To do otherwise would create too much disk wear
            if count > 8192 if not force else 1024:
                c.execute(
                    "DELETE FROM record WHERE channel=? AND time<?",
                    (
                        self.chID,
                        ts_to_iso(time.time() - self.history_length),
                    ),
                )
            conn.close()

    def getDataRange(self, minTime, maxTime, maxRecords=10000):
        with self.h.lock:
            d = []
            conn = sqlite3.Connection(self.filename)

            c = conn.cursor()
            c.execute(
                "SELECT time,value FROM record WHERE time>? AND time<? AND channel=? ORDER BY time ASC LIMIT ?",
                (ts_to_iso(minTime), ts_to_iso(maxTime), self.chID, maxRecords),
            )
            for i in c:
                d.append(i)

            x = []
            for safety_counter in range(10):
                x = []
                # Best-effort attempt to include recent stuff.
                # We don't want to use another lock and slow stuff down
                try:
                    for i in self.h.pending:
                        if i[0] == self.chID:
                            if i[1] >= minTime and i[1] <= maxTime:
                                x.append((i[1], i[2]))
                    break
                # Can fail due to iterationerror, we don't lock the pending list,
                # We just hope we can finish very fast.
                except Exception:
                    raise
            conn.close()

            return (d + x)[:maxRecords]

    def getRecent(self, minTime, maxTime, maxRecords=10000):
        with self.h.lock:
            d = []
            conn = sqlite3.Connection(self.filename)

            c = conn.cursor()
            c.execute(
                "SELECT time,value FROM record WHERE time>? AND time<? AND channel=? ORDER BY time DESC LIMIT ?",
                (ts_to_iso(minTime), ts_to_iso(maxTime), self.chID, maxRecords),
            )
            for i in c:
                d.append(i)

            x = []
            for safety_counter in range(15):
                x = []
                # Best-effort attempt to include recent stuff.
                # We don't want to use another lock and slow stuff down
                try:
                    for i in self.h.pending:
                        if i[0] == self.chID:
                            if i[1] >= minTime and i[1] <= maxTime:
                                x.append((i[1], i[2]))
                    break
                # Can fail due to iterationerror, we don't lock the pending list,
                # We just hope we can finish very fast.
                except Exception:
                    raise

            return (list(reversed(d)) + x)[-maxRecords:]

    def __del__(self):
        with historian.lock:
            del historian.children[id(self)]

    def accumulate(self, value, time, annotation):
        "Only ever called by the tag"
        self.accumVal = value
        self.accumTime = time
        self.accumCount = 1
        if isinstance(value, (int, float, bytes)):
            pass

        elif isinstance(value, str):
            value = value[: 1024 * 128]

        elif isinstance(value, (list, dict, tuple)):
            value = json.dumps(value)

        self.flush()

    # Only call from accumulate or from within the historian, which will use the taglock to call this.
    def flush(self, force=False):
        # Ratelimit how often we log, continue accumulating if nothing to log.
        if not force:
            if self.lastLogged > time.time() - self.interval:
                return

        self.insertData((self.chID, self.accumTime, self.accumVal))
        self.lastLogged = time.time()
        self.accumCount = 0
        self.accumVal = self.defaultAccum

    def getChannelID(self, tag):
        # Either get our stored channel name, or create a new onw
        with self.h.lock:
            # Have to make our own, we are in a new thread now.
            conn = sqlite3.Connection(self.filename)
            conn.row_factory = sqlite3.Row

            c = conn.cursor()
            c.execute(
                "SELECT id,name,unit,accumulate from channel WHERE name=?",
                (tag.name,),
            )
            self.chID = None

            if not isinstance(tag.unit, str):
                raise ValueError("bad tag unit " + str(tag.unit))

            if not isinstance(self.accumType, str):
                raise ValueError("bad tag accum " + str(self.accumType))

            for i in c:
                if (
                    i["name"] == tag.name
                    and i["unit"] == tag.unit
                    and i["accumulate"] == self.accumType
                ):
                    self.chID = i["id"]

            if not self.chID:
                conn.execute(
                    "INSERT INTO channel VALUES (?,?,?,?,?)",
                    (None, tag.name, tag.unit, self.accumType, "{}"),
                )
                conn.commit()

            c = conn.cursor()
            c.execute(
                "SELECT id from channel WHERE name=? AND unit=? AND accumulate=?",
                (tag.name, tag.unit, self.accumType),
            )
            self.chID = c.fetchone()[0]

            conn.close()


class AverageLogger(TagLogger):
    accumType = "mean"

    def accumulate(self, value, time, annotation):
        "Only ever called by the tag"
        self.accumVal += value
        self.accumTime += time
        self.accumCount += 1
        self.flush()

    # Only call from accumulate or from within the historian, which will use the taglock to call this.
    def flush(self, force=False):
        # Ratelimit how often we log, continue accumulating if nothing to log.
        if not force:
            if self.lastLogged > time.time() - self.interval:
                return

        self.insertData(
            (
                self.chID,
                (self.accumTime / self.accumCount),
                self.accumVal / self.accumCount,
            )
        )
        self.lastLogged = time.time()
        self.accumCount = 0
        self.accumVal = 0
        self.accumTime = 0


class MinLogger(TagLogger):
    accumType = "min"
    defaultAccum = 10**18

    def accumulate(self, value, time, annotation):
        "Only ever called by the tag"
        self.accumVal = min(self.accumVal, value)
        self.accumTime += time
        self.accumCount += 1

        self.flush()

    # Only call from accumulate or from within the historian, which will use the taglock to call this.
    def flush(self, force=False):
        # Ratelimit how often we log, continue accumulating if nothing to log.
        if not force:
            if self.lastLogged > time.time() - self.interval:
                return

        self.insertData(
            (self.chID, (self.accumTime / self.accumCount), self.accumVal)
        )
        self.lastLogged = time.time()
        self.accumCount = 0
        self.accumVal = 10**18
        self.accumTime = 0


class MaxLogger(MinLogger):
    accumType = "max"
    defaultAccum = -(10**18)

    def accumulate(self, value, time, annotation):
        "Only ever called by the tag"
        self.accumVal = max(self.accumVal, value)
        self.accumTime += time
        self.accumCount += 1

        self.flush()

    # Only call from accumulate or from within the historian, which will use the taglock to call this.
    def flush(self, force=False):
        # Ratelimit how often we log, continue accumulating if nothing to log.
        if not force:
            if self.lastLogged > time.time() - self.interval:
                return

        self.insertData(
            (self.chID, (self.accumTime / self.accumCount), self.accumVal)
        )
        self.lastLogged = time.time()
        self.accumCount = 0
        self.accumVal = -(10**18)
        self.accumTime = 0


accumTypes = {
    "latest": TagLogger,
    "mean": AverageLogger,
    "max": MaxLogger,
    "min": MinLogger,
}


class TagHistorian:
    # Generated puely randomly
    appID = 707898159

    def __init__(self, file):
        if not os.path.exists(file):
            newfile = True
        else:
            newfile = False

        self.history = sqlite3.Connection(file)

        try:
            self.history.execute(
                """CREATE TABLE IF NOT EXISTS channel  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name text, unit text, accumulate text, metadata text)"""
            )
        except Exception:
            shutil.move(file, file + ".error_archived")
            newfile = True
            self.history = sqlite3.Connection(file)

        self.history.row_factory = sqlite3.Row
        self.filename = file

        if newfile:
            self.history.execute("PRAGMA application_id = 707898159")
        self.lock = threading.RLock()
        self.children = {}

        self.history.execute(
            """CREATE TABLE IF NOT EXISTS channel  (id INTEGER PRIMARY KEY AUTOINCREMENT,
            name text, unit text, accumulate text, metadata text)"""
        )
        self.history.execute(
            """CREATE TABLE IF NOT EXISTS record  (channel INTEGER,
            time TEXT, value REAL, FOREIGN KEY(channel) REFERENCES channel(id))"""
        )

        self.history.execute(
            """CREATE VIEW IF NOT EXISTS SimpleViewLocalTime AS SELECT
            channel.name as Channel,
            channel.accumulate as Type,
            record.time as LocalTime,
              record.value as Value,
              channel.unit as Unit FROM record INNER JOIN channel ON channel.id = record.channel;"""
        )
        self.history.execute(
            """CREATE VIEW IF NOT EXISTS SimpleViewUTC AS SELECT
              channel.name as Channel,
              channel.accumulate as Type,
              record.time as UTCTime,
              record.value as Value,
              channel.unit as Unit FROM record INNER JOIN channel ON channel.id = record.channel;"""
        )

        # TODO: Legacy compatibility
        try:
            self.history.execute("""ALTER TABLE record
                RENAME COLUMN tagName TO name;""")
            self.history.execute("""ALTER TABLE channel
                    RENAME COLUMN tagName TO name;""")
        except Exception:
            pass

        self.pending = []

        self.history.close()

        self.lastFlushed = time.time()

        self.lastGarbageCollected = 0

        self.flushInterval = 10 * 60

        self.gcInterval = 3600 * 2

        messagebus.subscribe("/system/save", self.forceFlush)

        def f():
            self.flush()

        self.flusher_f = f
        self.flusher = scheduling.scheduler.every_minute(f)

    def insertData(self, d):
        self.pending.append(d)

    def forceFlush(self):
        self.flush(True)

    def flush(self, force=False):
        if not force:
            if time.time() - self.lastFlushed < self.flushInterval:
                return
            self.lastFlushed = time.time()

        with self.lock:
            needsGC = self.lastGarbageCollected < time.time() - self.gcInterval
            if needsGC:
                self.lastGarbageCollected = time.time()
            if force:
                needsGC = 1

            # Unfortunately, we still have to do some polling here.
            # The reason is that we could have a change immediately followed by another change,
            # and it is important that we eventually
            # record that new change.
            for i in self.children:
                x = self.children[i]()
                if x:
                    with x.lock:
                        if x.accumCount:
                            x.flush(force)

            pending = self.pending
            self.pending = []
            # Hopefully let any other threads finish
            # inserting into the old list . Note that here we consider very rarely losing a record
            # to be better than bad performace

            for i in range(30):
                time.sleep(0.001)

            self.history = sqlite3.Connection(self.filename)
            with self.history:
                if needsGC:
                    for i in self.children:
                        x = self.children[i]()
                        if x:
                            with x.lock:
                                x.clearOldData(force)

                for i in pending:
                    self.history.execute(
                        "INSERT INTO record VALUES (?,?,?)",
                        (i[0], ts_to_iso(i[1]), i[2]),
                    )
            self.history.close()


try:
    historian = TagHistorian(newHistoryDBFile)
    ramHistorian = TagHistorian(ramdbfile)
    os.chmod(ramdbfile, 0o750)
except Exception:
    messagebus.post_message(
        "/system/notifications/errors",
        "Failed to create tag historian, logging will not work."
        + "\n"
        + traceback.format_exc(),
    )


loggers: dict[tuple[str, str], TagLogger] = {}

pending: dict[tuple[str, str], Callable] = {}


class LoggerType(modules_state.ResourceType):
    def blurb(self, m, r, value):
        return f"""
        <div>
            <form  action="/plugin-tag-history/{quote(value['tag'], safe='')}" method="post">
                <button>View Logs</button>
            </form>
        </div>
        """

    def on_load(self, module, resourcename, value):
        cls = accumTypes[value["logger_type"]]

        def f(v=None):
            t = tagpoints.allTagsAtomic.get(value["tag"], None)
            if not t:
                return
            t = t()
            if not t:
                return
            loggers[module, resourcename] = cls(
                t,
                float(value["interval"]),
                int(value["history_length"]),
                value["log_target"],
            )

            t.configLoggers[module, resourcename] = loggers[
                module, resourcename
            ]

            pending.pop(module, resourcename)
            messagebus.unsubscribe("/system/tags/created", f)

        pending[module, resourcename] = f

        if value["tag"] in tagpoints.allTagsAtomic:
            f()
        else:
            # Do it later when ye olde tag existe.
            messagebus.subscribe("/system/tags/created", f)

    def on_move(self, module, resource, to_module, to_resource, resourceobj):
        x = loggers.pop((module, resource), None)
        if x:
            loggers[to_module, to_resource] = x

    def on_update(self, module, resource, obj):
        self.on_load(module, resource, obj)

    def on_delete(self, module, name, value):
        del loggers[module, name]

    def on_create_request(self, module, name, kwargs):
        d = {"resource_type": self.type}
        d.update(kwargs)
        d.pop("name")
        d.pop("Save", None)

        return d

    def on_update_request(self, module, resource, resourceobj, kwargs):
        d = resourceobj
        d.update(kwargs)
        d.pop("name", None)
        d.pop("Save", None)
        return d

    def create_page(self, module, path):
        d = dialogs.SimpleDialog("New Logger")
        d.text_input("name", title="Logger Name")
        d.text_input(
            "tag",
            title="Tag Point to Log",
            suggestions=[(i, i) for i in tagsapi.all_tags_raw().keys()],
        )
        d.selection(
            "logger_type",
            options=list(accumTypes.keys()),
            title="Accumulate Mode",
        )
        d.selection("log_target", options=["disk", "ram"])
        d.text_input("interval", title="Interval(seconds)", default=str(60))
        d.text_input(
            "history_length",
            title="History Length(seconds)",
            default=str(24 * 30 * 3600),
        )

        d.submit_button("Save")
        return d.render(self.get_create_target(module, path))

    def edit_page(self, module, name, value):
        d = dialogs.SimpleDialog("Editing Logger")
        d.text_input(
            "tag",
            title="Tag Point to Log",
            default=value["tag"],
            suggestions=[(i, i) for i in tagsapi.all_tags_raw().keys()],
        )
        d.selection(
            "logger_type",
            options=list(accumTypes.keys()),
            default=value["logger_type"],
            title="Accumulate Mode",
        )
        d.selection(
            "log_target", options=["disk", "ram"], default=value["log_target"]
        )
        d.text_input(
            "interval", title="Interval(seconds)", default=value["interval"]
        )
        d.text_input(
            "history_length",
            title="History Length(seconds)",
            default=value["history_length"],
        )

        d.submit_button("Save")
        return d.render(self.get_update_target(module, name))


drt = LoggerType("logger", mdi_icon="sine-wave")
modules_state.additionalTypes["logger"] = drt


t = os.path.join(os.path.dirname(__file__), "html", "logpage.html")


@quart_app.app.route("/plugin-tag-history", methods=["GET", "POST"])
@quart_app.app.route("/plugin-tag-history/<path:path>", methods=["GET", "POST"])
@quart_app.wrap_sync_route_handler
def logpage(path: str = "", **kwargs):
    pages.require("system_admin")
    path = "/" + path
    # This page could be slow because of the db stuff, so we restrict it more
    if not quart.request.method.lower() == "post":
        raise RuntimeError("POST only")

    if "exportRows" not in kwargs:
        return pages.get_template(t).render(tagName=path, data=kwargs)
    else:
        tag = tagpoints.allTags[path]()
        if tag is None:
            raise RuntimeError("This tag seems to no longer exist")

        for key, i in tag.configLoggers.items():
            if i.accumType == kwargs["exportType"]:
                tz = pytz.timezone("Etc/UTC")
                logtime = tz.localize(
                    dateutil.parser.parse(kwargs["logtime"])
                ).timestamp()
                raw = i.getDataRange(
                    logtime, time.time() + 10000000, int(kwargs["exportRows"])
                )

                if kwargs["exportFormat"] == "csv.iso":
                    filename = (
                        path.replace("/", "_")
                        .replace(".", "_")
                        .replace(":", "_")[1:]
                        + "_"
                        + kwargs["exportType"]
                        + tz.localize(
                            dateutil.parser.parse(kwargs["logtime"])
                        ).isoformat()
                        + ".csv"
                    )

                    d = [
                        "Time(ISO), "
                        + path.replace(",", "")
                        + " <accum "
                        + kwargs["exportType"]
                        + ">"
                    ]
                    for i in raw:
                        d.append(str(i[0]) + "," + str(i[1])[:128])
                    return quart.Response(
                        "\r\n".join(d) + "\r\n",
                        content_type="text/csv",
                        headers={
                            "Content-Disposition": "attachment; filename="
                            + filename
                        },
                    )

        raise RuntimeError("Logger not found")
