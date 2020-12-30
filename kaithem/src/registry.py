# Copyright Daniel Dunn 2015
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
from . import util, directories, messagebus, config
import os
import time
import json
import copy
import hashlib
import threading
import copy
import traceback
import shutil
import yaml
import validictory
import sqlite3
import sys
import logging
import getpass
from .util import url, unurl

log = logging.getLogger("system.registry")


if os.path.exists("/dev/shm"):
    # Detect if we are going to change to a different user
    selectedUser = config.config['run-as-user'] if util.getUser(
    ) == 'root' else util.getUser()
    uniqueInstanceId = ",".join(
        sys.argv) + os.path.normpath(__file__)+selectedUser
    uniqueInstanceId = hashlib.sha1(
        uniqueInstanceId.encode("utf8")).hexdigest()[:24]
    enable_sqlite_backup = True
    recoveryDbPath = os.path.join(
        "/dev/shm/kaithem_"+selectedUser, uniqueInstanceId, "registrybackup")

    util.ensure_dir(recoveryDbPath)
    recoveryDb = sqlite3.connect(recoveryDbPath)
    util.chmod_private_try(recoveryDbPath)

    # Chown to the user we are actually going to be running as
    if util.getUser() == 'root':
        shutil.chown(os.path.join("/dev/shm/kaithem_"+selectedUser,
                                  uniqueInstanceId, "registrybackup"), selectedUser)
        shutil.chown(os.path.join("/dev/shm/kaithem_" +
                                  selectedUser, uniqueInstanceId), selectedUser)
        shutil.chown(os.path.join(
            "/dev/shm/kaithem_"+selectedUser), selectedUser)

    util.chmod_private_try(recoveryDbPath)
    recoveryDb.row_factory = sqlite3.Row
    # If flag is 1, that means the resource has been deleted. All this is, is key value storage of
    # Unsaved changes to the modules. When you save, you clear everything before deleting the __complete__
    # Marker.

    # When we load kaithem, we can check if this database has newer data than anything in the modules and resources.
    # Time is of course used to detect that. We use the system time. We just have to trust that the system
    # Time won't go significantly backwards. Combined with the fact manual editing is probably not happening on
    # RTCless systems, none of this persists after reboots, and we normally delete these records when saving for real,
    # There is very little change that old data ever overwrites newer data.
    with recoveryDb:
        recoveryDb.execute(
            "CREATE TABLE IF NOT EXISTS change (key TEXT, value TEXT, flag INTEGER, time INTEGER)")
    recoveryDb.commit()
    recoveryDb.close()
else:
    enable_sqlite_backup = False


def purgeSqliteBackup():
    if enable_sqlite_backup:
        try:
            recoveryDb = sqlite3.connect(recoveryDbPath)
            with recoveryDb:
                recoveryDb.execute("delete from change")
            recoveryDb.commit()
            recoveryDb.close()
        except:
            logging.exception("err deleting old recovery records")


def createRecoveryEntry(key, value, flag):
    valuej = json.dumps(value)
    if enable_sqlite_backup:
        if not os.path.exists(recoveryDbPath):
            util.ensure_dir(recoveryDbPath)
        recoveryDb = sqlite3.connect(recoveryDbPath)
        with recoveryDb:
            recoveryDb.execute("delete from change where key=?", (key,))
            recoveryDb.execute("insert into change values (?,?,?,?)", (
                key, valuej, flag, int(time.time()*1000000)
            ))
        recoveryDb.commit()
        recoveryDb.close()


# Global cache for system registry
cache = {}


class PersistanceArea():

    # A special dict that works mostly like a normal one, except for it raises
    # an error if someone puts something non serializable in.

    class PersistanceDict(dict):
        def __init__(self, *args):
            self.md5 = ''
            self.schemas = {}
            dict.__init__(self, *args)

        # True if nothing changed since last marked clean. Used to decide to save or not.
        def isClean(self):
            if self.md5 == hashlib.md5(json.dumps(copy.deepcopy(self)).encode('utf8')).digest():
                return True
            else:
                return False

        # We could use a flag, but using the hash doesn't have possible thread issues.
        def markClean(self):
            self.md5 = hashlib.md5(json.dumps(
                copy.deepcopy(self)).encode('utf8')).digest()

        def __getitem__(self, key):
            val = dict.__getitem__(self, key)
            return val

        # Custom setitem because we want to ensure nobody puts non serializable things in
        # Even though we might use YAML at some point it stil makes sense to limit things to JSON
        # for simplicity
        def __setitem__(self, key, val):
            try:
                json.dumps({key: val})
            except:
                raise RuntimeError(
                    "Invalid dict insert %s:%s has a non serializable value or key" % (key, val))
            dict.__setitem__(self, key, val)

    def __init__(self, folder):
        try:
            # We want to loop over all the timestamp named directories till we find a valid one
            # We rename invalid ones to INCOMPLETE<name>
            # This is going to recheck data every time.
            f = None
            if os.path.isfile(os.path.join(folder, "data", "kaithem_dump_valid.txt")):
                f = "data"
            else:
                for i in(0, 15):
                    try:
                        f = util.getHighestNumberedTimeDirectory(folder)
                    except:
                        f = None
                        logging.exception("No registry data")
                        break

                    if os.path.isfile(os.path.join(folder, f, "kaithem_dump_valid.txt")):
                        break
                    else:
                        shutil.copytree(os.path.join(folder, f),
                                        os.path.join(folder, "INCOMPLETE"+f))
                        shutil.rmtree(os.path.join(folder, f))

            if not os.path.isfile(os.path.join(folder, "data", "kaithem_dump_valid.txt")):
                if os.path.isdir(os.path.join(folder, "data")):
                    # I guess assume it's already been backed up?
                    if not os.path.exists(os.path.join(folder, "INCOMPLETE"+f)):
                        shutil.copytree(os.path.join(folder, f),
                                        os.path.join(folder, "INCOMPLETE"+f))

            # Not that we are in a try block
            if not f:
                raise RuntimeError("No Folder Found")

            # Handle finding valid directory
            # Take all the json files and make PersistanceDicts, and mark them clean.
            self.files = {}
            for i in util.get_files(os.path.join(folder, f)):
                # YAML takes precedence
                if i.endswith('.json') and not os.path.exists(os.path.join(folder, f, i[:-5]+".yaml")):
                    with open(os.path.join(folder, f, i)) as x:
                        self.files[i[:-5]
                                   ] = self.PersistanceDict(json.load(x)['data'])
                        self.files[i[:-5]].markClean()
                if i.endswith('.yaml'):
                    with open(os.path.join(folder, f, i)) as x:
                        self.files[i[:-5]
                                   ] = self.PersistanceDict(yaml.load(x)['data'])
                        self.files[i[:-5]].markClean()

            if os.path.isfile(os.path.join(folder, "data", 'kaithem_dump_valid.txt')):
                completeFileTimestamp = os.stat(os.path.join(
                    folder, "data", 'kaithem_dump_valid.txt')).st_mtime
            else:
                completeFileTimestamp = 0
            global registry
            registry = self
            # If there are any unsaved registry changes, recover them now
            self.loadRecoveryDbInfo(completeFileTimestamp)

        except Exception as e:
            log.exception("Loading")
            self.files = {}
        self.folder = folder

    # Save persistane area to folder dump
    def save(self):
        error = 0
        save = 0
        # See if we need to save at all, save if we have at least one unclean file
        for i in self.files:
            if not self.files[i].isClean():
                save = 1
        if not save:
            return False

        try:
            t = str(util.time_or_increment())
            util.ensure_dir2(self.folder)

            if os.path.isdir(os.path.join(self.folder, "data")):
                # Copy everything except the completion marker
                shutil.copytree(os.path.join(self.folder, "data"), os.path.join(self.folder, t),
                                ignore=shutil.ignore_patterns("kaithem_dump_valid.txt"))

                with open(os.path.join(self.folder, t, 'kaithem_dump_valid.txt'), "w") as x:
                    util.chmod_private_try(os.path.join(
                        self.folder, t, 'kaithem_dump_valid.txt'), execute=False)
                    x.write("This file certifies this folder as valid")
            else:
                util.ensure_dir2(os.path.join(self.folder, "data"))

            if os.path.isdir(os.path.join(self.folder, "data", "kaithem_dump_valid.txt")):
                os.remove(os.path.join(self.folder, "data",
                                       "kaithem_dump_valid.txt"))
            # This segment relies on copy and deepcopy being atomic...
            # iterate over files and dump each to a json, set error flag if there are any errors
            for i in self.files.copy():
                try:
                    with open(os.path.join(self.folder, "data", url(i)+".yaml"), 'w') as x:
                        util.chmod_private_try(os.path.join(
                            self.folder, "data", url(i)+".yaml"), execute=False)
                        yaml.safe_dump(
                            {'data': dict(copy.deepcopy(self.files[i]))}, x)
                except Exception as e:
                    error = 1
                    try:
                        messagebus.postMessage(
                            "/system/notifications/errors", 'Registry save error:' + repr(e))
                    except:
                        pass

            for i in util.get_files(os.path.join(self.folder, "data")):
                try:
                    if (not unurl(i)[:-5] in self.files) and not i == "kaithem_dump_valid.txt":
                        print(unurl(i))
                        os.remove(os.path.join(self.folder, "data", i))
                except Exception as e:
                    error = 1
                    try:
                        messagebus.postMessage(
                            "/system/notifications/errors", 'Registry save error:' + repr(e))
                    except:
                        pass

        except Exception as e:
            log.exception("Failure dumping persistance dicts.")
            messagebus.postMessage(
                "/system/notifications/errors", 'Registry save error:' + repr(e))
        purgeSqliteBackup()
        if not error:
            with open(os.path.join(self.folder, "data", 'kaithem_dump_valid.txt'), "w") as x:
                util.chmod_private_try(os.path.join(
                    self.folder, "data", 'kaithem_dump_valid.txt'), execute=False)
                x.write("This file certifies this folder as valid")
        else:
            print("Failure dumping persistance dicts.")
        for i in self.files:
            self.files[i].markClean()

        util.deleteAllButHighestNumberedNDirectories(self.folder, 2)
        return True

    def loadRecoveryDbInfo(self, completeFileTimestamp=0):
        global is_clean
        with reglock:
            if enable_sqlite_backup:
                recoveryDb = sqlite3.connect(recoveryDbPath)
                with recoveryDb:
                    c = recoveryDb.cursor()
                    c.row_factory = sqlite3.Row
                    c.execute("select * from change")
                    for i in c:
                        is_clean = False
                        # Older than what we have now, ignore, the state was saved
                        # After this entry was created
                        if not i['time']/1000000 > completeFileTimestamp:
                            continue
                        if not i['flag']:
                            self.set(i['key'], json.loads(
                                i['value']), _noRecoveryRecord=True)
                        else:
                            delete(i['key'])
                recoveryDb.close()

    def open(self, f):
        if not f in self.files:
            self.files[f] = self.PersistanceDict()
        return self.files[f]

    def set(self, key, value, _noRecoveryRecord=False):
        global is_clean
        is_clean = False
        try:
            json.dumps({key: value})
        except:
            raise ValueError("Must be JSON Serializable")
        with reglock:
            cache.clear()

            prefix = key.split("/")[0]
            f = self.open(prefix)
            if not 'keys' in f:
                f['keys'] = {}
            if not key in f['keys']:
                f['keys'][key] = {}
            if 'schema' in f['keys'][key]:
                validictory.validate(value, f['keys'][key]['schema'])
            f['keys'][key]['data'] = copy.deepcopy(value)
            if not _noRecoveryRecord:
                createRecoveryEntry(key, value, 0)


reglock = threading.RLock()

# This is not the actual way we determine if it is clean or not for saving, that is determined per file in an odd way.
# however, this is used for display purposes.
is_clean = True


def get(key, default=None):
    if key in cache:
        return cache[key]

    if not exists(key):
        return default
    prefix = key.split("/")[0]

    with reglock:
        f = registry.open(prefix)

        v = copy.deepcopy(f['keys'][key]['data'])
        cache[key] = v
        return v


def delete(key):
    prefix = key.split("/")[0]
    with reglock:
        if key in cache:
            del cache[key]

        f = registry.open(prefix)
        if not 'keys' in f:
            return False
        k = f['keys']
        del k[key]
        createRecoveryEntry(key, None, 1)


def exists(key):
    if key in cache:
        return True

    prefix = key.split("/")[0]
    with reglock:
        f = registry.open(prefix)
        if not 'keys' in f:
            return False
        k = f['keys']
        if key in k:
            return True
        else:
            return False


def ls(key):
    prefix = key.split("/")[0]

    with reglock:
        f = registry.open(prefix)
        if not 'keys' in f:
            return []
        k = f['keys']
        return([i.split("/")[-1] for i in k if (i.startswith(key) or i.startswith('/'+key))])


def setschema(key, schema):
    "Associate a validitory schema with a key such that nobody can set an invalid value to it"
    global is_clean
    is_clean = False
    try:
        json.dumps({key: schema})
    except:
        raise Exception
    with reglock:
        prefix = key.split("/")[0]
        f = registry.open(prefix)
        if not 'keys' in f:
            f['keys'] = {}
        if not key in f['keys']:
            f['keys'][key] = {}
        validictory.SchemaValidator(schema)
        f['keys'][key]['schema'] = copy.deepcopy(schema)


def sync():
    global is_clean
    with reglock:
        x = registry.save()
    is_clean = True
    return x


registry = PersistanceArea(directories.regdir)
set = registry.set
