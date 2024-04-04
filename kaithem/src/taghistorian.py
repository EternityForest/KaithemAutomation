from . import directories, messagebus, scheduling
import os
import weakref
import time
import sqlite3
import logging
import traceback
import threading
import getpass
import socket
import shutil
import json

oldlogdir = os.path.join(directories.vardir, "logs")
logdir = directories.logdir
ramdbfile = "/dev/shm/" + socket.gethostname()+"-"+getpass.getuser()+"-taghistory.ldb"


syslogger = logging.getLogger("system")

if not os.path.exists(logdir):
    try:
        os.makedirs(logdir)
    except Exception:
        syslogger.exception("Can't make log dir")

# Build a filename including the hostname and user.   This is because SQLite may not be happy to be involved with SyncThing.
# For that reason, should someone get the bright idea to sync a kaithem vardir, we must keep the history databases single-writer.

# Plus, there is nothing in the DB itself to tell us who wrote it, so this is very convenient.
historyFilemame = socket.gethostname()+"-"+getpass.getuser()+"-taghistory.ldb"

newHistoryDBFile = os.path.join(logdir, historyFilemame)


class TagLogger():
    """Base class for the object associated with one tag point for logging
     a specific type(min,max,avg,etc) of data from that tag"""
    accumType = 'latest'
    defaultAccum = 0

    def __init__(self, tag, interval, historyLength=3 * 30 * 24 * 3600, target='disk'):

        # We can have purely ram file based logging
        if target == 'disk':
            self.h = historian
            self.filename = newHistoryDBFile
        elif target == 'ram':
            self.h = ramHistorian
            self.filename = ramdbfile
        else:
            raise ValueError("target not supported: "+target)

        self.target = target

        self.accumVal = self.defaultAccum
        self.accumCount = 0
        self.accumTime = 0
        self.historyLength = historyLength

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
        if not self.historyLength:
            return

        # Attempt to detect impossible times indicating the clock is wrong.
        if time.time() < 1597447271:
            return

        with self.h.lock:
            conn = sqlite3.Connection(self.filename)

            c = conn.cursor()
            c.execute("SELECT count(*) FROM record WHERE channel=? AND timestamp<?",
                      (self.chID, time.time() - self.historyLength))
            count = c.fetchone()[0]

            # Only delete records in large blocks. To do otherwise would create too much disk wear
            if count > 8192 if not force else 1024:
                c.execute("DELETE FROM record WHERE channel=? AND timestamp<?",
                          (self.chID, time.time() - self.historyLength))
            conn.close()

    def getDataRange(self, minTime, maxTime, maxRecords=10000):
        with self.h.lock:
            d = []
            conn = sqlite3.Connection(self.filename)

            c = conn.cursor()
            c.execute("SELECT timestamp,value FROM record WHERE timestamp>? AND timestamp<? AND channel=? ORDER BY timestamp ASC LIMIT ?",
                      (minTime, maxTime, self.chID, maxRecords))
            for i in c:
                d.append(i)

            x = []
            for l in range(10):
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
            c.execute("SELECT timestamp,value FROM record WHERE timestamp>? AND timestamp<? AND channel=? ORDER BY timestamp DESC LIMIT ?",
                      (minTime, maxTime, self.chID, maxRecords))
            for i in c:
                d.append(i)

            x = []
            for l in range(15):
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

    def accumulate(self, value, timestamp, annotation):
        "Only ever called by the tag"
        self.accumVal = value
        self.accumTime = timestamp
        self.accumCount = 1
        if isinstance(value, (int, float, bytes)):
            pass

        elif isinstance(value, str):
            value = value[:1024*128]

        elif isinstance(value, (list, dict, tuple)):
            value = json.dumps(value)

        self.flush()

    # Only call from accumulate or from within the historian, which will use the taglock to call this.
    def flush(self, force=False):
        # Ratelimit how often we log, continue accumulating if nothing to log.
        if not force:
            if self.lastLogged > time.monotonic() - self.interval:
                return

        offset = time.time() - time.monotonic()
        self.insertData((self.chID, self.accumTime + offset, self.accumVal))
        self.lastLogged = time.monotonic()
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
                "SELECT rowid,tagName,unit,accumulate from channel WHERE tagName=?", (tag.name,))
            self.chID = None

            if not isinstance(tag.unit, str):
                raise ValueError('bad tag unit ' + str(tag.unit))

            if not isinstance(self.accumType, str):
                raise ValueError('bad tag accum ' + str(self.accumType))

            for i in c:
                if i['tagName'] == tag.name and i['unit'] == tag.unit and i['accumulate'] == self.accumType:
                    self.chID = i['rowid']

            if not self.chID:
                conn.execute("INSERT INTO channel VALUES (?,?,?,?)",
                             (tag.name, tag.unit, self.accumType, '{}'))
                conn.commit()

            c = conn.cursor()
            c.execute("SELECT rowid from channel WHERE tagName=? AND unit=? AND accumulate=?",
                      (tag.name, tag.unit, self.accumType))
            self.chID = c.fetchone()[0]

            conn.close()


class AverageLogger(TagLogger):
    accumType = 'mean'

    def accumulate(self, value, timestamp, annotation):
        "Only ever called by the tag"
        self.accumVal += value
        self.accumTime += timestamp
        self.accumCount += 1
        self.flush()

    # Only call from accumulate or from within the historian, which will use the taglock to call this.
    def flush(self, force=False):
        # Ratelimit how often we log, continue accumulating if nothing to log.
        if not force:
            if self.lastLogged > time.monotonic() - self.interval:
                return
        offset = time.time() - time.monotonic()

        self.insertData(
            (self.chID, (self.accumTime / self.accumCount) + offset, self.accumVal / self.accumCount))
        self.lastLogged = time.monotonic()
        self.accumCount = 0
        self.accumVal = 0
        self.accumTime = 0


class MinLogger(TagLogger):
    accumType = 'min'
    defaultAccum = 10**18

    def accumulate(self, value, timestamp, annotation):
        "Only ever called by the tag"
        self.accumVal = min(self.accumVal, value)
        self.accumTime += timestamp
        self.accumCount += 1

        self.flush()

    # Only call from accumulate or from within the historian, which will use the taglock to call this.
    def flush(self, force=False):
        # Ratelimit how often we log, continue accumulating if nothing to log.
        if not force:
            if self.lastLogged > time.monotonic() - self.interval:
                return

        offset = time.time() - time.monotonic()
        self.insertData(
            (self.chID, (self.accumTime / self.accumCount) + offset, self.accumVal))
        self.lastLogged = time.monotonic()
        self.accumCount = 0
        self.accumVal = 10**18
        self.accumTime = 0


class MaxLogger(MinLogger):
    accumType = 'max'
    defaultAccum = -10**18

    def accumulate(self, value, timestamp, annotation):
        "Only ever called by the tag"
        self.accumVal = max(self.accumVal, value)
        self.accumTime += timestamp
        self.accumCount += 1

        self.flush()

    # Only call from accumulate or from within the historian, which will use the taglock to call this.
    def flush(self, force=False):
        # Ratelimit how often we log, continue accumulating if nothing to log.
        if not force:
            if self.lastLogged > time.monotonic() - self.interval:
                return

        offset = time.time() - time.monotonic()
        self.insertData(
            (self.chID, (self.accumTime / self.accumCount) + offset, self.accumVal))
        self.lastLogged = time.monotonic()
        self.accumCount = 0
        self.accumVal = -10**18
        self.accumTime = 0


accumTypes = {'replace': TagLogger, 'latest': TagLogger,
              'mean': AverageLogger, 'max': MaxLogger, 'min': MinLogger}


class TagHistorian():
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
                "CREATE TABLE IF NOT EXISTS channel  (tagName text, unit text, accumulate text, metadata text)")
        except Exception:
            shutil.move(file, file+".error_archived")
            newfile = True
            self.history = sqlite3.Connection(file)

        self.history.row_factory = sqlite3.Row
        self.filename = file

        if newfile:
            self.history.execute("PRAGMA application_id = 707898159")
        self.lock = threading.RLock()
        self.children = {}

        self.history.execute(
            "CREATE TABLE IF NOT EXISTS channel  (tagName text, unit text, accumulate text, metadata text)")
        self.history.execute(
            "CREATE TABLE IF NOT EXISTS record  (channel INTEGER, timestamp INTEGER, value REAL)")

        self.history.execute("CREATE VIEW IF NOT EXISTS SimpleViewLocalTime AS SELECT channel.tagName as Channel, channel.accumulate as Type, datetime(record.timestamp,'unixepoch','localtime') as LocalTime, record.value as Value, channel.unit as Unit FROM record INNER JOIN channel ON channel.rowid = record.channel;")
        self.history.execute("CREATE VIEW IF NOT EXISTS SimpleViewUTC AS SELECT channel.tagName as Channel, channel.accumulate as Type,  datetime(record.timestamp,'unixepoch','utc') as UTCTime, record.value as Value, channel.unit as Unit FROM record INNER JOIN channel ON channel.rowid = record.channel;")

        self.pending = []

        self.history.close()

        self.lastFlushed = time.monotonic()

        self.lastGarbageCollected = 0

        self.flushInterval = 10 * 60

        self.gcInterval = 3600 * 2

        messagebus.subscribe("/system/save", self.forceFlush)

        def f():
            self.flush()

        self.flusher_f = f
        self.flusher = scheduling.scheduler.everyMinute(f)

    def insertData(self, d):
        self.pending.append(d)

    def forceFlush(self):
        self.flush(True)

    def flush(self, force=False):
        if not force:
            if time.monotonic() - self.lastFlushed < self.flushInterval:
                return
            self.lastFlushed = time.monotonic()

        with self.lock:
            needsGC = self.lastGarbageCollected < time.monotonic() - self.gcInterval
            if needsGC:
                self.lastGarbageCollected = time.monotonic()
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
                        'INSERT INTO record VALUES (?,?,?)', i)
            self.history.close()


try:
    historian = TagHistorian(newHistoryDBFile)
    ramHistorian = TagHistorian(ramdbfile)
    os.chmod(ramdbfile, 0o750)
except Exception:
    messagebus.post_message("/system/notifications/errors",
                            "Failed to create tag historian, logging will not work." + "\n" + traceback.format_exc())
