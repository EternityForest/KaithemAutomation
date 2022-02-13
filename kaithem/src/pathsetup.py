# Copyright Daniel Dunn 2019
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.


# This file deals with configuring the way python's import mechanism works.

import sys
import os
import logging
logger = logging.getLogger("system")


def setupCython():
    # TODO do we want unique instance ids so two apps can be on one user?
    # Does that ever happen? Do they even need separate dirs?
    from src import config, util

    if config.config['run-as-user'] == 'root':
        d = "/dev/shm/kaithem_pyx_"+util.getUser()
    else:
        d = "/dev/shm/kaithem_pyx_"+config.config['run-as-user']
    # Set up pyximport in the proper kaithem-y way
    try:
        import os
        if os.path.exists("/dev/shm"):
            if not os.path.exists(d):
                os.mkdir(d)

        import pyximport
        pyximport.install(build_dir=d if os.path.isdir(d) else None,language_level=3)
    except:
        logger.exception(
            "Could not set up pyximport. Ensure that Cython is installed if you want to use .pyx files")


def setupPath(linuxpackage, force_local=False):
    global startupPluginsPath
    # There are some libraries that are actually different for 3 and 2, so we use the appropriate one
    # By changing the pathe to include the proper ones.

    # Also, when we install on linux, everything gets moved around, so we change the paths accordingly.

    x = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # This is ow we detect if we are running in "unzip+run mode" or installed on linux.
    # If we are installed, then src is found in /usr/lib/kaithem

    if x.startswith('/usr/bin') and not force_local:
        x = "/usr/lib/kaithem"
        sys.path = [x] + sys.path
    else:
        logger.info("Running in unzip-and-run mode")

    x = os.path.join(x, 'src')

    # Avoid having to rename six.py by treating it's folder as a special case.
    sys.path = [os.path.join(x, 'thirdparty', 'six')] + sys.path

    sys.path = [os.path.join(x, 'plugins', 'ondemand')] + sys.path
    sys.path = [os.path.join(x, 'plugins', 'startup')] + sys.path

    startupPluginsPath = os.path.join(x, 'plugins', 'startup')
    sys.path = sys.path + [os.path.join(x, 'plugins', 'lowpriority')]

    # There is actually a very good reason to change the import path here.
    # It means we can refer to an installed copy of a library by the same name
    # We use for the copy we include. Normally we use our version.
    # If not, it will fall back to theirs.
    sys.path = [os.path.join(x, 'thirdparty')] + sys.path

    # Low priority modules will default to using the version installed on the user's computer.
    sys.path = sys.path + [os.path.join(x, 'thirdparty', "lowpriority")]
