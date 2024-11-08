# SPDX-FileCopyrightText: Copyright 2016 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


import atexit
import bz2
import gc
import getpass
import gzip
import io
import logging
import os
import random
import re
import shutil
import textwrap
import threading
import time
import traceback
import weakref

from . import directories, messagebus, unitsofmeasure, util
from .config import config

configuredHandlers = {}

all_handlers = weakref.WeakValueDictionary()

logging.basicConfig(level=logging.INFO)


def at_exit():
    """
    Try to flush all the loggers as best we can at interpreter shutdown
    maybe fix so it doesn't have a threading issue where something could go away during
    iteration #TODO
    """
    try:
        for i in all_handlers:
            try:
                all_handlers[i].close()
            except Exception:
                pass
    except Exception:
        pass

    # This lets us tell a clean shutdown from something like a segfault
    if os.path.exists("/dev/shm"):
        try:
            with open(f"/dev/shm/shutdowntime_{getpass.getuser()}", "w") as f:
                f.write(str(time.time()))
        except Exception:
            print(traceback.format_exc())


atexit.register(at_exit)


class KFormatter(logging.Formatter):
    def formatException(self, exc_info):
        return "\n".join(
            textwrap.wrap(
                logging.Formatter.formatException(self, exc_info),
                initial_indent="  ",
                subsequent_indent="  ",
                width=80,
            )
        )


lastRaisedLogFailError = [0.0]


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


def rateLimitedRaise(e):
    # This is really bad to just let this error pass most of the time.
    # But if we don't, a no space left on device thing could be a cascading failure.
    # I don't even want to print anything lest systemd try to log it and make this situation worse.
    if lastRaisedLogFailError[0] < (time.time() - 1800):
        lastRaisedLogFailError[0] = time.time()
        print(traceback.format_exc())
        raise e


class LoggingHandler(logging.Handler):
    def __init__(
        self,
        name,
        folder,
        fn,
        bufferlen=25000,
        level=30,
        contextlevel=10,
        contextbuffer=0,
        entries_per_file=25000,
        keep=10,
        compress="none",
        doprint=False,
        exclude_print="",
    ):
        """Implements a memory-buffered context logger with automatic log rotation.
        Log entries are kept in memory until the in memory buffer exceeds bufferlen entries.
        When that happens,logs are dumped to a file named fn_TIMESTAMP.FRACTIONALPART.log,
        fn_TIMESTAMP.FRACTIONALPART.log.gz, or fn_TIMESTAMP.FRACTIONALPART.log.bz2.

        Log records below level are normally ignored, however in they are
        above contextlevel the most recent contextbuffer logs are kept in memory,
        and are flushed to the main logging buffer just before writing the next
        log record that is above level. In this way more important log messages
        will record a bit of "context".

        The program will continue writing to the same file until it writes entries_per_file
        to it, after which point it will move to a new file. Restarting the program will
        always cause a new file to be opened.
        """
        logging.Handler.__init__(self)
        if not compress == "none":
            if not bufferlen == entries_per_file:
                raise ValueError(
                    "entries_per_file must == bufferlen when using compression as compressed files cannot be efficiently appended"
                )
        self.name = name
        self.fn = fn
        self.doprint = doprint
        self.exclude_print = exclude_print

        self.folder = folder
        self.bufferlen = bufferlen
        self.contextlen = contextbuffer
        # How many MB of old logs to keep around
        self.keep = keep
        self.level = level
        self.contextlevel = contextlevel
        self.contextbuffer = []
        self.logbuffer = []
        self.lock = threading.Lock()
        self.savelock = threading.RLock()
        self.compress = compress
        self.entries_per_file = entries_per_file
        self.flush_before_close = True
        # The file we are writing to right now
        self.current_file = None

        self.isShmHandler = False

        # How many entries have we dumped to the file already?
        self.counter = 0
        # and how many bytes
        self.bytecounter = 0
        # This callback is for when we want to use this handler as a filter.
        self.callback = lambda x: x
        logging.getLogger().addHandler(self)
        formatter = KFormatter("%(message)s", "%Y%b%d %H:%M:%S %Z")
        self.setFormatter(formatter)
        all_handlers[(time.time(), random.random(), self.name)] = self

    def close(self):
        if self.flush_before_close:
            self.flush()
        logging.Handler.close(self)
        try:
            logging.getLogger().removeHandler(self)
        except Exception:
            pass

    def filter(self, record) -> bool:
        return super().filter(record)

    def handle(self, record):
        """Watch out with this. We are overriding the handle method so we can do our own locking."""

        rv = self.filter(record)

        if rv:
            self.emit(record)
        return rv

    def emit(self, record):
        # We handle all logs that make it to the root logger, and do the filtering ourselves
        raw = self.format(record)
        txt = strip_ansi_colour(raw)
        if self.doprint:
            if not self.exclude_print or (
                not (
                    record.name == self.exclude_print
                    or record.name.startswith(f"{self.exclude_print}.")
                )
            ):
                print(raw)

        self.callback(record)
        with self.lock:
            if record.levelno >= self.contextlevel:
                self.logbuffer.extend(self.contextbuffer)
                self.contextbuffer = []
                self.logbuffer.append(txt)
            # That truncation operation will actulally do nothing if the contextlen is 0
            elif self.contextlen:
                self.contextbuffer.append(txt)
                self.contextbuffer = self.contextbuffer[-self.contextlen :]

        if len(self.logbuffer) >= self.bufferlen:
            try:
                self.flush()
            except Exception as e:
                try:
                    # If it is getting really insane with the space usage due to unforseen bugs, just drop some logs.
                    if len(self.logbuffer) >= (self.bufferlen * 8):
                        self.logbuffer = self.logbuffer[-50:]
                        self.contextbuffer = []
                except Exception:
                    pass

                print(traceback.format_exc())
                print(f"Log flush error {repr(e)}")
                # logging.exception("error flushing logs with handler "+repr(self))

    def flush(self):
        """Flush all log entires that belong to topics that are in the list of things to save, and clear the staging area"""
        with self.savelock:
            # Allow null logging handlers that are only used for realtime displays
            if self.fn is None:
                self.logbuffer = []
                return

            if config["log_format"] == "none":
                self.logbuffer = []
                return

            # If there is no log entries to save, don't dump an empty file.
            if not self.logbuffer:
                return

            if self.compress == "bz2":
                openlog = bz2.BZ2File
                ext = ".log.bz2"

            elif self.compress == "gzip" or self.compress == "gz":
                openlog = gzip.GzipFile
                ext = ".log.gz"

            elif self.compress == "none":
                openlog = open
                ext = ".log"

            else:
                openlog = open
                ext = ".log"
                print(
                    "Invalid config option for 'log-compress' so defaulting to no compression"
                )

            # Swap out the log buffers so we can work with an immutable copy
            # That way we don't block anything that tries to write a log for the entirety of
            # the formatting process.
            with self.lock:
                logbuffer = self.logbuffer
                self.logbuffer = []
            # fixme in an editor that can unindent
            if True:
                if not os.path.exists(self.folder):
                    try:
                        os.makedirs(self.folder)
                    except Exception as e:
                        # Swap them back so we can flush later, but don't hoard too many
                        self.logbuffer = logbuffer[-256:]
                        # Sometimes the problem is that garbage collection
                        # Hasn't gotten to a bunch of sockets yet
                        gc.collect()
                        rateLimitedRaise(e)

                # Actually dump the log.
                t = time.time()
                if not self.current_file:
                    fn = os.path.join(self.folder, f"{self.fn}_{str(t)}{ext}")
                    self.current_file = fn
                else:
                    fn = self.current_file

                # We can't append to gz and bz2 files efficiently, so we dissalow using those for anything
                # except one file buffered dumps
                # TODO: TOo Many Open Files error
                chmodflag = not os.path.exists(self.current_file)
                try:
                    with openlog(
                        self.current_file,
                        "ba" if self.compress == "none" else "wb",
                    ) as f:
                        if chmodflag:
                            util.chmod_private_try(fn)
                        for i in logbuffer:
                            b = f"{i}\r\n".encode()
                            self.bytecounter += len(b)
                            f.write(b)
                    # Keep track of how many we have written to the file
                    self.counter += len(logbuffer)

                except PermissionError as e:
                    # Swap them back so we can flush later, but don't hoard too many
                    self.logbuffer = logbuffer[-32:]
                    self.contextbuffer = []
                    # Sometimes the problem is that garbage collection
                    # Hasn't gotten to a bunch of sockets yet
                    gc.collect()
                    rateLimitedRaise(e)

                except OSError as e:
                    # Swap them back so we can flush later, but don't hoard too many
                    self.logbuffer = logbuffer[-32:]
                    self.contextbuffer = []
                    # Sometimes the problem is that garbage collection
                    # Hasn't gotten to a bunch of sockets yet
                    gc.collect()
                    rateLimitedRaise(e)

                except Exception as e:
                    self.contextbuffer = []
                    self.logbuffer = logbuffer[-32:]
                    # Sometimes the problem is that garbage collection
                    # Hasn't gotten to a bunch of sockets yet
                    gc.collect()
                    rateLimitedRaise(e)

                # If we have filled up one file, we close it, and let the logic
                # for the next dump decide what to do about it.
                # Always start a new file after a compressed dump.
                if (
                    self.counter >= self.entries_per_file
                ) or not self.compress == "none":
                    self.current_file = None
                    self.counter = 0
                    self.bytecounter = 0

                # We really don't want all the logs in one file because of how we delete them
                # One file at a time.
                if self.bytecounter > (self.keep / 8):
                    self.current_file = None
                    self.counter = 0
                    self.bytecounter = 0

            # Make a list of our log dump files.
            asnumbers = {}
            for i in util.get_files(self.folder):
                if not re.match(f"{self.fn}_[0-9]+(.[0-9]+)?\\.log(\\..*)?", i):
                    continue
                try:
                    # Our filename format dictates that the last _ comes before the number and ext
                    j = i.split("_")[-1]
                    # Remove extensions
                    if i.endswith(".log"):
                        asnumbers[float(j[:-4])] = i
                    elif i.endswith(".log.gz"):
                        asnumbers[float(j[:-7])] = i
                    elif i.endswith(".log.bz2"):
                        asnumbers[float(j[:-8])] = i
                except ValueError:
                    pass

            maxsize = self.keep
            size = 0
            # Loop over all the old log dumps and add up the sizes
            for i in asnumbers.values():
                size = size + os.path.getsize(os.path.join(self.folder, i))

            # Get rid of oldest log dumps until the total size is within the limit
            for i in sorted(asnumbers.values()):
                if size <= maxsize:
                    break
                size = size - os.path.getsize(os.path.join(self.folder, i))
                os.remove(os.path.join(self.folder, i))


# Don't print, the root logger does that.
syslogger = LoggingHandler(
    "root",
    fn="system",
    folder=os.path.join(directories.logdir, "dumps"),
    level=logging.INFO,
    entries_per_file=config["log_dump_size"],
    bufferlen=config["log_buffer"],
    keep=unitsofmeasure.str_to_int_si_multipliers(config["keep_log_files"]),
    compress=config["log_compress"],
    doprint=False,
)

logging.getLogger().addHandler(syslogger)

# Linux only way of recovering backups even if the
if os.path.exists(f"/dev/shm/kaithemdbglog_{getpass.getuser()}"):
    if not os.path.exists(f"/dev/shm/shutdowntime_{getpass.getuser()}"):
        try:
            shutil.copytree(
                f"/dev/shm/kaithemdbglog_{getpass.getuser()}",
                f"/dev/shm/kaithemdbglogbackup_{getpass.getuser()}",
            )
        except Exception:
            pass

        try:
            shutil.rmtree(f"/dev/shm/kaithemdbglog_{getpass.getuser()}")
        except Exception:
            pass

        messagebus.post_message(
            "/system/notifications/errors",
            """Kaithem may have shutdown uncleanly due to a segfault, kill-9, or similar.
        Recovered logs have been backed up to '/dev/shm/kaithemdbglogbackup'
        """,
        )


# This lets us tell a clean shutdown from something like a segfault.
# Remove it, and if it's not back by next time, but somehow there's still log files,
# We know that there was a problem, and we can report that.
if os.path.exists("/dev/shm"):
    try:
        os.remove(f"/dev/shm/shutdowntime_{getpass.getuser()}")
    except Exception:
        pass


# This buffer stores 100K of the most recent of all system logs in /dev/shm.
# This should be made configurable for people with multiple instances, but for now
# This is better than nothing, because it gives us a way to find what's going on if there's a segfault.

# We may want to name it after when kaithem booted, and reduce to 10KB, or make it configurable.
# Or, we may want to read old debug log info at boot, and save it, so we have a chance to look through
# and diagnose really odd errors.

# We also print everything not printed in the root here
if os.path.exists("/dev/shm"):
    shmhandler = LoggingHandler(
        "",
        fn="kaithemlog",
        folder=f"/dev/shm/kaithemdbglog_{getpass.getuser()}/",
        level=0,
        entries_per_file=5000,
        bufferlen=0,
        keep=10**6,
        compress="none",
        doprint=False,
    )
    shmhandler.isShmHandler = True
    logging.getLogger().addHandler(shmhandler)
