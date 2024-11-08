# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import faulthandler

# fix https://github.com/python/cpython/issues/91216
# TODO this is a yucky hack
import importlib.metadata
import logging
import mimetypes
import os
import re
import sys
import threading

import structlog
import uvloop

uvloop.install()

mimetypes.add_type("text/html", ".vue", strict=False)
# ??????????
mimetypes.add_type("application/javascript", ".js", strict=True)


if not os.environ.get("VIRTUAL_ENV"):
    if "pipx" in sys.executable:
        os.environ["VIRTUAL_ENV"] = os.path.dirname(
            os.path.dirname(sys.executable)
        )

try:
    import typeguard  # noqa
except Exception:
    v = importlib.metadata.version

    def version(p):
        x = v(p)
        if not x:
            raise importlib.metadata.PackageNotFoundError()
        return p

    importlib.metadata.version = version


def test_access(i):
    try:
        os.listdir(i)
        return True
    except Exception:
        return False


original_path = sys.path
# Snapcraft is putting in nonsense path entries
sys.path = [i for i in sys.path if test_access(i)]


# Whatever it used to be was way too high and causingh seg faults if you mess up
sys.setrecursionlimit(256)


faulthandler.enable()


threadlogger = structlog.get_logger(__name__)


class rtMidiFixer:
    def __init__(self, obj):
        self.__obj = obj

    def __getattr__(self, attr):
        if hasattr(self.__obj, attr):
            return getattr(self.__obj, attr)
        # Convert from camel to snake API
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", attr).lower()
        return getattr(self.__obj, name)

    def delete(self):
        # Let GC do this
        pass

    def __del__(self):
        try:
            self.__obj.delete()
        except AttributeError:
            self.__obj.close_port()
        self.__obj = None


try:
    import rtmidi

    if hasattr(rtmidi, "MidiIn"):

        def mget(*a, **k):
            m = rtmidi.MidiIn(*a, **k)
            return rtMidiFixer(m)

        rtmidi.RtMidiIn = mget

    if hasattr(rtmidi, "MidiOut"):

        def moget(*a, **k):
            m = rtmidi.MidiOut(*a, **k)
            return rtMidiFixer(m)

        rtmidi.RtMidiOut = moget
except Exception:
    logging.exception("RtMidi compatibility error")


def installThreadLogging():
    """
    Workaround for sys.excepthook thread bug
    From
    http://spyced.blogspot.com/2007/06/workaround-for-sysexcepthook-bug.html
    (https://sourceforge.net/tracker/?func=detail&atid=105470&aid=1230540&group_id=5470).
    Call once from __main__ before creating any threads.
    If using psyco, call psyco.cannotcompile(threading.Thread.run)
    since this replaces a new-style class method.

    Modified by kaithem project to do something slightly different. Credit to Ian Beaver.
    What our version does is posts to the message bus when a thread starts, stops, or has an exception.
    """
    init_old = threading.Thread.__init__

    def init(self, *args, **kwargs):
        # This does not need to block shutdown.
        if kwargs.get("name", "").startswith("zeroconf-ServiceBrowser"):
            kwargs["daemon"] = True

        init_old(self, *args, **kwargs)
        run_old = self.run

        def run_with_except_hook(*args, **kw):
            if self.name.startswith("nostartstoplog.") or self.name.startswith(
                "Thread-"
            ):
                try:
                    run_old(*args, **kw)
                except Exception as e:
                    threadlogger.exception(
                        "Thread stopping due to exception: "
                        + self.name
                        + " with ID: "
                        + str(threading.current_thread().ident)
                    )
                    raise e
            else:
                try:
                    threadlogger.debug(
                        "Thread starting: "
                        + self.name
                        + " with ID: "
                        + str(threading.current_thread().ident)
                        + " Daemon: "
                        + str(self.daemon)
                    )

                    run_old(*args, **kw)
                    threadlogger.debug(
                        "Thread stopping: "
                        + self.name
                        + " with ID: "
                        + str(threading.current_thread().ident)
                    )

                except Exception as e:
                    threadlogger.exception(
                        "Thread stopping due to exception: "
                        + self.name
                        + " with ID: "
                        + str(threading.current_thread().ident)
                    )
                    from . import messagebus

                    messagebus.post_message(
                        "/system/notifications/errors",
                        "Thread: "
                        + self.name
                        + " with ID: "
                        + str(threading.current_thread().ident)
                        + " stopped due to exception ",
                    )
                    raise e

        # Rename thread so debugging works
        try:
            if self._target:
                run_with_except_hook.__name__ = self._target.__name__
                run_with_except_hook.__module__ = self._target.__module__
        except Exception:
            try:
                run_with_except_hook.__name__ = "run"
            except Exception:
                pass
        self.run = run_with_except_hook

    threading.Thread.__init__ = init


installThreadLogging()
