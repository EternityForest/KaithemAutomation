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
import uvloop
import yaml
from scullery import messagebus

# TODO: deprecated install function
try:
    uvloop.install()
except Exception:
    print("Failed to install uvloop")

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
