# SPDX-License-Identifier: GPL-3.0-or-later

# This is for the ability to move directories.
# State is for modules ad persistance files
# cfg is any user configurable things
# Log is the log files

# []Put these in approprite places when running on linux
import getpass
import os
import pwd
import shutil
import socket

from .config import config

# Normally we run from one folder. If it's been installed, we change the paths a bit.
dn = os.path.dirname(os.path.realpath(__file__))

srcdir = dn

# Todo? Why this line here?
vardir = os.path.normpath(os.path.join(dn, ".."))
# Set in config now, not a real config entry

if "site_data_dir" in config:
    vardir = os.path.join(vardir, os.path.expanduser(config["site_data_dir"]))
else:
    vardir = "/dev/shm/kaithem-default-temp-vardir"
    os.makedirs(vardir, exist_ok=True)

datadir = os.path.normpath(os.path.join(dn, "../data"))
logdir = os.path.join(
    vardir, "logs", socket.gethostname() + "-" + getpass.getuser()
)

usersdir = os.path.join(vardir, "users")


mixerdir = os.path.join(vardir, "system.mixer")


moduledir = os.path.join(vardir, "modules")
htmldir = os.path.join(dn, "html")

# Mostly to not break unit tests
if "ssl_dir" not in config:
    config["ssl_dir"] = "ssl"

ssldir = os.path.expanduser(config["ssl_dir"])
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
