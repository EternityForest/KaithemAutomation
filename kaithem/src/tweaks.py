# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later

import faulthandler

# fix https://github.com/python/cpython/issues/91216
# TODO this is a yucky hack
import importlib.metadata
import mimetypes
import os
import sys
import threading

import structlog
import yaml
from scullery import messagebus

faulthandler.enable()

mimetypes.add_type("text/html", ".html", strict=False)
mimetypes.add_type("text/html", ".vue", strict=False)
# ??????????
mimetypes.add_type("application/javascript", ".js", strict=True)


# Fix any bad environment that doesn't have this set which might break the display list feature
if not os.environ.get("DISPLAY"):
    os.environ["DISPLAY"] = ":0"


def str_presenter(dumper, data):
    """configures yaml for dumping multiline strings
    Ref: https://stackoverflow.com/questions/8640959/how-can-i-control-what-scalar-form-pyyaml-uses-for-my-data"""
    if data.count("\n") > 0:  # check for multiline string
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, str_presenter)
yaml.representer.SafeRepresenter.add_representer(
    str, str_presenter
)  # to use with safe_dum

if not os.environ.get("VIRTUAL_ENV"):
    if "pipx" in sys.executable:
        os.environ["VIRTUAL_ENV"] = os.path.dirname(
            os.path.dirname(sys.executable)
        )
    else:
        messagebus.post_message(
            "/system/notifications/warnings",
            "No virtual environment detected.  This may cause issues.",
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


def _get_non_stdlib_frame_info():
    """
    Walk the call stack and return (module, function) of the first
    non-stdlib frame that created the current thread. Returns
    (None, None) if only stdlib frames found.
    """
    import inspect

    stdlib_prefixes = (
        "asyncio/",
        "asyncio\\",
        "<frozen",
        "threading.py",
    )

    for frame_info in inspect.stack():
        frame_file = frame_info.filename
        # Skip stdlib
        if any(prefix in frame_file for prefix in stdlib_prefixes):
            continue
        if "/lib/python" in frame_file or "\\lib\\python" in frame_file:
            continue

        module = frame_info.frame.f_globals.get("__name__", "unknown")
        if module.endswith(".tweaks"):
            continue
        func = frame_info.function
        return (module, func)

    return (None, None)


def _rename_asyncio_thread(thread):
    """
    If thread has a generic asyncio name like 'asyncio_11', rename it
    to reflect the module and function that created it.
    """
    if thread.name and (
        thread.name.startswith("asyncio_") or thread.name.startswith("Thread-")
    ):
        module, func = _get_non_stdlib_frame_info()
        if module and func:
            thread.name = f"async_from: {module}.{func}"


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

        # Rename generic asyncio threads to reflect their origin
        _rename_asyncio_thread(self)
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
