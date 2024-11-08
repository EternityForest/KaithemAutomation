# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

"""This file manages the concept of Users, Groups, and Permissions.
A "User" is a user of the system who can belong to zero or more "Groups" each of which can have
"Permissions". "Permissions" are strings like "WriteDisk". A user must be in at least one group
With a given permission to do that thing.
Users log in by means of a username and password and are given a token.
The token lets them do things. A user is considered "Logged in" if he is in possession
of a valid token"""

# Users and groups are saved in RAM and synched with the filesystem due to the goal
# of not using the filesystem much to save any SD cards.

import base64
import copy
import hashlib
import hmac
import json
import os
import shutil
import struct
import threading
import time
from typing import Any

import beartype
import structlog
import yaml
from argon2 import PasswordHasher

from . import directories, messagebus, modules_state, util

lock = threading.RLock()

default_data = {
    "groups": {
        "Administrators": {"permissions": ["__all_permissions__"]},
        "Guests": {
            "permissions": [
                "view_admin_info",
                "view_admin_info",
                "view_status",
                "enumerate_endpoints",
            ]
        },
    },
    "users": {
        "__guest__": {
            "groups": ["Guests"],
            "password": "V+hZrbd22NjvNwvQAfwOAzLrudfX/+SMuddMmetm0Vk=",  # pragma: allowlist secret
            "salt": "AtTjOSUQyNFoklVv+i8Lbw==",  # pragma: allowlist secret
            "settings": {"restrict-lan": False},
            "username": "__guest__",
        }
    },
}

# Python doesn't let us make custom attributes on normal dicts


class User(dict):
    def __init__(self, *a, **k) -> None:
        dict.__init__(self, *a, **k)

        self.permissions: dict[str, bool] | set[str] = {}
        self.limits: dict[str, int | float] = {}
        self.token: str | None = None


logger = structlog.get_logger(__name__)
# This maps raw tokens to users
Tokens: dict[str, User] = {}

Groups = {}
Users = {}

# This maps hashed tokens to users. There's an easy timing attack I'd imagine
# with looking up tokens literally in a dict.
# So instead we hash them, with a salt.

# For discussion of similar things, see:
# https://crypto.stackexchange.com/questions/25607/practical-uses-for-timing-attacks-on-hash-comparisons-e-g-md5
# https://security.stackexchange.com/questions/9192/timing-attacks-on-password-hashes

# This post discusses token auth directly:
# https://stackoverflow.com/questions/18605294/is-devises-token-authenticatable-secure
tokenHashes: dict[bytes, User] = {}

with open(os.path.join(directories.datadir, "defaultusersettings.yaml")) as f:
    defaultusersettings = yaml.load(f, Loader=yaml.SafeLoader)


usr_bytes = bytes


# If nobody loadsusers from the file make sure nothing breaks(mostly for tests)
"""A dict of all the users"""
Users: dict[str, User] = {}
"""A dict of all the groups"""
Groups: dict[str, dict] = {}

"""These are the "built in" permissions required to control basic functions
User code can add to these"""
BasePermissions: dict[str, str] = {
    "system_admin": "The main admin permission. Implies that the user can do anything the base account running the server can.",
    "view_admin_info": "Allows read but not write access to most of the system state",
    "view_status": "View the main page of the application, the active alerts, the about box, and other basic overview info",
    "enumerate_endpoints": "Required for any action that reveals whether something like a page or tagpoint exists.",
    "acknowledge_alerts": "Required to acknowledge alerts",
    "view_devices": "The default permission used to expose device points for reading, but devices can be configured to use others.",
    "write_devices": "The default permission used to expose device points for writing, but devices can be configured to use others.",
    "own_account_settings": "Edit ones own account preferences",
    "chandler_operator": "Access the Chandler console, jump to cues, change input fields.  Does not allow editing settings or groups.",
    "__guest__": "Everyone always has this permission even when not logged in",
    "__all_permissions__": "Special universal permission that grants all permissions in the system. Use with care.",
}

crossSiteRestrictedPermissions = BasePermissions.copy()
crossSiteRestrictedPermissions.pop("__guest__")
crossSiteRestrictedPermissions.pop("view_status")
crossSiteRestrictedPermissions.pop("enumerate_endpoints")


Permissions = {i: {"description": BasePermissions[i]} for i in BasePermissions}

"""True only if auth module stuff changed since last save, used to prevent unneccesary disk writes.
YOU MUST SET THIS EVERY TIME YOU CHANGE THE STATE AND WANT IT TO BE PERSISTANT"""
authchanged = False

# This __local_secret is really important, otherwise
# the timing attack might be even worse.
__local_secret = os.urandom(24)


def resist_timing_attack(data, maxdelay=0.0001) -> None:
    """Input dependant deterministic pseudorandom delay. Use to make sure delay
    is constant for a given user input, so that averaging won't work.
    Theory: http://blog.ircmaxell.com/2014/11/its-all-about-time.html
    """
    # Note the very high timing resolution.
    # Attackers can determine nanosecond level timings.
    h = hashlib.sha256(data + __local_secret).digest()
    t = struct.unpack("<Q", h[:8])[0]
    time.sleep(maxdelay * (t / 2**64))


def importPermissionsFromModules() -> None:
    """Import all user defined permissions that are module resources into the global
    list of modules that can be assigned, and delete any that are no loger defined
    in modules."""

    p2: dict[str, modules_state.ResourceDictType] = {
        i: {"description": BasePermissions[i]} for i in BasePermissions
    }
    with modules_state.modulesLock:
        for (
            module
        ) in modules_state.ActiveModules.copy():  # Iterate over all modules
            # for every resource of type permission
            for resource in modules_state.ActiveModules[module].copy():
                if (
                    modules_state.ActiveModules[module][resource][
                        "resource_type"
                    ]
                    == "permission"
                ):
                    # add it to the permissions list
                    p2[resource.split("/")[-1]] = modules_state.ActiveModules[
                        module
                    ][resource]
    global Permissions
    Permissions = p2


def changeUsername(old, new) -> None:
    "Change a user's username"
    global authchanged
    with lock:
        authchanged = True
        # this should work because tokens stores object references ad we are not deleting
        # the actual user object
        Users[new] = Users.pop(old)
        Users[new]["username"] = new
        dumpDatabase()


def changePassword(user, newpassword, useSystem=False) -> None:
    "Change a user's password"
    global authchanged
    if len(newpassword) > 256:
        raise ValueError("Password cannot be longer than 256 bytes")

    with lock:
        authchanged = True
        if useSystem:
            Users[user]["password"] = "system"  # pragma: allowlist secret
            dumpDatabase()
            return

        Users[user].pop("salt", None)
        Users[user]["algorithm"] = "argon2id"
        ph = PasswordHasher(
            memory_cost=8192, time_cost=1, parallelism=4, hash_len=32
        )
        m = ph.hash(newpassword)
        Users[user]["password"] = m
        dumpDatabase()


def add_user(username, password, useSystem=False) -> None:
    global authchanged
    with lock:
        authchanged = True
        if username not in Users:  # stop overwriting attempts
            Users[username] = User({"username": username, "groups": []})
            Users[username].limits = {}
            changePassword(username, password, useSystem)
        dumpDatabase()


def removeUser(user) -> None:
    global authchanged, tokenHashes
    with lock:
        authchanged = True
        x = Users.pop(user)
        # If the user has a token, delete that too
        if x.token in Tokens:
            Tokens.pop(x.token)
            try:
                tokenHashes.pop(hashToken(x.token))
            except Exception:
                dumpDatabase()
                raise
        dumpDatabase()


def removeGroup(group) -> None:
    global authchanged
    with lock:
        authchanged = True
        Groups.pop(group)
        # Remove all references to that group from all users
        for i in Users:
            if group in Users[i]["groups"]:
                Users[i]["groups"].remove(group)
        generateUserPermissions()
        dumpDatabase()


def addGroup(groupname) -> None:
    global authchanged
    with lock:
        authchanged = True
        if groupname not in Groups:  # stop from overwriting
            Groups[groupname] = {"permissions": []}
        dumpDatabase()


def add_user_to_group(username, group) -> None:
    global authchanged
    with lock:
        authchanged = True
        # Don't add multiple copies of a group
        if group not in Users[username]["groups"]:
            Users[username]["groups"].append(group)
        # Regenerate the per-user permissions cache for that user
        generateUserPermissions(username)
        dumpDatabase()


def removeUserFromGroup(username, group) -> None:
    global authchanged
    with lock:
        authchanged = True
        Users[username]["groups"].remove(group)
        # Regenerate the per-user permissions cache for that user
        generateUserPermissions(username)
        dumpDatabase()


def tryToLoadFrom(d: str) -> bool:
    with lock:
        with open(d) as f:
            temp = json.load(f)

        loadFromData(temp)
        return True


@beartype.beartype
def loadFromData(
    d: dict[
        str,
        dict[
            str,
            dict[str, list[str]]
            | dict[str, dict[str, int] | list[str]]
            | dict[str, list[str] | str | dict[str, bool]]
            | dict[str, str],
        ],
    ],
) -> bool:
    global tokenHashes
    with lock:
        temp = copy.deepcopy(d)

        Users.clear()
        Groups.clear()

        Groups.update(temp["groups"])

        global Tokens
        Tokens = {}
        tokenHashes.clear()
        for user in temp["users"]:
            Users[user] = User(temp["users"][user])
            assignNewToken(user)
        generateUserPermissions()
        return True


data_bad = False


def initializeAuthentication() -> None:
    with lock:
        "Load the saved users and groups, but not the permissions from the modules. "
        # If no file use default but set filename anyway so the dump function will work
        # Gets the highest numbered of all directories that are named after floating point values(i.e. most recent timestamp)

        if os.path.exists(
            os.path.join(directories.usersdir, "data", "users.json")
        ):
            try:
                tryToLoadFrom(
                    os.path.join(directories.usersdir, "data", "users.json")
                )
            except Exception as e:
                logger.exception(
                    "Error loading auth data, no users or groups loaded"
                )
                messagebus.post_message(
                    "/system/notifications/errors",
                    "Error loading auth data, no users or groups loaded:\n"
                    + str(e),
                )

        else:
            loadFromData(default_data)
            addLinuxSystemUser()
            messagebus.post_message(
                "/system/notifications/warnings",
                "No auth data found, using default admin user",
            )


def generateUserPermissions(username: None = None) -> None:
    """Generate the list of permissions for each user from their groups plus __guest__"""
    with lock:
        # TODO let you do one user at a time
        # Give each user all of the permissions that his or her groups have
        global tokenHashes

        for i in Users:
            limits = {}

            newp = []
            for j in Users[i].get("groups", []):
                # Handle nonexistant groups
                if j not in Groups:
                    logger.warning(
                        "User " + i + " is member of nonexistant group " + j
                    )

                for k in Groups[j]["permissions"]:
                    newp.append(k)

                # A user has access to the highest limit of all the groups he's in
                for k in Groups[j].get("limits", {}):
                    limits[k] = max(
                        Groups[j].get("limits", {})[k], limits.get(k, 0)
                    )

            Users[i].limits = limits

            # If the user has a token, update the stored copy of user in the tokens dict too
            t = Users[i].token
            if t:
                Tokens[t] = Users[i]
                tokenHashes[hashToken(t)] = Users[i]

            for j in Users[i].get("permissions", []):
                if j not in newp:
                    messagebus.post_message(
                        "/system/permissions/rmfromuser", (i, j)
                    )

            # Speed up by using a set
            Users[i].permissions = set(newp)


def addLinuxSystemUser() -> None:
    """
    Add an admin user, representing the Linux system user actually running the process, using the system
    login mechanism.

    The rationale for this is that the system user has full acess to everything anyway.  Restrict to LAN for the obvious reason
    we might to that on a local system.
    """
    global authchanged
    import getpass

    username = getpass.getuser()
    with lock:
        authchanged = True
        if username not in Users:  # stop overwriting attempts
            Users[username] = User(
                {
                    "username": username,
                    "groups": ["Administrators"],
                    "password": "system",  # pragma: allowlist secret
                    "settings": {"restrict-lan": True},
                }
            )

            Users[username].limits = {}
            generateUserPermissions()

        dumpDatabase()


def userLogin(username, password) -> str:
    """return a base64 authentication token on sucess or return False on failure"""

    # The user that we are running as

    try:
        import getpass
        import pwd

        # pragma: allowlist nextline secret
        if (
            username in Users
            and ("password" in Users[username])
            and Users[username]["password"]
            == "system"  # pragma: allowlist secret
        ):
            runningUser = getpass.getuser()
            if runningUser in (username, "root"):
                if pwd.getpwnam(username):
                    import pam

                    # Two APIs??
                    try:
                        p = pam.authenticate()  # type: ignore
                    except Exception:
                        p = pam
                    if p.authenticate(username, password):
                        with lock:
                            if not Users[username].token:
                                assignNewToken(username)
                            x = Users[username].token
                            assert x
                            return x

            return "failure"

    except ImportError:
        logger.error("Could not import PAM")
        return "failure"

    except KeyError:
        pass

    with lock:
        if username in Users and ("password" in Users[username]):
            if Users[username].get("algorithm", "sha256") == "sha256":
                m = hashlib.sha256()
                m.update(usr_bytes(password, "utf8"))
                m.update(
                    base64.b64decode(Users[username]["salt"].encode("utf8"))
                )
                m = m.digest()
                if hmac.compare_digest(
                    base64.b64decode(
                        Users[username]["password"].encode("utf8")
                    ),
                    m,
                ):
                    # We can't just always assign a new token because that would break multiple
                    # Logins as same user
                    if not Users[username].token:
                        assignNewToken(username)
                    x = Users[username].token
                    assert x
                    return x
            else:
                ph = PasswordHasher()
                if ph.verify(Users[username]["password"], password):
                    # We can't just always assign a new token because that would break multiple
                    # Logins as same user
                    if not Users[username].token:
                        assignNewToken(username)
                    x = Users[username].token
                    assert x
                    return x
        return "failure"


def checkTokenPermission(token, permission) -> bool:
    """return true if the user associated with token has the permission"""
    global tokenHashes

    with lock:
        token = hashToken(token)
        if token in tokenHashes:
            if permission in tokenHashes[token].permissions:
                return True
            else:
                if "__all_permissions__" in tokenHashes[token].permissions:
                    return True
                else:
                    return False
        else:
            return False


def dumpDatabase() -> bool:
    """Save the state of the users and groups to a file."""
    with lock:
        global authchanged
        if not authchanged:
            return False
        x = Users.copy()
        for i in x:
            # Don't save the login history.
            if "loginhistory" in x[i]:
                del x[i]["loginhistory"]
        # Assemble the users and groups data and save it back where we found it
        temp = {"users": x, "groups": Groups.copy()}

        p = os.path.join(directories.usersdir, "data")

        os.makedirs(p, exist_ok=True)
        util.chmod_private_try(p)
        with open(os.path.join(p, "users.json~"), "w") as f:
            util.chmod_private_try(
                os.path.join(p, "users.json~"), execute=False
            )
            # pretty print
            json.dump(temp, f, sort_keys=True, indent=4, separators=(",", ": "))

        shutil.move(
            os.path.join(p, "users.json~"), os.path.join(p, "users.json")
        )

        authchanged = False
        return True


def setGroupLimit(group, limit, val) -> None:
    with lock:
        global authchanged
        authchanged = True
        if val == 0:
            try:
                Groups[group].get("limits", {}).pop(limit)
            except Exception:
                pass
        else:
            # TODO unlikely race condition here
            gr = Groups[group]
            if "limits" not in gr:
                gr["limits"] = {}
            gr["limits"][limit] = val

        dumpDatabase()


def addGroupPermission(group: str, permission: str) -> None:
    """Add a permission to a group"""
    with lock:
        global authchanged
        authchanged = True
        if permission not in Groups[group]["permissions"]:
            Groups[group]["permissions"].append(permission)
        dumpDatabase()


def removeGroupPermission(group, permission) -> None:
    global authchanged
    with lock:
        authchanged = True
        Groups[group]["permissions"].remove(permission)
        dumpDatabase()


# This is a salt for the token hint. The idea being that we look
# up the tokens by hashing them, not by actually looking them up.
# The attacker has no information about the token hashes or the token secret,
# so it should be safe to compare them and look them in dicts.
# due to them being completely secret and random.

# You don't get useful information from timing attacks because the remote node doesn't know the tokenHashSecret

# TODO: Someone who knows more about crypto should look this over.


def whoHasToken(token: str) -> str:
    global tokenHashes
    return tokenHashes[hashToken(token)]["username"]


tokenHashSecret = os.urandom(24)


def hashToken(token: str) -> bytes:
    return hashlib.sha256(usr_bytes(token, "utf8") + tokenHashSecret).digest()


def assignNewToken(user: str) -> None:
    """Log user out by defining a new token"""
    global tokenHashes
    with lock:
        # Generate new token
        x = base64.b64encode(os.urandom(24)).decode()
        # Get the old token, delete it, and assign a new one
        oldtoken = Users[user].token

        if oldtoken:
            del Tokens[oldtoken]

            try:
                del tokenHashes[hashToken(oldtoken)]
            except KeyError:
                # Not there?
                pass

        Users[user].token = x
        Tokens[x] = Users[user]
        tokenHashes[hashToken(x)] = Users[user]


class UnsetSettingException:
    pass


def setUserSetting(user, setting, value) -> None:
    with lock:
        global authchanged
        authchanged = True
        un = user
        if user == "__guest__":
            return
        user = Users[user]
        # This line is just there to raise an error on bad data.
        json.dumps(value)
        if "settings" not in user:
            user["settings"] = {}

        Users[un]["settings"][setting] = value
        dumpDatabase()


def getUserSetting(username: str, setting: str) -> Any:
    # I suppose this doesnt need a lock?
    if username == "__guest__":
        return defaultusersettings[setting]
    if username == "__no_request__":
        return defaultusersettings[setting]

    user = Users[username]
    if "settings" not in user:
        return defaultusersettings[setting]

    if setting in user["settings"]:
        return user["settings"][setting]
    else:
        return defaultusersettings[setting]


def getUserLimit(
    user: str, limit: str, maximum: int | float = 2**64
) -> float | int:
    """Return the user's limit for any limit category, or 0 if not set.
    Limit to maximum.
    If user has __all_permissions__, limit _is_ maximum.
    """
    if "__guest__" in Users:
        guestlimit = min(Users["__guest__"].limits.get(limit, 0), maximum)
    else:
        guestlimit = 0

    if user in Users:
        if "__all_permissions__" not in Users[user].permissions:
            val = max(
                min(Users[user].limits.get(limit, 0), maximum), guestlimit
            )
        else:
            val = maximum
        return min(val, maximum)
    else:
        if user == "__no_request__":
            return maximum
        return guestlimit
    return 0


def canUserDoThis(user: str, permission: str) -> bool:
    """Return True if given user(by username) has access to the given permission"""

    if permission == "__never__":
        return False

    if user == "__admin__":
        return True

    if permission == "__guest__":
        return True
    if user not in Users:
        if (
            "__guest__" in Users
            and permission in Users["__guest__"].permissions
        ):
            return True
        else:
            if (
                "__guest__" in Users
                and "__all_permissions__" in Users["__guest__"].permissions
            ):
                return True

        return False

    if permission in Users[user].permissions:
        return True

    if "__all_permissions__" in Users[user].permissions:
        return True

    if (
        "__guest__" in Users
        and "__all_permissions__" in Users["__guest__"].permissions
    ):
        return True

    if (
        "__guest__" in Users
        and "__all_permissions__" in Users["__guest__"].permissions
    ):
        return True

    return False
