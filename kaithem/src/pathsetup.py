# SPDX-FileCopyrightText: Copyright 2019 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


# This file deals with configuring the way python's import mechanism works.

import os
import sys

import structlog

logger = structlog.get_logger(__name__)

setup = False


def setupPath(linuxpackage=None, force_local=False):
    global setup
    if setup:
        return
    setup = True

    global startupPluginsPath
    # There are some libraries that are actually different for 3 and 2, so we use the appropriate one
    # By changing the pathe to include the proper ones.

    # Also, when we install on linux, everything gets moved around, so we change the paths accordingly.

    x = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # This is ow we detect if we are running in "unzip+run mode" or installed on linux.
    # If we are installed, then src is found in /usr/lib/kaithem

    x = os.path.join(x, "src")

    startupPluginsPath = os.path.join(x, "plugins")

    # With snaps, lets not use this style of including the packages.
    # Perhaps we'll totally leave it behind later!
    if not os.path.normpath(__file__).startswith("/snap"):
        sys.path = [os.path.join(x, "thirdparty")] + sys.path

    else:
        # Still a few old things we need in Thirdparty
        sys.path = sys.path + [os.path.join(x, "thirdparty")]
    # Truly an awefullehaccken
    # Break out of venv to get to gstreamer

    # Consider using importlib.util.module_for_loader() to handle
    # most of these details for you.

    def load_module(self, fullname):
        for i in sys.modules:
            if fullname.endswith(i):
                return sys.modules[i]

    # Truly an awefullehaccken
    # Break out of venv to get to gstreamer
    # It's just that one package.  Literally everything else
    # Is perfectly fine. GStreamer doesn't do pip so we do this.

    try:
        if os.environ.get("VIRTUAL_ENV"):
            en = os.environ["VIRTUAL_ENV"]
            p = os.path.join(
                en,
                "lib",
                "python" + ".".join(sys.version.split(".")[:2]),
                "site-packages",
                "gi",
            )
            s = "/usr/lib/python3/dist-packages/gi"

            if os.path.exists(s) and (not os.path.exists(p)):
                os.symlink(s, p)
    except Exception:
        logger.exception("Failed to do the gstreamer hack")


setupPath()
