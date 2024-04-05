# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

from typing import List
from urllib.request import urlopen
import reprlib
from urllib.parse import unquote as unurl
from urllib.parse import quote

"This file ideally should only depend on sdtilb stuff and import the rest as needed. We don't want this to drag in threads and everything"
import os
import threading
import copy
import sys
import shutil
import difflib
import time
import json
import traceback
import stat
import subprocess
import copy
import collections
import types
import weakref
import logging
import struct
import hashlib
import getpass
import yaml
from typing import Iterable
import zeroconf

zeroconf = zeroconf.Zeroconf()

logger = logging.getLogger("system")

min_time = 0


savelock = threading.RLock()

# Normally we run from one folder. If it's been installed, we change the paths a bit.
dn = os.path.dirname(os.path.realpath(__file__))
if "/usr/lib" in dn:
    datadir = "/usr/share/kaithem"
else:
    datadir = os.path.join(dn, "../data")

eff_wordlist = [s.split()[1] for s in open(os.path.join(datadir, "words_eff.txt"))]
mnemonic_wordlist = [
    s.strip() for s in open(os.path.join(datadir, "words_mnemonic.txt"))
]


def memorableHash(x, num=3, separator=""):
    "Use the diceware list to encode a hash. Not meant to be secure."
    o = ""

    if isinstance(x, str):
        x = x.encode("utf8")
    for i in range(num):
        while 1:
            x = hashlib.sha256(x).digest()
            n = struct.unpack("<Q", x[:8])[0] % len(eff_wordlist)
            e = eff_wordlist[n]
            # Don't have a word that starts with the letter the last one ends with
            # So it's easier to read
            if o:
                if e[0] == o[-1]:
                    continue
                o += separator + e
            else:
                o = e
            break
    return o


def blakeMemorable(x, num=3, separator=""):
    "Use the diceware list to encode a hash. This IS meant to be secure"
    o = ""

    if isinstance(x, str):
        x = x.encode("utf8")

    x = hashlib.blake2b(x).digest()

    for i in range(num):
        # 4096 is an even divisor of 2**16
        n = struct.unpack("<H", x[:2])[0] % 4096
        o += eff_wordlist[n] + separator
        x = x[2:]
    return o[: -len(separator)] if separator else o


def universal_weakref(f, cb=None):
    if isinstance(f, types.MethodType):
        return weakref.WeakMethod(f, cb)
    else:
        return weakref.ref(f, cb)


def chmod_private_try(p, execute=True):
    try:
        if execute:
            os.chmod(
                p,
                stat.S_IRUSR
                | stat.S_IWUSR
                | stat.S_IXUSR
                | stat.S_IRGRP
                | stat.S_IWGRP
                | stat.S_IXGRP,
            )
        else:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)
    except Exception as e:
        raise e


def open_private_text_write(p):
    try:
        x = os.open("/path/to/file", os.O_RDWR | os.O_CREAT, 0o0600)
        return os.fdopen(x, "w")
    except Exception:
        try:
            os.close(x)
        except Exception:
            pass
        return open(p, "w")


def url(u: str, safe: str | Iterable[str] = ""):
    safe = "".join(safe)
    return quote(u, safe)


def SaveAllState():
    # fix circular import by putting it here
    from . import messagebus, pylogginghandler

    with savelock:
        try:
            x = False
            messagebus.post_message("/system/save", None, synchronous=True)
            pylogginghandler.syslogger.flush()
            return x
        except Exception as e:
            messagebus.post_message(
                "/system/notifications/errors",
                "Failed to save state:" + traceback.format_exc(8),
            )


# http://stackoverflow.com/questions/3812849/how-to-check-whether-a-directory-is-a-sub-directory-of-another-directory
# It looks like a lot of people might have contributed to this little bit of code.


def in_directory(file, directory):
    # make both absolute
    directory = os.path.join(os.path.realpath(directory), "")
    file = os.path.realpath(file)

    # return true, if the common prefix of both is equal to directory
    # e.g. /a/b/c/d.rst and directory is /a/b, the common prefix is /a/b
    return os.path.commonprefix([file, directory]) == directory


# What is the point of this? I don't know and there's probably an issue here.


def fakeUnixRename(src, dst):
    shutil.move(src, dst)


def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)


def ensure_dir2(f):
    if not os.path.exists(f):
        os.makedirs(f)


def readfile(f):
    with open(f) as fh:
        r = fh.read()
    return r


# Get the names of all subdirectories in a folder but not full paths


def get_immediate_subdirectories(folder):
    return [
        name for name in os.listdir(folder) if os.path.isdir(os.path.join(folder, name))
    ]


# Get a list of all filenames but not the full paths


def get_files(folder):
    return [
        name
        for name in os.listdir(folder)
        if not os.path.isdir(os.path.join(folder, name))
    ]


def search_paths(fn: str, paths: List[str]) -> str | None:
    for i in paths:
        if os.path.exists(os.path.join(i, fn)):
            return os.path.join(i, fn)


def getHighestNumberedTimeDirectory(where, n=0):
    """Given a directory containing entirely folders named after floating point values get the name of the highest. ignore files.
    and also ignoring non-timestapt float looking named directories

    n is normally 0, but setting it to 1 gets the second highest time dir, etc.
    """
    asnumbers = {}
    global min_time

    for i in get_immediate_subdirectories(where):
        try:
            asnumbers[float(i)] = i
        except ValueError:
            pass
    min_time = max(sorted(asnumbers.keys(), reverse=True)[0], min_time)
    return asnumbers[sorted(asnumbers.keys(), reverse=True)[n]]


def deleteAllButHighestNumberedNDirectories(where, N):
    """In a directory full of folders named after time values, we delete all but the highest N directores ignoring files
    and also ignoring non-timestapt float looking named directories
    """
    asnumbers = {}
    for i in get_immediate_subdirectories(where):
        try:
            asnumbers[float(i)] = i
        except ValueError:
            pass

    for i in sorted(asnumbers.keys())[0:-N]:
        shutil.rmtree(os.path.join(where, asnumbers[i]))


def deleteOldStuffAndEmptyDirectories(where, age):
    torm = []

    for b, d, f in os.walk(where, topdown=False):
        for i in f:
            if os.stat(f).st_mtime < time.time() - age:
                torm.append(os.path.join(b, i))

    for i in torm:
        os.remove(i)

    for b, d, f in os.walk(where, topdown=False):
        for i in d:
            if not os.listdir(i):
                torm.append(os.path.join(b, i))

    for i in torm:
        os.remove(i)


def disallowSpecialChars(s, allow=""):
    for i in r"""~!@#$%^&*()_+`-=[]\{}|;':"',./<>?""":
        if i in s:
            raise ValueError("String contains " + i)
    for i in "\n\r\t":
        if i in s:
            raise ValueError("String contains tab, newline, or return")


class LowPassFiter(object):
    "Speed should be 0 to 1 and express by what percentage to approach the new value per sample"

    def __init__(self, speed, startval=0):
        self.value = startval
        self.speed = speed

    def sample(self, x):
        self.value = (self.value * (1 - self.speed)) + ((x) * self.speed)


# Credit to Jay of stack overflow for this function


def which(program):
    "Check if a program is installed like you would do with UNIX's which command."

    # Because in windows, the actual executable name has .exe while the command name does not.
    if sys.platform == "win32" and not program.endswith(".exe"):
        program += ".exe"

    # Find out if path represents a file that the current user can execute.
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    # If the input was a direct path to an executable, return it
    if fpath:
        if is_exe(program):
            return program

    # Else search the path for the file.
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    # If we got this far in execution, we assume the file is not there and return None
    return None


def restart():
    cherrypy.engine.restart()


def exit():
    cherrypy.engine.exit()


def updateIP():
    global MyExternalIPAdress
    # Yes, This really is the only way i know of to get your public IP.
    try:
        if config["get-public-ip"]:
            u = urlopen("http://ipecho.net/plain", timeout=60)
        MyExternalIPAdress = u.read()

        if sys.version_info > (3, 0):
            MyExternalIPAdress = MyExternalIPAdress.decode("utf8")
    except:
        MyExternalIPAdress = "unknown"
    finally:
        try:
            u.close()
        except Exception:
            pass
    return MyExternalIPAdress


last = time.time()


lastNTP = 0
oldNTPOffset = 30 * 365 * 24 * 60 * 60
hasInternet = False


def timeaccuracy():
    from . import messagebus

    global lastNTP, oldNTPOffset
    try:
        if (time.time() - lastNTP) > 600:
            lastNTP = time.time()
            c = ntplib.NTPClient()
            response = c.request("ntp.pool.org", version=3)
            oldNTPOffset = (
                response.offset + response.root_delay + response.root_dispersion
            )
            if not hasInternet:
                messagebus.post_message("/system/internet", True)
            hasInternet = True
            return oldNTPOffset
        else:
            return oldNTPOffset + (time.time() - lastNTP) / 10000.0
    except:
        if hasInternet:
            messagebus.post_message("/system/internet", False)
        hasInternet = False
        return oldNTPOffset + (time.time() - lastNTP) / 10000.0


def diff(a, b):
    x = a.split("\n")
    x2 = []
    for i in x:
        x2.append(i)
    y = b.split("\n")
    y2 = []
    for i in y:
        y2.append(i)
    return "".join(difflib.unified_diff(x2, y2))


# This returns either the current time, or a value that is higher than any
# timestamp in the latest server save
def time_or_increment():
    if time.time() > min_time:
        return time.time()
    else:
        return int(min_time) + 1.234567


def roundto(n, s):
    if not s:
        return n
    if (n % s) > (s / 2):
        return n + (s - (n % s))
    else:
        return n - n % s


def split_escape(s, separator, escape=None, preserve_escapes=False):
    current_token = ""
    tokens = []
    literal = False

    for i in s:
        if literal:
            current_token += i
            literal = False
        elif i == separator:
            tokens += [current_token]
            current_token = ""

        elif i == escape:
            literal = True
            if preserve_escapes:
                current_token += i
        else:
            current_token += i

    if current_token:
        return tokens + [current_token]
    else:
        return tokens


def unescape(s, escape="\\"):
    s2 = ""
    literal = False
    for i in s:
        if literal:
            s2 += i
            literal = False
        elif i == escape:
            literal = True
        else:
            s2 += i
    return s2


def resourcename_escape(s):
    return s.replace("\\", "\\\\").replace("/", "\\/")


def module_onelevelup(s):
    return "/".join(
        [
            i.replace("\\", "\\\\").replace("/", "\\/")
            for i in split_escape(s, "/", "\\")[:-1]
        ]
    )


numberlock = threading.Lock()
current_number = -1


def unique_number():
    global current_number
    with numberlock:
        current_number += 1
        x = current_number
    return x


def is_private_ip(ip):
    if "." in ip:
        ip = [int(i) for i in ip.split(".")]

        if ip[0] == 10 or ip[0] == 127:
            return True

        elif ip[0] == [172]:
            if ip[1] >= 16 and ip[1] <= 31:
                return True

        elif ip[0] == 192 and ip[1] == 168:
            return True

        return False

    if ip == "::1":
        return True

    elif ip.startswith(("fc", "fd", "fe80")):
        return True

    return False


srepr = reprlib.Repr()

srepr.maxdict = 25
srepr.maxlist = 15
srepr.maxset = 10
srepr.maxlong = 24
srepr.maxstring = 240
srepr.maxother = 240


def saferepr(obj):
    try:
        return srepr.repr(obj)
    except Exception as e:
        return e + " in repr() call"


currentUser = None


def getUser():
    global currentUser
    return currentUser or getpass.getuser()


# Partly based on code by Tamás of stack overflow.


def drop_perms(user, group=None):
    global currentUser
    if os.name == "nt":
        return

    if os.getuid() != 0:
        # No perms to drop!!
        return

    if user.strip() == "root":
        # Don't mess with stuff uneccesarily,
        # Changing to the exact same user can cause problems
        return

    logger.info("Changing user and group to: " + str(user) + " " + str(group))

    import grp
    import pwd

    # Thanks to Gareth A. Lloyd of Stack Exchange!
    groups = [g.gr_gid for g in grp.getgrall() if user in g.gr_mem]
    gid = pwd.getpwnam(user).pw_gid
    groups.append(grp.getgrgid(gid).gr_gid)

    if group == "__default__":
        group = user

    running_uid = pwd.getpwnam(user).pw_uid
    running_gid = grp.getgrnam(group).gr_gid
    os.setgroups(groups)
    os.setgid(running_gid)
    os.setuid(running_uid)
    currentUser = user


def lrucache(n=10):
    class LruCache:
        def __init__(self, f):
            self.f = f
            self.n = n
            self.cache = collections.OrderedDict()

        def invalidate_cache(self, *args, **kwargs):
            if (not args) and not kwargs:
                self.cache = collections.OrderedDict()
            else:
                self.cache.pop(self.fargs(args, kwargs))

        def fargs(self, a, kw):
            "Serialize kwargs as (k,v) pairs so we can use the args as a key"
            # This has the issue of undefined ordering. But a few duplicate
            # cache entries won't be too much of a performance hit I don't think
            k = []
            for i in kw.items():
                k.append(i)
            return (a, tuple(k))

        def __call__(self, *args, **kwargs):
            x = self.fargs(args, kwargs)
            if x in self.cache:
                self.cache[x] = self.cache.pop(x)
            else:
                self.cache[x] = self.f(*args, **kwargs)
                if len(self.cache) > self.n:
                    self.cache.popitem(last=False)
            return self.cache[x]

    return LruCache


def display_yaml(d):
    d = copy.deepcopy(d)
    _yaml_esc(d)
    return yaml.dump(d)


def _yaml_esc(s, depth=0, r=""):
    if depth > 20:
        raise RuntimeError()
    if isinstance(s, (str, float, int)):
        return
    if isinstance(s, list):
        x = range(len(s))
    else:
        x = s
    for i in x:
        if isinstance(s[i], str):
            s[i] = s[i].replace("\t", "\\t").replace("\r", r)
        else:
            _yaml_esc(s[i])
