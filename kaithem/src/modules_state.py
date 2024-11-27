# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

# This file is just for keeping track of state info that would otherwise cause circular issues.
import base64
import copy
import datetime
import hashlib
import os
import time
import urllib
import urllib.parse
from collections.abc import Iterator
from typing import Any, Callable

import beartype
import structlog
import yaml
from stream_zip import ZIP_64, stream_zip

from . import context_restrictions, directories, util
from .resource_types import ResourceDictType, ResourceType, additionalTypes

# Dummy keeps linter happy
ResourceType = ResourceType


# / is there because we just forbid use of that char for anything but dirs,
# So there is no confusion
safeFnChars = "~@*&()-_=+/ '"
FORBID_CHARS = """\n\r\t@*&^%$#`"';:<>.,|{}+=[]\\"""

logger = structlog.get_logger(__name__)

# This lets us have some modules saved outside the var dir.
external_module_locations: dict[str, str] = {}


prev_versions: dict[tuple, dict] = {}


def get_module_metadata(module: str) -> dict[str, Any]:
    m = ActiveModules[module]
    if "__metadata__" not in m:
        return {}

    return dict(copy.deepcopy(m["__metadata__"]))


@beartype.beartype
def check_forbidden(s: str) -> None:
    if not s:
        raise ValueError("Resource or module name cannot be empty")

    if len(s) > 255:
        raise ValueError(f"Excessively long name {s[:128]}...")

    for i in s:
        if i in FORBID_CHARS:
            raise ValueError(f"{s} contains {i}")

    if s[0] == "/":
        raise ValueError("Resource or module name cannot start with /")


def getModuleDir(module: str) -> str:
    if module in external_module_locations:
        return external_module_locations[module]

    else:
        return os.path.join(directories.moduledir, "data", module)


# Items must be dicts, with the key being the name of the type, and the dict itself having the key 'editpage'
# That is a function which takes 3 arguments, module and resource, and the current resource arg,
# and must return an HTML string to be returned to the user.

# The key update must also be defined.
# This must take a module, a resource, the current resource object, and a dict created from a form
# POST, and returning a new updated resource object.


# If you want to be able to move the module, you must define a function 'on_move' that takes(module,resource,newmodule,newresource,object)
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

# When a module is saved outside of the var dir, we put the folder in which it is saved in here.
external_module_locations = {}


def parseTarget(t: str, module: str, in_ext: bool = False):
    if t.startswith("$MODULERESOURCES/"):
        t = t[len("$MODULERESOURCES/") :]
    return t


def getExt(r: ResourceDictType):
    if r["resource_type"] == "directory":
        return ""

    elif r["resource_type"] == "page":
        if r.get("template_engine", "") == "markdown":
            return ".md"
        else:
            return ".html"

    elif r["resource_type"] == "event":
        return ".py"

    else:
        return ".yaml"


def serializeResource(name: str, obj: ResourceDictType) -> dict[str, str]:
    """Returns data as a dict of file base names
    to file contents, to be written in appropriate folder"""

    r = copy.deepcopy(obj)
    rt = r["resource_type"]
    assert isinstance(rt, str)

    if rt in additionalTypes:
        return additionalTypes[rt].to_files(name, r)

    else:
        return {f"{name.split('/')[-1]}.yaml": yaml.dump(r)}


def importFiledataFolderStructure(module: str) -> None:
    with modulesLock:
        folder = getModuleDir(module)
        folder = os.path.join(folder, "__filedata__")

        if os.path.exists(folder):
            for root, dirs, files in os.walk(folder):
                for i in dirs:
                    if "." in i:
                        continue

                    relfn = os.path.relpath(os.path.join(root, i), folder)

                    # Create a directory resource for the directory
                    ActiveModules[module][util.unurl(relfn)] = {
                        "resource_type": "directory"
                    }


@beartype.beartype
def writeResource(
    obj: ResourceDictType, dir: str, resource_name: str
) -> str | None:
    "Write resource into dir"
    # logger.debug("Saving resource to "+str(fn))

    if obj.get("do-not-save-to-disk", False):
        return

    # directories get saved just by writing a literal directory.
    if obj["resource_type"] == "directory":
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
        if not ".".join(bn.split(".")[:-1]) == resource_name.split("/")[-1]:
            raise RuntimeError(
                f"Plugin wants to save file {bn} that doesn't match resource {resource_name}"
            )
        if "/" in bn:
            raise RuntimeError(
                f"Resource saving plugins can't create subfolder. Requested fn {bn}"
            )
        fn = os.path.join(dir, bn)
        d = files[bn]

        data = d.encode("utf-8")

        # Check if anything is actually new
        if os.path.isfile(fn):
            with open(fn, "rb") as f:
                if f.read() == data:
                    return fn

        os.makedirs(os.path.dirname(fn), exist_ok=True)

        with open(fn, "wb") as f:
            util.chmod_private_try(fn, execute=False)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

            return fn


@beartype.beartype
def save_resource(
    module: str,
    resource: str,
    resourceData: ResourceDictType,
    name: str | None = None,
) -> None:
    if "__do__not__save__to__disk__:" in module:
        return

    name = name or resource

    # Open a file at /where/module/resource

    dir = get_resource_save_location(module, name)

    if not name == resource:
        for i in os.listdir(dir):
            if i.startswith(name + "."):
                raise ValueError(
                    f"File appears to exist: {os.path.join(dir, i)}"
                )

    if resourceData["resource_type"] == "directory":
        d = dict(copy.deepcopy(resourceData))
        d.pop("resource_type", None)

        # As the folder on disk is enough to create the resource internally, we don't need to clutter
        # the FS with this if there is no extra data
        if not d:
            return

    writeResource(resourceData, dir, resource)


@beartype.beartype
def rawInsertResource(
    module: str, resource: str, resource_data: ResourceDictType
):
    resourceData: dict[str, Any] = copy.deepcopy(resource_data)  # type: ignore
    check_forbidden(resource)
    assert resource[0] != "/"

    if "resource_timestamp" not in resourceData:
        resourceData["resource_timestamp"] = int(time.time() * 1000000)

    # todo maybe we don't need os independence
    d = os.path.dirname(resource.replace("/", os.path.pathsep))
    while d:
        if d not in ActiveModules[module]:
            ActiveModules[module][d.replace(os.path.pathsep, "/")] = {
                "resource_type": "directory"
            }
        d = os.path.dirname(d)

    ActiveModules[module][resource] = resourceData
    save_resource(module, resource, resourceData)
    recalcModuleHashes()


@beartype.beartype
def rawDeleteResource(m: str, r: str, type: str | None = None) -> None:
    """
    Delete a resource from the module, but don't do
    any bookkeeping. Will not remove whatever runtime objects
    were created from the resource, also will not update hashes.
    """
    resourceData = ActiveModules[m].pop(r)
    rt = resourceData["resource_type"]
    assert isinstance(rt, str)

    if type and rt != type:
        raise ValueError("Resource exists but is wrong type")

    dir = get_resource_save_location(m, r)
    for i in os.listdir(dir):
        if i.startswith(r + "."):
            os.remove(os.path.join(dir, i))

    recalcModuleHashes()


def getModuleFn(modulename: str) -> str:
    if modulename not in external_module_locations:
        dir = os.path.join(directories.moduledir, "data", modulename)
    else:
        dir = external_module_locations[modulename]

    return dir


def get_resource_save_location(m: str, r: str) -> str:
    dir = getModuleFn(m)
    return os.path.dirname(os.path.join(dir, urllib.parse.quote(r, safe=" /")))


@beartype.beartype
def saveModule(
    module: dict[str, ResourceDictType], modulename: str
) -> list[str] | None:
    """Returns a list of saved module,resource tuples and the saved resource.
    ignore_func if present must take an abs path and return true if that path should be
    left alone. It's meant for external modules and version control systems.
    """

    if "__do__not__save__to__disk__:" in modulename:
        return

    if modulename in external_module_locations:
        fn = os.path.join(
            directories.moduledir, "data", modulename + ".location"
        )
        with open(fn, "w") as f:
            f.write(external_module_locations[modulename])

    # Iterate over all of the resources in a module and save them as json files
    # under the URL url module name for the filename.
    logger.debug("Saving module " + str(modulename))
    saved: list[str] = []

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
            save_resource(modulename, resource, resourceData=r)

        saved.append(modulename)
        return saved
    except Exception:
        raise


# Lets just store the entire list of modules as a huge dict for now at least
ActiveModules: dict[str, dict[str, ResourceDictType]] = {}

moduleshash = "000000000000000000000000"
modulehashes: dict[str, str] = {}
modulewordhashes: dict[str, str] = {}


def hashModules() -> str:
    try:
        m = hashlib.sha256()
        with modulesLock:
            for i in sorted(ActiveModules.keys()):
                m.update(i.encode())
                m.update(hashModule(i).encode())
        return (
            base64.b32encode(m.digest()[:16]).decode().upper().replace("=", "")
        )
    except Exception:
        logger.exception("Could not hash modules")
        return "ERRORHASHINGMODULES"


def wordHashModule(module: str) -> str:
    try:
        with modulesLock:
            return util.memorableHash(
                hashModule(module).encode("utf-8"),
                num=4,
                separator=" ",
            )
    except Exception:
        logger.exception("Could not hash module")
        return "ERRORHASHINGMODULE"


def getModuleHash(m: str) -> str:
    global modulehashes

    if m not in modulehashes:
        modulehashes[m] = hashModule(m)
    return modulehashes[m].upper()


def getModuleWordHash(m: str) -> str:
    global modulewordhashes
    if m not in modulewordhashes:
        modulewordhashes[m] = wordHashModule(m)
    return modulewordhashes[m].upper()


def recalcModuleHashes() -> None:
    global moduleshash, modulehashes, modulewordhashes
    moduleshash = hashModules()
    modulehashes = {}
    modulewordhashes = {}


def deterministic_walk(
    d: str,
) -> Iterator[
    tuple[str, list[str], list[Any]]
    | tuple[str, list[Any], list[str]]
    | tuple[str, list[str], list[str]]
    | tuple[str, list[Any], list[Any]]
]:
    dirs: list[str] = []
    files: list[str] = []

    sld = sorted(os.listdir(d))

    for i in sld:
        if os.path.isdir(os.path.join(d, i)):
            dirs.append(i)
        else:
            files.append(i)

    dirs = sorted(dirs)
    yield d, dirs, sorted(files)

    for i in dirs:
        yield from deterministic_walk(os.path.join(d, i))


def iter_fc(f: str) -> Iterator[bytes]:
    with open(f, "rb") as fd:
        for i in range(100000):
            d = fd.read(128 * 1024)
            if d:
                yield d
            else:
                return
    raise RuntimeError("File size limit")


def member_files(
    module: str,
) -> Iterator[
    tuple[
        str,
        datetime.datetime,
        int,
        Callable[[Any, Any], tuple[object, object, Any, None, None]],
        Iterator[Any],
    ]
]:
    dir = getModuleDir(module)
    for root, dirs, files in deterministic_walk(dir):
        for i in files:
            x = os.path.join(root, i)
            if "./" in x or ".\\" in x:
                continue

            fd = os.open(x, os.O_RDONLY)
            mode = os.fstat(fd).st_mode
            mtime = datetime.datetime.fromtimestamp(os.fstat(fd).st_mtime)
            os.close(fd)

            fn = os.path.relpath(x, dir)
            yield (f"{module}/{fn}", mtime, mode, ZIP_64, iter_fc(x))


def getModuleAsYamlZip(module: str) -> Iterator[Any]:
    return stream_zip(member_files(module))


def hashModule(module: str) -> str:
    x = hashlib.sha256()
    x.update(module.encode())
    for i in member_files(module):
        x.update(b"\0" * 32)
        x.update(i[0].encode())
        for d in i[4]:
            x.update(d)
    return base64.b32encode(x.digest()[:16]).decode().upper().replace("=", "")


def in_folder(n: str, folder_name: str) -> bool:
    """Return true if name r represents a kaithem resource in folder f"""
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
    o: list[str] = []
    x = ActiveModules[m]
    for i in x:
        if in_folder(i, d):
            o.append(i)
    return o


"this lock protects the activemodules thing. Any changes at all should go through this."
modulesLock = context_restrictions.Context("ModulesLock")


# For passing things to that owning thread
mlockFunctionQueue: list[Callable[[], Any]] = []


# Define a place to keep the module private scope objects.
# Every module has a object of class object that is used so user code can share state between resources in
# a module
scopes: dict[str, Any] = {}
