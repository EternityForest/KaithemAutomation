# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

# File for keeping track of and editing kaithem modules(not python modules)
import copy
import gc
import logging
import os
import re
import shutil
import time
import traceback
import weakref
import zipfile
from collections.abc import Callable
from io import BytesIO

import beartype
import structlog
import yaml
from scullery import snake_compat

from . import auth, directories, messagebus, modules_state, pages, util
from .modules_state import (
    ResourceDictType,
    additionalTypes,
    check_forbidden,
    external_module_locations,
    getModuleDir,
    getModuleFn,
    modulesLock,
    saveModule,
    scopes,
)

logger = structlog.get_logger(__name__)


def new_empty_module():
    return {
        "__metadata__": {
            "resource_type": "module_metadata",
            "description": "",
            "resource_timestamp": int(time.time() * 1000000),
        }
    }


def loadAllCustomResourceTypes() -> None:
    # TODO this is O(m * n) time. Is that bad?

    types: list[tuple[float, str]] = []
    for key, typeobj in additionalTypes.items():
        types.append((typeobj.priority, key))
    types = sorted(types)

    for loading_priority, loading_rt in types:
        for i in modules_state.ActiveModules:
            # Ensure that child elements load before parent elements.
            for j in sorted(
                list(modules_state.ActiveModules[i].keys()),
                key=lambda n: len(n),
                reverse=True,
            ):
                orig = modules_state.ActiveModules[i][j]
                # Be defensive in case something on loader code
                # Tries to modify something
                r = copy.deepcopy(orig)
                if hasattr(r, "get"):
                    if r.get("resource_type", "") == loading_rt:
                        try:
                            rt = r["resource_type"]
                            assert isinstance(rt, str)
                            additionalTypes[rt]._validate(r)
                            additionalTypes[rt].on_load(i, j, r)
                        except Exception:
                            messagebus.post_message(
                                "/system/notifications/errors",
                                f"Error loading resource:{str((i, j))}",
                            )
                            logger.exception(
                                f"Error loading resource: {str((i, j))}"
                            )
                if not r == orig:
                    logger.warning(
                        f"Loader tried to modify resource object {i}:{j} during load"
                    )

    for i in additionalTypes:
        additionalTypes[i].on_finished_loading(None)


class ModuleObject:
    """
    These are the objects acessible as 'module' within pages, events, etc.
    Normally you use them to share variables, but they have incomplete and undocumented support
    For acting as an API for user code to acess or modify the resources, which could be useful if you want to be able to
    dynamically create resources, or more likely just acess file resource contents or metadata about the module.
    """

    def __init__(self, modulename: str) -> None:
        self.__kaithem_modulename__ = modulename


@beartype.beartype
def readResourceFromFile(
    fn: str, relative_name: str, ver: int = 1, modulename: str | None = None
) -> tuple[ResourceDictType | None, str | None]:
    """Relative name is rel to the folder, aka the part of the path that actually belongs in
    the resource name.

    Modulename is there because this function will one day auto-migrate to new versions of the file
    format.
    """
    with open(fn, "rb") as f:
        d = f.read().decode("utf-8")

    x = readResourceFromData(d, relative_name, ver, filename=fn)
    # logger.debug("Loaded resource from file "+fn)
    original = copy.deepcopy(x[0])

    if not (x[0] == original):
        logger.info(
            f"Resource {x[1]} is in an older format and should be migrated to the new file type"
        )
    # For now don't break anything by actually changing the data.
    return (original, x[1])


# Backwards compatible resource loader.
def readResourceFromData(
    d: str, relative_name: str, ver: int = 1, filename: str | None = None
) -> tuple[ResourceDictType | None, str | None]:
    """Returns (datadict, ResourceName)
    Should be pure except logging
    """
    fn = relative_name
    r = None
    if filename and (
        not filename.endswith(".yaml") or filename.endswith(".toml")
    ):
        return None, None
    try:
        # This regex is meant to handle any combination of cr, lf, and trailing whitespaces
        # We don't do anything with more that 3 sections yet, so limit just in case there's ----
        # in a markdown file
        sections = re.split(r"\r?\n?----*\s*\r?\n*", d, 2)

        shouldRemoveExtension = False

        isSpecialEncoded = False
        wasProblem = False

        if fn.endswith((".yaml", ".json")):
            shouldRemoveExtension = True

        if not isSpecialEncoded:
            r = yaml.load(sections[0], Loader=yaml.SafeLoader)
            r = snake_compat.snakify_dict_keys(r)

            # Catch new style save files
            if len(sections) > 1:
                if r["resource_type"] == "page":
                    r["body"] = sections[1]

        if wasProblem:
            messagebus.post_message(
                "/system/notifications/warnings",
                f"Potential problem or nonstandard encoding with file: {fn}",
            )
    except Exception:
        # This is a workaround for when dolphin puts .directory files in directories and gitignore files
        # and things like that. Also ignore attempts to load from filedata
        # I'd like to add more workarounds if there are other programs that insert similar crap files.
        if (
            "/.git" in fn
            or "/.gitignore" in fn
            or "__filedata__" in fn
            or fn.endswith(".directory")
        ):
            return (None, None)
        else:
            raise
    if not r or "resource_type" not in r:
        if (
            "/.git" in fn
            or "/.gitignore" in fn
            or "__filedata__" in fn
            or fn.endswith(".directory")
        ):
            return None, None
        else:
            print(fn)

    assert r

    # If no resource timestamp use the one from the file time.
    if "resource_timestamp" not in r:
        if filename:
            r["resource_timestamp"] = int(os.stat(filename).st_mtime * 1000000)
        else:
            r["resource_timestamp"] = int(time.time() * 1000000)

    resourcename = util.unurl(fn)
    if shouldRemoveExtension:
        resourcename = ".".join(resourcename.split(".")[:-1])
    return (r, resourcename)


def indent(s, prefix="    "):
    s = [prefix + i for i in s.split("\n")]
    return "\n".join(s)


def initModules() -> None:
    global external_module_locations
    """"Find the most recent module dump folder and use that. Should there not be a module dump folder, it is corrupted, etc,
    Then start with an empty list of modules. Should normally be called once at startup."""

    if not os.path.isdir(directories.moduledir):
        os.makedirs(directories.moduledir, exist_ok=True)

    try:
        # __COMPLETE__ is a special file we write to the dump directory to show it as valid
        possibledir = os.path.join(directories.moduledir, "data")
        if os.path.isdir(possibledir):
            loadModules(possibledir)

    except Exception:
        logging.exception("Err loading modules")
        messagebus.post_message(
            "/system/notifications/errors",
            f" Error loading modules: {traceback.format_exc(4)}",
        )

    auth.importPermissionsFromModules()
    loadAllCustomResourceTypes()
    modules_state.moduleshash = modules_state.hashModules()
    logger.info("Initialized modules")


def loadModules(modulesdir: str) -> None:
    "Load all modules in the given folder to RAM."
    logger.debug(f"Loading modules from {modulesdir}")
    for i in util.get_immediate_subdirectories(modulesdir):
        loadModule(os.path.join(modulesdir, i), util.unurl(i))

    for i in os.listdir(modulesdir):
        try:
            if not i.endswith(".location"):
                continue
            if not os.path.isfile(os.path.join(modulesdir, i)):
                continue
            # Read ythe location we are supposed to load from
            with open(os.path.join(modulesdir, i)) as f:
                s = f.read(4096)
            # Get rid of the .location, then set the location in the dict
            with modulesLock:
                external_module_locations[util.unurl(i[0:-9])] = s
            # We use the ignore func when loading ext modules
            loadModule(s, util.unurl(i[0:-9]), detect_ignorable)
        except Exception:
            messagebus.post_message(
                "/system/notifications/errors",
                f" Error loading external module: {traceback.format_exc(4)}",
            )


def detect_ignorable(path: str) -> bool:
    "Recursive detect paths that should be ignored and left alone when loading and saving"
    # Safety counter, this seems like it might need it.
    for i in range(64):
        if _detect_ignorable(path):
            return True
        path = os.path.dirname(path)
        # Detect end of path
        if not os.path.split(path)[1]:
            return False
    return False


def _detect_ignorable(path: str) -> bool:
    "Detect paths that should be ignored when loading a module"
    # Detect .git
    if os.path.basename(path) == ".git":
        # Double check, because we can, on the off chance something else is named .git
        if os.path.exists(os.path.join(path, "HEAD")) or os.path.exists(
            os.path.join(path, "branches")
        ):
            return True
    # I think that's how you detect hg repos?
    if os.path.basename(path) == ".hg" and os.path.isdir(path):
        return True
    if os.path.basename(path) in [".gitignore", ".gitconfig"]:
        return True
    return False


@beartype.beartype
def load_one_yaml_resource(folder: str, relpath: str, module: str):
    if not relpath.endswith(".yaml") or relpath.endswith(".json"):
        return "Wrong extension"
    try:
        r: ResourceDictType | None
        r, resourcename = readResourceFromFile(
            os.path.join(folder, relpath), relpath, modulename=module
        )
        assert isinstance(r, dict)
        assert isinstance(resourcename, str)
        assert "resource_type" in r
    except Exception:
        messagebus.post_message(
            "/system/notifications/errors",
            f"Error loadingresource from: {os.path.join(folder, relpath)}",
        )
        logger.exception(
            f"Error loading resource from file {os.path.join(folder, relpath)}"
        )
        raise
    if not r:
        return

    modules_state.ActiveModules[module][resourcename] = r

    if "resource_type" not in r:
        logger.warning(f"No resource type found for {str(resourcename)}")
        return

    handleResourceChange(module, resourcename)


def loadModule(
    folder: str,
    modulename: str,
    ignore_func: Callable[[str], bool] | None = None,
    resource_folder: str | None = None,
) -> None:
    "Load a single module but don't bookkeep it . Used by loadModules"
    logger.debug(f"Attempting to load module {modulename}")

    if not resource_folder:
        resource_folder = os.path.join(folder, "__filedata__")

    with modulesLock:
        # Make an empty dict to hold the module resources
        module: dict[str, ResourceDictType] = {}

        for t in additionalTypes:
            found = additionalTypes[t].scan_dir(folder)
            module.update(found)

        # Iterate over all resource files and load them
        for root, dirs, files in os.walk(folder):
            # Function used to ignore things like VCS folders and such
            if ignore_func and ignore_func(root):
                continue
            if root.startswith(resource_folder):
                continue

            # Handle all resources that have unusual file types.

            # TODO multiple storage types for one
            # Name mean we can have conflicts, detect and warn
            for i in dirs:
                if "/__" not in i:
                    for t in additionalTypes:
                        abs = os.path.join(root, i)
                        rel = os.path.relpath(abs, folder)
                        found = additionalTypes[t].scan_dir(abs)
                        found = copy.deepcopy(found)

                        for rn in found:
                            if rel:
                                module[rel + "/" + rn] = found[rn]
                            else:
                                module[rn] = found[rn]

            for i in files:
                relfn = os.path.relpath(os.path.join(root, i), folder)
                fn = os.path.join(folder, relfn)
                if ignore_func and ignore_func(i):
                    continue

                if "/." in fn:
                    continue

                if fn.endswith(("yaml", ".json")):
                    try:
                        # TODO: Lib modules? filedata?
                        # Load the resource and add it to the dict. Resouce names are urlencodes in filenames.
                        try:
                            r, resourcename = readResourceFromFile(fn, relfn)
                            if not r or not resourcename:
                                # File managers sprinkle this crap around
                                if not os.path.basename(fn) == ".directory":
                                    logger.exception(f"Null loading {fn}")
                                continue

                        except Exception:
                            logger.exception(f"Error loading {fn}")
                            continue

                        module[resourcename] = r
                        if "resource_type" not in r:
                            logger.warning(
                                f"No resource type found for {resourcename}"
                            )
                            continue

                    except Exception:
                        messagebus.post_message(
                            "/system/notifications/errors",
                            f"Error loading from: {fn}\r\n{traceback.format_exc()}",
                        )
                        raise

            for i in dirs:
                if ignore_func and ignore_func(i):
                    continue
                relfn = os.path.relpath(os.path.join(root, i), folder)
                fn = os.path.join(folder, relfn)
                if "/__filedata__/" in fn or fn.endswith("/__filedata__"):
                    continue

                # Create a directory resource for the dirrctory
                module[util.unurl(relfn)] = {"resource_type": "directory"}

        if "__metadata__" not in module:
            module["__metadata__"] = {
                "resource_type": "module_metadata",
                "description": "",
                "resource_timestamp": int(time.time() * 1000000),
            }

        # Legacy upgrade TODO: Remove at some point
        if "__description" in module:
            md = dict(copy.deepcopy(module["__metadata__"]))
            md["description"] = module["__description"]["text"]
            module["__metadata__"] = md

            del module["__description"]

        scopes[modulename] = ModuleObject(modulename)
        modules_state.ActiveModules[modulename] = module
        modules_state.importFiledataFolderStructure(modulename)
        messagebus.post_message("/system/modules/loaded", modulename)

        logger.info("Loaded module " + modulename)


def load_modules_from_zip(f: BytesIO, replace: bool = False) -> None:
    """Given a zip file, import all modules found therin.
    On failure, revert to existing module if replacing"""
    z = zipfile.ZipFile(f)
    tmp = os.path.join(directories.vardir, "modules", "__upload__")
    bu = os.path.join(directories.vardir, "modules", "__backup__")

    if os.path.exists(bu):
        shutil.rmtree(bu)
    if os.path.exists(tmp):
        shutil.rmtree(tmp)

    os.makedirs(bu)

    try:
        with modulesLock:
            z.extractall(tmp)

            for i in os.listdir(tmp):
                temp_module_folder = os.path.join(tmp, i)
                if os.path.isdir(temp_module_folder):
                    old_module_dir = None
                    m_backup = None
                    if i in modules_state.ActiveModules:
                        if "module_lock" in modules_state.get_module_metadata(
                            i
                        ):
                            raise PermissionError("Old module is locked")

                        old_module_dir = getModuleDir(i)
                        if not replace:
                            raise RuntimeError(f"Module {i} already loaded")
                        if i in external_module_locations:
                            raise RuntimeError(
                                f"Module {i} is an external module"
                            )

                        shutil.move(old_module_dir, bu)
                        m_backup = os.path.join(bu, i)
                        rmModule(i)
                    try:
                        loadModule(temp_module_folder, i)
                        bookkeeponemodule(i)
                        shutil.move(
                            temp_module_folder,
                            os.path.join(directories.vardir, "modules", "data"),
                        )
                    except Exception:
                        if old_module_dir and m_backup:
                            try:
                                if i in modules_state.ActiveModules:
                                    rmModule(i)
                            except Exception:
                                pass

                            shutil.move(
                                m_backup, os.path.dirname(old_module_dir)
                            )
                            loadModule(old_module_dir, i)
                            bookkeeponemodule(i)
                        raise

    finally:
        if os.path.exists(bu):
            shutil.rmtree(bu)
        if os.path.exists(tmp):
            shutil.rmtree(tmp)

    z.close()


def bookkeeponemodule(module: str, update: bool = False) -> None:
    """Given the name of one module that has been copied to
    modules_state.ActiveModules but nothing else,
    let the rest of the system know the module is there."""

    if module not in scopes:
        scopes[module] = ModuleObject(module)

    for i in modules_state.ActiveModules[module]:
        # Handle events separately due to dependency resolution logic
        rt = modules_state.ActiveModules[module][i]["resource_type"]
        assert isinstance(rt, str)

        try:
            handleResourceChange(module, i, newly_added=not update)
        except Exception:
            messagebus.post_message(
                "/system/notifications/errors", f"Failed to load  resource: {i}"
            )

    for i in modules_state.additionalTypes:
        modules_state.additionalTypes[i].on_finished_loading(module)

    if not update:
        messagebus.post_message("/system/modules/loaded", module)


def mvResource(module: str, resource: str, to_module: str, to_resource: str):
    # Raise an error if the user ever tries to move something somewhere that does not exist.
    new = to_resource.split("/")
    for i in new:
        check_forbidden(i)

    if not (
        "/".join(new[:-1]) in modules_state.ActiveModules[to_module]
        or len(new) < 2
    ):
        raise ValueError("Invalid destination")
    if to_module not in modules_state.ActiveModules:
        raise ValueError("Invalid destination")
    # If something by the name of the directory we are moving to exists but it is not a directory.
    # short circuit evaluating the len makes this clause ignore moves that are to the root of a module.
    if not (
        len(new) < 2
        or modules_state.ActiveModules[to_module]["/".join(new[:-1])][
            "resource_type"
        ]
        == "directory"
    ):
        raise ValueError("Invalid destination")

    obj: modules_state.ResourceDictType = modules_state.ActiveModules[module][
        resource
    ]
    rt = obj["resource_type"]

    assert isinstance(rt, str)

    mp = []
    dir = modules_state.get_resource_save_location(to_module, to_resource)

    for i in os.listdir(dir):
        if i.split(".", 1)[0] == resource:
            newfn = os.path.join(dir, i.replace(resource, to_resource))
            oldfn = os.path.join(dir, i)
            mp.append((oldfn, newfn))
            if os.path.exists(newfn):
                raise FileExistsError(newfn)

    modules_state.ActiveModules[to_module][to_resource] = (
        modules_state.ActiveModules[module][resource]
    )
    del modules_state.ActiveModules[module][resource]
    if rt in modules_state.additionalTypes:
        modules_state.additionalTypes[rt].on_move(
            module, resource, to_module, to_resource, obj
        )

    os.makedirs(dir, exist_ok=True)

    for i in mp:
        if not i[0] == i[1]:
            shutil.move(i[0], i[1])


def rmResource(
    module: str, resource: str, message: str = "Resource Deleted"
) -> None:
    "Delete one resource by name, message is an optional message explaining the change"
    with modulesLock:
        if resource not in modules_state.ActiveModules[module]:
            fr = os.path.join(getModuleDir(module), "__filedata__", resource)
            if os.path.isfile(fr):
                os.remove(fr)
            return

        r = modules_state.ActiveModules[module][resource]

    try:
        rt = r["resource_type"]
        assert isinstance(rt, str)

        if rt == "directory":
            # Directories are special, they can have the extra data file
            fn = getModuleDir(module)
            fn = os.path.join(fn, resource)

            if os.path.exists(fn):
                os.remove(fn)

        elif rt == "permission":
            auth.importPermissionsFromModules()  # sync auth's list of permissions

        else:
            additionalTypes[rt].on_delete(module, resource, r)

        modules_state.rawDeleteResource(module, resource)

    except Exception:
        messagebus.post_message(
            "/system/modules/errors/unloading",
            f"Error deleting resource: {str((module, resource))}",
        )


def newModule(name: str, location: str | None = None) -> None:
    "Create a new module by the supplied name, throwing an error if one already exists. If location exists, load from there."

    check_forbidden(name)
    # If there is no module by that name, create a blank template and the scope obj
    with modulesLock:
        if location:
            external_module_locations[name] = os.path.expanduser(location)

        if name in modules_state.ActiveModules:
            raise RuntimeError("A module by that name already exists.")
        if location:
            if os.path.isfile(location):
                raise RuntimeError(
                    "Cannot create new module that would clobber existing file"
                )

            if os.path.isdir(location):
                loadModule(location, name)
            else:
                modules_state.ActiveModules[name] = {
                    "__metadata__": {
                        "resource_type": "module_metadata",
                        "description": "",
                        "resource_timestamp": int(time.time() * 1000000),
                    }
                }
        else:
            modules_state.ActiveModules[name] = {
                "__metadata__": {
                    "resource_type": "module_metadata",
                    "description": "",
                    "resource_timestamp": int(time.time() * 1000000),
                }
            }
        saveModule(modules_state.ActiveModules[name], name)

        bookkeeponemodule(name)
        # Go directly to the newly created module
        messagebus.post_message(
            "/system/notifications",
            f"User {pages.getAcessingUser()} Created Module {name}",
        )
        messagebus.post_message(
            "/system/modules/new",
            {"user": pages.getAcessingUser(), "module": name},
        )

        modules_state.recalcModuleHashes()


def rmModule(module: str, message: str = "deleted") -> None:
    with modulesLock:
        x = modules_state.ActiveModules.pop(module)
        j = {
            i: copy.deepcopy(x[i])
            for i in x
            if not (isinstance(x[i], weakref.ref))
        }
        scopes.pop(module)

    for i in additionalTypes:
        additionalTypes[i].on_delete_module(module)

    # Delete any custom resource types hanging around.
    for k in j:
        if j[k].get("resource_type", None) in additionalTypes:
            try:
                rt = j[k]["resource_type"]
                assert isinstance(rt, str)
                additionalTypes[rt].on_delete(module, k, j[k])
            except Exception:
                messagebus.post_message(
                    "/system/modules/errors/unloading",
                    f"Error deleting resource: {module},{k}",
                )

    # Get rid of any permissions defined in the modules.
    auth.importPermissionsFromModules()

    with modulesLock:
        if module in external_module_locations:
            del external_module_locations[module]

    fn = getModuleFn(module)

    if module not in external_module_locations:
        if os.path.exists(fn):
            shutil.rmtree(fn)

    modules_state.recalcModuleHashes()
    # Get rid of any garbage cycles associated with the event.
    gc.collect()
    messagebus.post_message("/system/modules/unloaded", module)
    messagebus.post_message(
        "/system/modules/deleted", {"user": pages.getAcessingUser()}
    )


class KaithemEvent(dict):
    pass


def createResource(module: str, resource: str, data: ResourceDictType):
    modules_state.rawInsertResource(module, resource, data)
    handleResourceChange(module, resource)


def handleResourceChange(
    module: str, resource: str, obj: None = None, newly_added: bool = False
) -> None:
    modules_state.recalcModuleHashes()

    with modules_state.modulesLock:
        t = modules_state.ActiveModules[module][resource]["resource_type"]

        resourceobj = modules_state.ActiveModules[module][resource]

        assert isinstance(t, str)

        if t == "permission":
            auth.importPermissionsFromModules()  # sync auth's list of permissions
        if t == "module-description":
            pass
        else:
            if not newly_added:
                additionalTypes[t].on_update(module, resource, resourceobj)
            else:
                additionalTypes[t].on_load(module, resource, resourceobj)
