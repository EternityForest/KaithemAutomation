# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

# This file is just for keeping track of state info that would otherwise cause circular issues.
import copy
import hashlib
import json
import logging
import os
import time
import urllib
import urllib.parse
from threading import RLock
from typing import Any

import beartype
import yaml

from . import directories, util
from .resource_types import ResourceDictType, ResourceType, additionalTypes

# Dummy keeps linter happy
ResourceType = ResourceType


# / is there because we just forbid use of that char for anything but dirs,
# So there is no confusion
safeFnChars = "~@*&()-_=+/ '"

logger = logging.getLogger("system")

# This lets us have some modules saved outside the var dir.
external_module_locations: dict[str, str] = {}


# Items must be dicts, with the key being the name of the type, and the dict itself having the key 'editpage'
# That is a function which takes 3 arguments, module and resource, and the current resource arg,
# and must return an HTML string to be returned to the user.

# The key update must also be defined.
# This must take a module, a resource, the current resource object, and a dict created from a form
# POST, and returing a new updated resource object.


# If you want to be able to move the module, you must define a function 'onmove' that takes(module,resource,newmodule,newresource,object)
# The update function will always run under a lock.


# If you want your resource to do something special when it loads, you must define onload(module,resource,object)

# All of these functions are guaranteed to only be called during times when the entire list of modules is locked, only
# one at a time, etc.


# If you, as is most likely, want to be able to create new resources, define a function createpage(module,resource)
# That returns an HTML page for creating a new resource.

# It must post to /modules/module/MODULENAME/addresourcetarget/TYPE/THE/PATH/WITHIN/THE/MODULE with name as a kwarg


# To actually create the page, define a function create(module,resource, kwargs)
# TWhich must return the JSON object of the module. Onload will be automatically called for newly created resources.

# Note that the actual dict objects are directly passed, you can modify them in place but you still must return them.

# This is a dict indexed by module/resource tuples that contains the absolute path to what
# The system considers the current "loaded" version.
fileResourceAbsPaths: dict[tuple, str] = {}

# When a module is saved outside of the var dir, we put the folder in which it is saved in here.
external_module_locations = {}


def parseTarget(t: str, module: str, in_ext=False):
    if t.startswith("$MODULERESOURCES/"):
        t = t[len("$MODULERESOURCES/") :]
    return t


def getExt(r):
    if r["resource-type"] == "directory":
        return ""

    elif r["resource-type"] == "page":
        if r.get("template-engine", "") == "markdown":
            return ".md"
        else:
            return ".html"

    elif r["resource-type"] == "event":
        return ".py"

    else:
        return ".yaml"


def serializeResource(name, obj) -> dict[str, str]:
    "Returns the raw data, plus the proper file extension"

    r = copy.deepcopy(obj)

    # This is a ram only thing that tells us where it is saved
    if "resource-loadedfrom" in r:
        del r["resource-loadedfrom"]

    if r["resource-type"] in additionalTypes:
        return additionalTypes[r["resource-type"]].to_files(name, r)

    else:
        return {f"{name}.yaml": yaml.dump(r)}


def writeResource(obj: dict, dir: str, resource_name: str):
    "Write resource into dir"
    # logger.debug("Saving resource to "+str(fn))

    if obj.get("do-not-save-to-disk", False):
        return

    # directories get saved just by writing a literal directory.
    if obj["resource-type"] == "directory":
        fn = os.path.join(dir, resource_name)
        if os.path.exists(fn):
            if not os.path.isdir(fn):
                os.remove(fn)
                os.makedirs(fn, exist_ok=True)
        else:
            os.makedirs(fn, exist_ok=True)
        return

    files = serializeResource(resource_name, obj)

    for bn in files:
        if not bn.split(".")[0] == resource_name.split("/")[-1]:
            raise RuntimeError(f"Plugin wants to save file {bn} that doesn't match resource {resource_name}")
        if "/" in bn:
            raise RuntimeError(f"Resource saving plugins can't create subfolder. Requested fn {bn}")
        fn = os.path.join(dir, bn)
        d = files[bn]

        data = d.encode("utf-8")

        # Check if anything is actually new
        if os.path.isfile(fn):
            with open(fn, "rb") as f:
                if f.read() == data:
                    if "resource-loadedfrom" not in obj:
                        obj["resource-loadedfrom"] = []

                    obj["resource-loadedfrom"].append(fn)
                    return fn

        os.makedirs(os.path.dirname(fn), exist_ok=True)

        with open(fn, "wb") as f:
            util.chmod_private_try(fn, execute=False)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

            if "resource-loadedfrom" not in obj:
                obj["resource-loadedfrom"] = []

            obj["resource-loadedfrom"].append(fn)
            return fn


@beartype.beartype
def saveResource(module: str, resource: str, resourceData: ResourceDictType, name: str | None = None):
    if "__do__not__save__to__disk__:" in module:
        return

    name = name or resource

    # Open a file at /where/module/resource

    dir = get_resource_save_location(module, name)

    if not name == resource:
        for i in os.listdir(dir):
            if i.startswith(name + "."):
                raise ValueError(f"File appears to exist: {os.path.join(dir, i)}")

    if resourceData["resource-type"] == "directory":
        d = copy.deepcopy(resourceData)
        d.pop("resource-type", None)

        # As the folder on disk is enough to create the resource internally, we don't need to clutter
        # the FS with this if there is no extra data
        if not d:
            return

    writeResource(resourceData, dir, resource)


@beartype.beartype
def rawInsertResource(module: str, resource: str, resourceData: ResourceDictType):
    ActiveModules[module][resource] = resourceData
    saveResource(module, resource, resourceData)


@beartype.beartype
def rawDeleteResource(m: str, r: str, type: str | None = None):
    """
    Delete a resource from the module, but don't do
    any bookkeeping. Will not remove whatever runtime objectes
    were created from the resource, also will not update hashes.
    """
    resourceData = ActiveModules[m].pop(r)
    rt = resourceData["resource-type"]
    assert isinstance(rt, str)

    if type and rt != type:
        raise ValueError("Resource exists but is wrong type")

    dir = get_resource_save_location(m, r)
    for i in os.listdir(dir):
        if i.startswith(r + "."):
            os.remove(os.path.join(dir, i))


def getModuleFn(modulename: str):
    if modulename not in external_module_locations:
        dir = os.path.join(directories.moduledir, "data", modulename)
    else:
        dir = external_module_locations[modulename]

    return dir


def get_resource_save_location(m, r):
    dir = getModuleFn(m)
    return os.path.dirname(os.path.join(dir, urllib.parse.quote(r, safe=" /")))


@beartype.beartype
def saveModule(module: dict[str, ResourceDictType], modulename: str):
    """Returns a list of saved module,resource tuples and the saved resource.
    ignore_func if present must take an abs path and return true if that path should be
    left alone. It's meant for external modules and version control systems.
    """

    if "__do__not__save__to__disk__:" in modulename:
        return

    if modulename in external_module_locations:
        fn = os.path.join(directories.moduledir, "data", modulename + ".location")
        with open(fn, "w") as f:
            f.write(external_module_locations[modulename])

    # Iterate over all of the resources in a module and save them as json files
    # under the URL url module name for the filename.
    logger.debug("Saving module " + str(modulename))
    saved = []

    # do the saving
    dir = getModuleFn(modulename)

    if not modulename:
        raise RuntimeError("Something wrong")

    try:
        # Make sure there is a directory at where/module/
        os.makedirs(dir, exist_ok=True)
        util.chmod_private_try(dir)
        for resource in module:
            r = module[resource]
            saveResource(modulename, resource, resourceData=r)

        saved.append(modulename)
        return saved
    except Exception:
        raise


class HierarchyDict:
    def __init__(self):
        self.flat = {}
        # This tree only stores the tree structure, actual elements are referenced by flat.
        # Names can be both dirs and entries, and no matter what are marked by dicts in the root.
        # To get the actual item, use root to navigate quickly and use flat to get the actual item
        self.root = {}

    def parsePath(self, s):
        return s.split("/")

    def pathJoin(self, *p):
        return "/".join(p)

    def copy(self):
        return self.flat.copy()

    def ls(self, k):
        p = self.parsePath(k)
        currentLocation = self.root
        # Navigate to the last dir in the path, making dirs as needed.
        for i in p:
            if i in currentLocation:
                currentLocation = currentLocation[i]
            else:
                currentLocation[i] = {}
                currentLocation = currentLocation[i]
        return currentLocation.keys()

    def __contains__(self, k):
        if k in self.flat:
            return True
        return False

    def __setitem__(self, k, v):
        self.flat[k] = v
        p = self.parsePath(k)
        currentLocation = self.root
        # Navigate to the last dir in the path, making dirs as needed.
        #
        for i in p:
            if i in currentLocation:
                currentLocation = currentLocation[i]
            else:
                currentLocation[i] = {}
                currentLocation = currentLocation[i]

    def __getitem__(self, k):
        return self.flat[k]

    def __delitem__(self, k):
        del self.flat[k]
        p = self.parsePath(k)
        location = self.root
        pathTaken = []
        # Navigate to the last dir in the path, making dirs as needed
        for i in p[:-1]:
            if i in location:
                pathTaken.append((location, location[i], i))
                location = location[i]
            else:
                location[i] = {}
                pathTaken.append((location, location[i], i))
                location = location[i]
        # Now delete the "leaf node"
        for i in location[p[-1]]:
            try:
                del self[self.pathJoin(k, i)]
            except KeyError:
                pass

        del location[p[-1]]

        # This deletes the entire chain of empty folders, should such things exist.
        for i in reversed(pathTaken):
            if not i[1]:
                del i[0][2]


# Lets just store the entire list of modules as a huge dict for now at least
ActiveModules: dict[str, dict[str, ResourceDictType]] = {}

moduleshash = "000000000000000000000000"
modulehashes = {}
modulewordhashes = {}


def hashModules():
    """For some unknown lagacy reason, the hash of the entire module state is different from the hash of individual modules
    hashed together
    """
    try:
        m = hashlib.md5()
        with modulesLock:
            for i in sorted(ActiveModules.keys()):
                m.update(i.encode("utf-8"))
                for j in sorted(ActiveModules[i].keys()):
                    m.update(j.encode("utf-8"))
                    m.update(json.dumps(ActiveModules[i][j], sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return m.hexdigest().upper()
    except Exception:
        logger.exception("Could not hash modules")
        return "ERRORHASHINGMODULES"


def hashModule(module: str):
    try:
        m = hashlib.md5()
        with modulesLock:
            m.update(
                json.dumps(
                    {i: ActiveModules[module][i] for i in ActiveModules[module]},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
        return m.hexdigest()
    except Exception:
        logger.exception("Could not hash module")
        return "ERRORHASHINGMODULE"


def wordHashModule(module: str):
    try:
        with modulesLock:
            return util.blakeMemorable(
                json.dumps(
                    {i: ActiveModules[module][i] for i in ActiveModules[module]},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
                num=12,
                separator=" ",
            )
    except Exception:
        logger.exception("Could not hash module")
        return "ERRORHASHINGMODULE"


def getModuleHash(m: str):
    if m not in modulehashes:
        modulehashes[m] = hashModule(m)
    return modulehashes[m].upper()


def getModuleWordHash(m: str):
    if m not in modulewordhashes:
        modulewordhashes[m] = wordHashModule(m)
    return modulewordhashes[m].upper()


def modulesHaveChanged():
    global moduleshash, modulehashes, modulewordhashes
    moduleshash = hashModules()
    modulehashes = {}
    modulewordhashes = {}


def in_folder(n: str, folder_name: str):
    """Return true if name r represents a kaihem resource in folder f"""
    # Note: this is about kaithem resources and folders, not actual filesystem dirs.
    if not n.startswith(folder_name):
        return False
    # Get the path as a list
    r = n.split("/")
    # Get the path of the folder
    f = folder_name.split("/")
    if f[0] == "":
        f.pop()
    # make sure the resource path is one longer than module
    if not len(r) == len(f) + 1:
        return False
    return True


def ls_folder(m: str, d: str) -> list[str]:
    "List a kaithem resource folder's direct children"
    o = []
    x = ActiveModules[m]
    for i in x:
        if in_folder(i, d):
            o.append(i)
    return o


"this lock protects the activemodules thing. Any changes at all should go through this."
modulesLock = RLock()


# For passing thigs to that owning thread
mlockFunctionQueue = []

# Allows the owner f the lock to let other threads run things in it,
# By overriding this, them setting it back.

# This is because USER code may want to use this lock, q=while it is taken by the page handler compiling it.
# As the user init code is a different thread, they have to pass requests to us


def runWithModulesLock(g):
    return g()


# TODO: Whatever this is should probably go away


def listenForMlockRequests():
    global runWithModulesLock

    def f(g):
        g._ret = None
        g._err = None
        mlockFunctionQueue.append(g)
        while mlockFunctionQueue:
            time.sleep(0.01)
        if g._err:
            # No clue whats happening here
            raise g._err  # type: ignore
        return g._ret

    runWithModulesLock = f


def stopMlockRequests():
    "ALWAYS call this before you stop polling for requests"
    global runWithModulesLock

    def f(g):
        return g()

    runWithModulesLock = f


def pollMlockRequests():
    while mlockFunctionQueue:
        f = mlockFunctionQueue[-1]

        try:
            f._ret = f()
        except Exception as e:
            f._err = e
        mlockFunctionQueue.pop()


# Define a place to keep the module private scope obects.
# Every module has a object of class object that is used so user code can share state between resources in
# a module
scopes: dict[str, Any] = {}


class ResourceObject:
    def __init__(self, m: str | None = None, r: str | None = None, o=None):
        self.resource = r
        self.module = m
        self._object = o
