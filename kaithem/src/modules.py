# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

# File for keeping track of and editing kaithem modules(not python modules)
from .util import url
from io import BytesIO as StringIO
import zipfile
import shutil
import time
import os
import json
import traceback
import copy
import logging
import gc
import re
import weakref
import ast
import cherrypy
import yaml
from typing import Optional, Dict, Any
from . import auth, pages, directories, util, newevt, kaithemobj
from . import usrpages, messagebus, schemas
from .modules_state import (
    modulesLock,
    scopes,
    additionalTypes,
    fileResourceAbsPaths,
    external_module_locations,
    saveResource,
)
from .modules_state import (
    saveModule,
    parseTarget,
    getModuleFn,
    getResourceFn,
    serializeResource,
    safeFnChars,
)

from . import modules_state

logger = logging.getLogger("system")


try:
    import fcntl
except Exception:
    print(traceback.format_exc())


def lockFile(f):
    t = time.time()
    while time.time() - t > 5:
        try:
            fcntl.lockf(f, fcntl.LOCK_SH)
        except OSError:
            time.sleep(0.01)
        except Exception:
            return


def unlockFile(f):
    try:
        fcntl.lockf(f, fcntl.LOCK_SH)
    except Exception:
        pass


def new_empty_module():
    return {"__description": {"resource-type": "module-description", "text": ""}}


def new_module_container():
    return {}


def getInitialWhitespace(s):
    t = ""
    for i in s:
        if i in "\t ":
            t += i
        else:
            break
    return t


def readToplevelBlock(p, heading):
    """Given code and a heading like an if or a def, read everything under it.
    return tuple of the code we read, and the code WITHOUT that stuff
    """
    x = p.split("\n")
    state = "outside"
    indent = 0
    lines = []
    outside_lines = []
    firstline = ""
    heading = heading.strip()
    # Eliminate space, this is probably not the best way
    heading = heading.replace(" ", "").replace('"', "'")
    for i in x:
        if state == "outside":
            if i.replace(" ", "").replace('"', "'").strip().startswith(heading):
                state = "firstline"
                firstline = i
            else:
                outside_lines.append(i)
        elif state == "firstline":
            indent = getInitialWhitespace(i)
            if not indent:
                raise ValueError(f"Expected indented block after {firstline}")
            lines.append(i[len(indent) :])
            state = "inside"
        elif state == "inside":
            if not len(indent) <= len(getInitialWhitespace(i)):
                state = "outside"
            lines.append(i[len(indent) :])
    if not lines:
        if state == "outside":
            raise ValueError("No such block")
    return ("\n".join(lines), "\n".join(outside_lines))


def readStringFromSource(s, var):
    "Without executing it, get a string var from source code"
    a = ast.parse(s)
    b = a.body
    for i in b:
        if isinstance(i, ast.Assign):
            for t in i.targets:
                if t.id == var:
                    return i.value.s


def loadAllCustomResourceTypes():
    for i in modules_state.ActiveModules:
        # Ensure that child elements load before parent elements.
        for j in sorted(
            list(modules_state.ActiveModules[i].keys()),
            key=lambda n: len(n),
            reverse=True,
        ):
            r = modules_state.ActiveModules[i][j]
            if not isinstance(r, weakref.ref):
                if hasattr(r, "get"):
                    if r.get("resource-type", "") in additionalTypes:
                        try:
                            additionalTypes[r["resource-type"]].onload(i, j, r)
                        except Exception:
                            messagebus.post_message(
                                "/system/notifications/errors",
                                f"Error loading resource:{str((i, j))}",
                            )
                            logger.exception(f"Error loading resource: {str((i, j))}")
    for i in additionalTypes:
        additionalTypes[i].onfinishedloading()


class ResourceObject:
    def __init__(self, m: str = None, r: str = None, o=None):
        self.resource = r
        self.module = m
        self._object = o


class EventAPI(ResourceObject):
    resourceType = "event"

    def __init__(self, m, r, o):
        ResourceObject.__init__(self, m, r, o)

    def run(self):
        newevt.EventReferences[self.module, self.resource].manualRun()

    @property
    def scope(self):
        return newevt.EventReferences[self.module, self.resource].pymodule

    @property
    def data(self):
        return newevt.EventReferences[self.module, self.resource].data

    # Allow people to start and stop events at runtime.
    # Some events support a separate new pause/unpause api, otherwise use register
    # and unregister. It might not be safe to re-register events that
    # have a pause api.

    def start(self):
        ev = newevt.EventReferences[self.module, self.resource]
        if hasattr(ev, "unpause"):
            ev.unpause()
        else:
            ev.register()

    def stop(self):
        ev = newevt.EventReferences[self.module, self.resource]
        if hasattr(ev, "pause"):
            ev.pause()
        else:
            ev.unregister()

    def report_exception(self):
        """Call in an exception handler to handle the exception as if it came from the given event"""
        newevt.EventReferences[self.module, self.resource]._handle_exception()


class Page(ResourceObject):
    resourceType = "page"


class Permission(ResourceObject):
    resourceType = "permission"


class InternalFileRef(ResourceObject):
    resourceType = "internal-fileref"

    def getPath(self):
        "Return the actual path on the filesystem of things"
        return fileResourceAbsPaths[self.module, self.resource]


class ModuleObject:
    """
    These are the objects acessible as 'module' within pages, events, etc.
    Normally you use them to share variables, but they have incomplete and undocumented support
    For acting as an API for user code to acess or modify the resources, which could be useful if you want to be able to
    dynamically create resources, or more likely just acess file resource contents or metadata about the module.
    """

    def __init__(self, modulename: str):
        self.__kaithem_modulename__ = modulename

    def __getitem__(self, name: str):
        "When someone acesses a key, return an interface to that module."
        x = modules_state.ActiveModules[self.__kaithem_modulename__][name]

        module = self.__kaithem_modulename__

        resourcetype = x["resource-type"]

        if resourcetype == "page":
            x = Page(module, name, x)

        elif resourcetype == "event":
            x = EventAPI(module, name, x)

        elif resourcetype == "permission":
            x = Permission(module, name, x)

        elif resourcetype == "internal-fileref":
            x = InternalFileRef(module, name, x)

        return x

        raise KeyError(name)

    def __setitem__(self, name, value):
        "When someone sets an item, validate it, then do any required bookkeeping"

        module = self.__kaithem_modulename__

        def f():
            with modulesLock:
                if not isinstance(value, dict):
                    messagebus.post_message(
                        "/system/notifications/errors",
                        f"VirtualResource is removed. Can't add {name} to {module}",
                    )
                    return

                if "resource-type" not in value:
                    raise ValueError("Supplied dict has no resource-type")

                resourcetype = value["resource-type"]
                # Raise an exception on anything non-serializable or without a resource-type,
                # As those could break something.
                json.dumps({name: value})

                # Insert the new item into the global modules thing
                modules_state.ActiveModules[module][name] = value

                modules_state.modulesHaveChanged()

                # Make sure we recognize the resource-type, or else we can't load it.
                if (
                    resourcetype not in ["event", "page", "permission", "directory"]
                ) and (resourcetype not in additionalTypes):
                    raise ValueError("Unknown resource-type")

                # Do the type-specific init action
                if resourcetype == "event":
                    e = newevt.make_event_from_resource(module, name)
                    newevt.updateOneEvent(module, name, e)

                elif resourcetype == "page":
                    # Yes, module and resource really are backwards, and no, it wasn't a good idea to do that.
                    usrpages.updateOnePage(name, module)

                elif resourcetype == "permission":
                    auth.importPermissionsFromModules()

                else:
                    additionalTypes[resourcetype].onload(module, name, value)

                saveResource(module, name, value)

        modules_state.runWithModulesLock(f)


# This is used for the kaithem object.


class ResourceAPI:
    def __getitem__(self, name):
        if isinstance(name, tuple):
            x = modules_state.ActiveModules[name[0]][name[1]]
            if isinstance(x, weakref.ref):
                return x
            else:
                raise ValueError("Name refers to a non-virtual resource")


kaithemobj.kaithem.resource = ResourceAPI()


def readResourceFromFile(
    fn: str, relative_name: str, ver: int = 1, modulename=Optional[str]
):
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
    validate(x[0])
    if not (x[0] == original):
        logger.info(
            f"Resource {x[1]} is in an older format and should be migrated to the new file type"
        )
    # For now don't break anything by actually changing the data.
    return (original, x[1])


# Backwards compatible resource loader.
def readResourceFromData(d, relative_name: str, ver: int = 1, filename=None):
    """Returns (datadict, ResourceName)
    Should be pure except logging
    """
    fn = relative_name
    try:
        # This regex is meant to handle any combination of cr, lf, and trailing whitespaces
        # We don't do anything with more that 3 sections yet, so limit just in case there's ----
        # in a markdown file
        sections = re.split(r"\r?\n?----*\s*\r?\n*", d, 2)

        shouldRemoveExtension = False

        isSpecialEncoded = False
        wasProblem = False
        if fn.endswith(".py"):
            isSpecialEncoded = True

            try:
                # Get the two code blocks, then remove  them before further processing
                action, restofthecode = readToplevelBlock(d, "def eventAction():")
                setup, restofthecode = readToplevelBlock(
                    restofthecode, "if __name__ == '__setup__':"
                )
                # Restofthecode doesn't have those blocks, we should be able to AST parse with less fear of
                # A syntax error preventing reading the data at all
                data = yaml.load(
                    readStringFromSource(restofthecode, "__data__"),
                    Loader=yaml.SafeLoader,
                )
                data["trigger"] = readStringFromSource(restofthecode, "__trigger__")
                data["setup"] = setup.strip()
                data["action"] = action.strip()

                r = data
                # This is a .py file, remove the extension
                shouldRemoveExtension = True
            except Exception:
                isSpecialEncoded = False
                wasProblem = True
                logger.exception(f"err loading as pyencoded: {fn}")

        # Markdown and most html files files start with --- and are delimited by ---
        # The first section is YAML and the second is the page body.
        elif fn.endswith((".md", ".html")):
            isSpecialEncoded = True
            try:
                data = yaml.load(sections[1], Loader=yaml.SafeLoader)
                data["body"] = sections[2]
                r = data
                shouldRemoveExtension = True
            except Exception:
                isSpecialEncoded = False
                wasProblem = True
                logger.exception(f"err loading as html encoded: {fn}")
        elif fn.endswith((".yaml", ".json")):
            shouldRemoveExtension = True

        if not isSpecialEncoded:
            r = yaml.load(sections[0], Loader=yaml.SafeLoader)

            # Catch new style save files
            if len(sections) > 1:
                if r["resource-type"] == "page":
                    r["body"] = sections[1]

                if r["resource-type"] == "event":
                    r["setup"] = sections[1]
                    r["action"] = sections[2]

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
            return (None, False)
        else:
            raise
    if not r or "resource-type" not in r:
        if (
            "/.git" in fn
            or "/.gitignore" in fn
            or "__filedata__" in fn
            or fn.endswith(".directory")
        ):
            return None, False
        else:
            print(fn)
    # If no resource timestamp use the one from the file time.
    if "resource-timestamp" not in r:
        if filename:
            r["resource-timestamp"] = int(os.stat(filename).st_mtime * 1000000)
        else:
            r["resource-timestamp"] = int(time.time() * 1000000)
    # Set the loaded from. we strip this before saving
    r["resource-loadedfrom"] = fn

    resourcename = util.unurl(fn)
    if shouldRemoveExtension:
        resourcename = ".".join(resourcename.split(".")[:-1])
    return (r, resourcename)


def indent(s, prefix="    "):
    s = [prefix + i for i in s.split("\n")]
    return "\n".join(s)


def initModules():
    global external_module_locations
    """"Find the most recent module dump folder and use that. Should there not be a module dump folder, it is corrupted, etc,
    Then start with an empty list of modules. Should normally be called once at startup."""

    if not os.path.isdir(directories.moduledir):
        os.makedirs(directories.moduledir)

    if not util.get_immediate_subdirectories(directories.moduledir):
        return
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
    newevt.getEventsFromModules()
    usrpages.getPagesFromModules()
    modules_state.moduleshash = modules_state.hashModules()
    logger.info("Initialized modules")


def loadModules(modulesdir: str):
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
            loadModule(s, util.unurl(i[2:-9]), detect_ignorable)
        except Exception:
            messagebus.post_message(
                "/system/notifications/errors",
                f" Error loading external module: {traceback.format_exc(4)}",
            )


def detect_ignorable(path: str):
    "Recursive detect paths that should be ignored and left alone when loading and saving"
    # Safety counter, this seems like it might need it.
    for i in range(64):
        if _detect_ignorable(path):
            return True
        path = os.path.dirname(path)
        # Detect end of path
        if not os.path.split(path)[1]:
            return


def _detect_ignorable(path: str):
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


def reloadOneResource(module, resource):
    r = modules_state.ActiveModules[module][resource]
    if "resource-loadedfrom" in r:
        mfolder = getModuleDir(module)
        loadOneResource(
            mfolder, os.path.relpath(r["resource-loadedfrom"], mfolder), module
        )


def validate(r):
    "Clean up any old dict keys"
    try:
        if r["resource-type"] == "page":
            schemas.get_validator("resources/page").validate(r)
            schemas.clean_data_inplace("resources/page", r)

    except Exception:
        print("Ignoring invalid resource and loading anyway for now")
        print(traceback.format_exc())
        print(str(r)[10240])


def loadOneResource(folder, relpath, module):
    try:
        r, resourcename = readResourceFromFile(
            os.path.join(folder, relpath), relpath, module
        )
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

    if "resource-type" not in r:
        logger.warning(f"No resource type found for {str(resourcename)}")
        return

    validate(r)
    handleResourceChange(module, resourcename)

    if r["resource-type"] == "internal-fileref":
        # Handle two separate ways of handling these file resources.
        # One is to store them directly in the module data in a special folder.
        # That's what we do if we are using an external folder
        # For internal folders we don't want to store duplicate copies in the dumps,
        # So we store them in one big folder that is shared between all loaded modules.
        # Which is not exactly ideal, but all the per-module stuff is stored in dumps.

        # Note that we handle things in library modules the same as in loaded vardir modules,
        # Because things in vardir modules get copied to the vardir.

        if util.in_directory(
            os.path.join(folder, relpath), directories.vardir
        ) or util.in_directory(os.path.join(folder, relpath), directories.datadir):
            t = parseTarget(r["target"], module)
            d = getModuleDir(module)
            target = os.path.normpath(os.path.join(d, "__filedata__", t))
        else:
            t = parseTarget(r["target"], module, True)
            target = os.path.normpath(os.path.join(folder, "__filedata__", t))

        if not os.path.exists(target):
            logger.info(f"Missing file resource: {target}")

            messagebus.post_message(
                "/system/notifications",
                f"File Resource: {target}Was deleted",
            )

            try:
                del modules_state.ActiveModules[module][resourcename]

                # Remove the no longer relevant internal fileref
                os.remove(os.path.join(folder, relpath))
            except Exception:
                logger.exception("Error cleaning up old file ref")
        else:
            fileResourceAbsPaths[module, resourcename] = target


def loadModule(folder: str, modulename: str, ignore_func=None, resource_folder=None):
    "Load a single module but don't bookkeep it . Used by loadModules"
    logger.debug(f"Attempting to load module {modulename}")

    if not resource_folder:
        resource_folder = os.path.join(folder, "__filedata__")

    with modulesLock:
        # Make an empty dict to hold the module resources
        module = {}

        # Iterate over all resource files and load them
        for root, dirs, files in os.walk(folder):
            # Function used to ignore things like VCS folders and such
            if ignore_func and ignore_func(root):
                continue
            if root.startswith(resource_folder):
                continue
            for i in files:
                if ignore_func and ignore_func(i):
                    continue
                relfn = os.path.relpath(os.path.join(root, i), folder)
                fn = os.path.join(folder, relfn)
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
                    if "resource-type" not in r:
                        logger.warning(f"No resource type found for {resourcename}")
                        continue
                    if r["resource-type"] == "internal-fileref":
                        fileResourceAbsPaths[modulename, resourcename] = os.path.join(
                            folder, "__filedata__", url(resourcename, safeFnChars)
                        )

                        if not os.path.exists(
                            fileResourceAbsPaths[modulename, resourcename]
                        ):
                            logger.error(
                                "Missing file resource: "
                                + fileResourceAbsPaths[modulename, resourcename]
                            )
                            messagebus.post_message(
                                "/system/notifications/errors",
                                "Missing file resource: "
                                + fileResourceAbsPaths[modulename, resourcename],
                            )

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
                module[util.unurl(relfn)] = {"resource-type": "directory"}

        # Make resource objects for anything missing one
        # Don't save to disk since there's nothing we can't generate.
        if resource_folder:
            autoGenerateFileRefResources(module, modulename)

        scopes[modulename] = ModuleObject(modulename)
        modules_state.ActiveModules[modulename] = module
        messagebus.post_message("/system/modules/loaded", modulename)

        logger.info(
            "Loaded module "
            + modulename
            + " with md5 "
            + modules_state.getModuleHash(modulename)
        )
        # bookkeeponemodule(name)


def autoGenerateFileRefResources(module: Dict[str, Any], modulename: str):
    "Return true if anything generared"
    rt = False
    with modulesLock:
        resource_folder = os.path.join(getModuleDir(modulename), "__filedata__")
        if not os.path.exists(resource_folder):
            return

        torm = []
        for i in fileResourceAbsPaths:
            if not os.path.exists(fileResourceAbsPaths[i]):
                m, r = i
                if m == modulename:
                    if module[r].get("ephemeral", False):
                        torm.append(i)

        for i in torm:
            rt = True
            fileResourceAbsPaths.pop(i)

        s = set(fileResourceAbsPaths.values())
        for root, dirs, files in os.walk(resource_folder):
            for i in files:
                f = os.path.join(root, i)
                if not resource_folder.endswith("/"):
                    resource_folder += "/"

                data_basename = f[len(resource_folder) :]

                if f not in s:
                    rt = True
                    module[util.unurl(data_basename)] = {
                        "resource-type": "internal-fileref",
                        "target": f"$MODULERESOURCES/{data_basename}",
                        "ephemeral": True,
                    }
                fileResourceAbsPaths[modulename, data_basename] = f

            for i in dirs:
                f = os.path.join(root, i)
                if not resource_folder.endswith("/"):
                    resource_folder += "/"

                data_basename = f[len(resource_folder) :]

                if data_basename not in module:
                    rt = True
                    r = {
                        "resource-type": "directory",
                        "resource-timestamp": int(time.time() * 1000000),
                        "ephemeral": True,
                    }
                    module[data_basename] = r
    return rt


def getModuleAsYamlZip(module, noFiles=True):
    incompleteError = False
    with modulesLock:
        # Ensure any manually put therer files are there
        autoGenerateFileRefResources(module, modules_state.ActiveModules[module])
        # We use a stringIO so we can avoid using a real file.
        ram_file = StringIO()
        z = zipfile.ZipFile(ram_file, "w")
        # Dump each resource to JSON in the ZIP
        for resource in modules_state.ActiveModules[module]:
            if not resource.strip():
                raise RuntimeError("WTF?")
            if not isinstance(modules_state.ActiveModules[module][resource], dict):
                continue
            # AFAIK Zip files fake the directories with naming conventions
            s, ext = serializeResource(modules_state.ActiveModules[module][resource])
            z.writestr(f"{url(module, ' ')}/{url(resource, safeFnChars)}{ext}", s)
            if (
                modules_state.ActiveModules[module][resource]["resource-type"]
                == "internal-fileref"
            ):
                if noFiles:
                    raise RuntimeError(
                        "Cannot download this module without admin rights as it contains embedded files"
                    )

                target = fileResourceAbsPaths[module, resource]
                if os.path.exists(target):
                    z.write(
                        target, f"{module}/__filedata__/{url(resource, safeFnChars)}"
                    )

                else:
                    if not incompleteError:
                        logger.error(f"Missing file(s) in module including: {target}")
                        incompleteError = True
        z.close()
        s = ram_file.getvalue()
        ram_file.close()
        return s


def load_modules_from_zip(f, replace=False):
    "Given a zip file, import all modules found therin."
    new_modules = {}
    z = zipfile.ZipFile(f)
    newfrpaths = {}

    for i in z.namelist():
        if i.endswith("/"):
            continue
        # get just the folder, ie the module
        p = util.unurl(i.split("/", 1)[0])

        relative_name = (i.split("/", 1))[1]
        if p not in new_modules:
            new_modules[p] = {}
        try:
            if "/__filedata__/" not in i:
                try:
                    f = z.open(i)
                    r, n = readResourceFromData(f.read().decode(), relative_name)
                    if r is None:
                        raise RuntimeError(
                            "Attempting to decode file "
                            + str(i)
                            + " resulted in a value of None"
                        )
                    new_modules[p][n] = r
                    if r["resource-type"] == "internal-fileref":
                        newfrpaths[p, n] = os.path.join(
                            directories.vardir,
                            "modules",
                            "data",
                            p,
                            "__filedata__",
                            url(n, safeFnChars),
                        )
                except Exception:
                    raise ValueError(f"{i} in zip makes no sense")
                finally:
                    f.close()
            else:
                try:
                    inputfile = z.open(i)
                    folder = os.path.join(
                        directories.vardir, "modules", "data", p, "__filedata__"
                    )
                    os.makedirs(folder, exist_ok=True)

                    # Assumimg format is MODULE/__filedata__/file.png, we get just
                    # file.png
                    data_basename = util.unurl(i.split("/", 2)[2])

                    # We are saving it in vardir/module/__filedata__/file.png
                    dataname = os.path.join(folder, data_basename)

                    os.makedirs(os.path.dirname(dataname), exist_ok=True)

                    total = 0
                    with open(dataname, "wb") as f:
                        while True:
                            d = inputfile.read(8192)
                            total += len(d)
                            if total > 8 * 1024 * 1024 * 1024:
                                raise RuntimeError(
                                    "Cannot upload resource file bigger than 8GB"
                                )
                            if not d:
                                break
                            f.write(d)
                        f.flush()
                        os.fsync(f.fileno())
                finally:
                    inputfile.close()
                newfrpaths[p, n] = dataname
        except Exception:
            raise RuntimeError(f"Could not correctly process {str(i)}")

    with modulesLock:
        backup = {}
        # Precheck if anything is being overwritten
        replaced_count = 0
        for i in new_modules:
            if i in modules_state.ActiveModules:
                if not replace:
                    raise cherrypy.HTTPRedirect("/errors/alreadyexists")
                replaced_count += 1

        for i in new_modules:
            if i in modules_state.ActiveModules:
                backup[i] = modules_state.ActiveModules[i].copy()
                rmModule(
                    i,
                    "Module Deleted by "
                    + pages.getAcessingUser()
                    + " during process of update",
                )

                messagebus.post_message(
                    "/system/notifications",
                    "User "
                    + pages.getAcessingUser()
                    + " Deleted old module "
                    + i
                    + " for auto upgrade",
                )
                messagebus.post_message("/system/modules/unloaded", i)
                messagebus.post_message(
                    "/system/modules/deleted", {"user": pages.getAcessingUser()}
                )

        try:
            for i in new_modules:
                modules_state.ActiveModules[i] = new_modules[i]

                messagebus.post_message(
                    "/system/notifications",
                    "User "
                    + pages.getAcessingUser()
                    + " uploaded module"
                    + i
                    + " from a zip file",
                )
                bookkeeponemodule(i)
        except Exception:
            # TODO: Do we need more cleanup before revert?
            for i in new_modules:
                if i in backup:
                    modules_state.ActiveModules[i] = backup[i]

                    messagebus.post_message(
                        "/system/notifications",
                        "User "
                        + pages.getAcessingUser()
                        + " uploaded module"
                        + i
                        + " from a zip file, but initializing failed. Reverting to old version.",
                    )
                    bookkeeponemodule(i)
            raise
        fileResourceAbsPaths.update(newfrpaths)

        modules_state.modulesHaveChanged()
        for i in new_modules:
            saveModule(modules_state.ActiveModules[i], i)

    z.close()
    return new_modules.keys()


def bookkeeponemodule(module, update=False):
    """Given the name of one module that has been copied to modules_state.ActiveModules but nothing else,
    let the rest of the system know the module is there."""
    if module not in scopes:
        scopes[module] = ModuleObject(module)

    for i in modules_state.ActiveModules[module]:
        # Handle events separately due to dependency resolution logic
        if modules_state.ActiveModules[module][i]["resource-type"] not in ("event"):
            try:
                handleResourceChange(module, i)
            except Exception:
                messagebus.post_message(
                    "/system/notifications/errors", f"Failed to load  resource: {i}"
                )

    newevt.getEventsFromModules([module])

    if not update:
        messagebus.post_message("/system/modules/loaded", module)


def mvResource(module: str, resource: str, toModule: str, toResource: str):
    # Raise an error if the user ever tries to move something somewhere that does not exist.
    new = util.split_escape(toResource, "/", "\\", True)
    if not (
        "/".join(new[:-1]) in modules_state.ActiveModules[toModule] or len(new) < 2
    ):
        raise cherrypy.HTTPRedirect("/errors/nofoldeday1veerror")
    if toModule not in modules_state.ActiveModules:
        raise cherrypy.HTTPRedirect("/errors/nofoldermoveerror")
    # If something by the name of the directory we are moving to exists but it is not a directory.
    # short circuit evaluating the len makes this clause ignore moves that are to the root of a module.
    if not (
        len(new) < 2
        or modules_state.ActiveModules[toModule]["/".join(new[:-1])]["resource-type"]
        == "directory"
    ):
        raise cherrypy.HTTPRedirect("/errors/nofoldermoveerror")

    if (
        modules_state.ActiveModules[module][resource]["resource-type"]
        == "internal-fileref"
    ):
        modules_state.ActiveModules[toModule][toResource] = modules_state.ActiveModules[
            module
        ][resource]
        del modules_state.ActiveModules[module][resource]
        fileResourceAbsPaths[toModule, toResource] = fileResourceAbsPaths[
            module, resource
        ]
        del fileResourceAbsPaths[module, resource]
        return

    if modules_state.ActiveModules[module][resource]["resource-type"] == "event":
        modules_state.ActiveModules[toModule][toResource] = modules_state.ActiveModules[
            module
        ][resource]
        del modules_state.ActiveModules[module][resource]
        newevt.renameEvent(module, resource, toModule, toResource)
        return

    if modules_state.ActiveModules[module][resource]["resource-type"] == "page":
        modules_state.ActiveModules[toModule][toResource] = modules_state.ActiveModules[
            module
        ][resource]
        del modules_state.ActiveModules[module][resource]
        usrpages.removeOnePage(module, resource)
        usrpages.updateOnePage(toResource, toModule)
        return

    o = modules_state.ActiveModules[toModule][toResource]
    os.makedirs(os.path.dirname(getResourceFn(toModule, toResource, o)))

    # Don't move if the file is already saved under the right name
    if os.path.exists(getResourceFn(module, resource, o)):
        shutil.move(
            getResourceFn(module, resource, o), getResourceFn(toModule, toResource, o)
        )


def rmResource(module: str, resource: str, message: str = "Resource Deleted"):
    "Delete one resource by name, message is an optional message explaining the change"
    with modulesLock:
        r = modules_state.ActiveModules[module].pop(resource)
        modules_state.modulesHaveChanged()
    try:
        if r["resource-type"] == "page":
            usrpages.removeOnePage(module, resource)

        elif r["resource-type"] == "event":
            newevt.removeOneEvent(module, resource)

        elif r["resource-type"] == "directory":
            # Directories are special, they can have the extra data file
            fn = f"{getResourceFn(module, resource, r)}.yaml"

            if os.path.exists(fn):
                os.remove(fn)

        elif r["resource-type"] == "permission":
            auth.importPermissionsFromModules()  # sync auth's list of permissions

        elif r["resource-type"] == "internal-fileref":
            try:
                os.remove(fileResourceAbsPaths[module, resource])
            except Exception:
                print(traceback.format_exc())

            del fileResourceAbsPaths[module, resource]
            usrpages.removeOnePage(module, resource)

        else:
            additionalTypes[r["resource-type"]].ondelete(module, resource, r)

        fn = getResourceFn(module, resource, r)

        if os.path.exists(fn):
            os.remove(fn)

    except Exception:
        messagebus.post_message(
            "/system/modules/errors/unloading",
            f"Error deleting resource: {str((module, resource))}",
        )


def getModuleDir(module: str):
    if module in external_module_locations:
        return external_module_locations[module]

    else:
        return os.path.join(directories.moduledir, "data", module)


def newModule(name: str, location: Optional[str] = None):
    "Create a new module by the supplied name, throwing an error if one already exists. If location exists, load from there."

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
                    "__description": {"resource-type": "module-description", "text": ""}
                }
        else:
            modules_state.ActiveModules[name] = {
                "__description": {"resource-type": "module-description", "text": ""}
            }

        bookkeeponemodule(name)
        # Go directly to the newly created module
        messagebus.post_message(
            "/system/notifications",
            f"User {pages.getAcessingUser()} Created Module {name}",
        )
        messagebus.post_message(
            "/system/modules/new", {"user": pages.getAcessingUser(), "module": name}
        )

        modules_state.modulesHaveChanged()
        saveModule(modules_state.ActiveModules[name], name)


def rmModule(module, message="deleted"):
    with modulesLock:
        x = modules_state.ActiveModules.pop(module)
        j = {i: copy.deepcopy(x[i]) for i in x if not (isinstance(x[i], weakref.ref))}
        scopes.pop(module)

    # Delete any custom resource types hanging around.
    for k in j:
        if j[k].get("resource-type", None) in additionalTypes:
            try:
                additionalTypes[j[k]["resource-type"]].ondelete(module, k, j[k])
            except Exception:
                messagebus.post_message(
                    "/system/modules/errors/unloading",
                    f"Error deleting resource: {str(module, k)}",
                )

    # Get rid of any lingering cached events
    newevt.removeModuleEvents(module)
    # Get rid of any permissions defined in the modules.
    auth.importPermissionsFromModules()
    usrpages.removeModulePages(module)

    with modulesLock:
        if module in external_module_locations:
            del external_module_locations[module]

    fn = getModuleFn(module)

    if module not in external_module_locations:
        if os.path.exists(fn):
            shutil.rmtree(fn)

    modules_state.modulesHaveChanged()
    # Get rid of any garbage cycles associated with the event.
    gc.collect()
    messagebus.post_message("/system/modules/unloaded", module)
    messagebus.post_message(
        "/system/modules/deleted", {"user": pages.getAcessingUser()}
    )


class KaithemEvent(dict):
    pass


def handleResourceChange(module, resource, obj=None):
    modules_state.modulesHaveChanged()

    with modules_state.modulesLock:
        t = modules_state.ActiveModules[module][resource]["resource-type"]

        resourceobj = modules_state.ActiveModules[module][resource]

        if t == "permission":
            auth.importPermissionsFromModules()  # sync auth's list of permissions

        elif t == "internal-fileref":
            try:
                usrpages.updateOnePage(resource, module)
            except Exception:
                messagebus.post_message(
                    "/system/notifications/errors",
                    f"Failed to load file resource: {resource} module: {module}",
                )

        elif t == "event":
            # if the test compile fails, evt will be None and the function will look up the old one in the modules database
            # And compile that. Otherwise, we avoid having to double-compile.
            newevt.updateOneEvent(resource, module, obj)

        elif t == "page":
            try:
                usrpages.updateOnePage(resource, module)
            except Exception as e:
                usrpages.makeDummyPage(resource, module)
                logger.exception("failed to load resource")
                messagebus.post_message(
                    "/system/notifications/errors",
                    "Failed to load page resource: "
                    + resource
                    + " module: "
                    + module
                    + "\n"
                    + str(e)
                    + "\n"
                    + "please edit and reload.",
                )

        else:
            additionalTypes[resourceobj["resource-type"]].update(module, resource, {})
