# SPDX-FileCopyrightText: Copyright 2019 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


# This file deals with configuring the way python's import mechanism works.

import sys
import os
import logging

logger = logging.getLogger("system")


def setupPath(linuxpackage=None, force_local=False):
    global startupPluginsPath
    # There are some libraries that are actually different for 3 and 2, so we use the appropriate one
    # By changing the pathe to include the proper ones.

    # Also, when we install on linux, everything gets moved around, so we change the paths accordingly.

    x = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # This is ow we detect if we are running in "unzip+run mode" or installed on linux.
    # If we are installed, then src is found in /usr/lib/kaithem

    if x.startswith("/usr/bin") and not force_local:
        x = "/usr/lib/kaithem"
        sys.path = [x] + sys.path
    else:
        logger.info("Running in unzip-and-run mode")

    whatHasTheSrcFolder = x
    x = os.path.join(x, "src")

    sys.path = [os.path.join(x, "plugins", "ondemand")] + sys.path
    sys.path = [os.path.join(x, "plugins", "startup")] + sys.path

    startupPluginsPath = os.path.join(x, "plugins", "startup")
    sys.path = sys.path + [os.path.join(x, "plugins", "lowpriority")]

    # With snaps, lets not use this style of including the packages.
    # Perhaps we'll totally leave it behind later!
    if not os.path.normpath(__file__).startswith("/snap"):
        sys.path = [os.path.join(x, "thirdparty")] + sys.path

        # Low priority modules will default to using the version installed on the user's computer.
        sys.path = sys.path + [os.path.join(x, "thirdparty", "lowpriority")]

    else:
        # Still a few old things we need in Thirdparty
        sys.path = sys.path + [os.path.join(x, "thirdparty")]

        # Low priority modules will default to using the version installed on the user's computer.
        sys.path = sys.path + [os.path.join(x, "thirdparty", "lowpriority")]

    # Consider using importlib.util.module_for_loader() to handle
    # most of these details for you.

    def load_module(self, fullname):
        for i in sys.modules:
            if fullname.endswith(i):
                return sys.modules[i]


setupPath(linuxpackage=os.path.abspath(__file__).startswith("/usr/bin"))
