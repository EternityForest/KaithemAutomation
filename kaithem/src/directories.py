# Copyright Daniel Dunn 2013, 2015
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

# This is for the ability to move directories.
# State is for modules ad persistance files
# cfg is any user configurable things
# Log is the log files

# []Put these in approprite places when running on linux
import os
import pwd
import getpass
import shutil
import ssl
from .config import config
from os import environ

import socket

# Normally we run from one folder. If it's been installed, we change the paths a bit.
dn = os.path.dirname(os.path.realpath(__file__))

srcdir = dn


def getRootAndroidDir():
    from jnius import autoclass, cast
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Environment = autoclass('android.os.Environment')
    context = cast('android.content.Context', PythonActivity.mActivity)

    user_services_dir = context.getExternalFilesDir(
        Environment.getDataDirectory().getAbsolutePath()
    ).getAbsolutePath()

    return os.path.join(user_services_dir, "var")


if 'ANDROID_ARGUMENT' in environ:
    vardir = getRootAndroidDir()
    datadir = os.path.normpath(os.path.join(dn, '../data'))
    logdir = os.path.join(
        vardir, 'logs', socket.gethostname() + "-" + getpass.getuser())
else:

    vardir = os.path.normpath(os.path.join(dn, '..'))
    vardir = os.path.join(vardir, os.path.expanduser(config['site-data-dir']))

    # These non writable paths indicate we should do stuff differently because we are installed with setuptools
    # most likely
    if vardir.startswith('/usr') or vardir.startswith('/nix'):
        vardir = os.path.expanduser("~/kaithem")



    datadir = os.path.normpath(os.path.join(dn, '../data'))
    logdir = os.path.join(
        vardir, 'logs', socket.gethostname() + "-" + getpass.getuser())


moduledatadir = os.path.join(vardir, 'moduledata')

usersdir = os.path.join(vardir, 'users')


mixerdir = os.path.join(vardir, 'system.mixer')


moduledir = os.path.join(vardir, 'modules')
htmldir = os.path.join(dn, 'html')

ssldir = os.path.expanduser(config['ssl-dir'])
if not ssldir.startswith("/"):
    ssldir = os.path.join(vardir, ssldir)
else:
    ssldir = os.path.join(ssldir)


def recreate():
    global dn, vardir, usersdir, logdir, regdir, moduledir, datadir, htmldir, ssldir
    dn = os.path.dirname(os.path.realpath(__file__))

    if 'ANDROID_ARGUMENT' in environ:
        vardir = getRootAndroidDir()
    else:
        vd = os.path.normpath(os.path.join(dn, '..'))
        vardir = os.path.join(vd, os.path.expanduser(config['site-data-dir']))

    usersdir = os.path.join(vardir, 'users')
    logdir = os.path.join(
        vardir, 'logs', socket.gethostname() + "-" + getpass.getuser())
    moduledir = os.path.join(vardir, 'modules')
    datadir = os.path.normpath(os.path.join(dn, '../data'))
    htmldir = os.path.join(dn, 'html')

    

    ssldir = os.path.expanduser(config['ssl-dir'])
    if not ssldir.startswith("/"):
        ssldir = os.path.join(vardir, ssldir)
    else:
        ssldir = os.path.join(ssldir)


def chownIf(f, usr):
    if not pwd.getpwuid(os.stat(f).st_uid).pw_name == usr:
        shutil.chown(f, usr, usr)


def rchown(d, usr):
    chownIf(d, usr)
    for root, dirs, files in os.walk():
        chownIf(root, usr)
        for file in files:
            chownIf(os.path.join(root, file), usr)
