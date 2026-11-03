"""Logs changes in the environment such as package versions"""

import os
import subprocess
import sys
import time
from typing import Any

import jsonpatch
import structlog
import yaml

from kaithem.api.util import bip39_hash, get_logdir

from . import code_hash

logger = structlog.get_logger(__name__)

important_envars = [
    "PATH",
    "PYTHONPATH",
    "LD_LIBRARY_PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_NUMERIC",
    "LC_TIME",
    "LC_MONETARY",
    "LC_COLLATE",
    "LC_MESSAGES",
    "DESKTOP_SESSION",
    "XDG_CURRENT_DESKTOP",
    "DISPLAY",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
    "XDG_CONFIG_DIRS",
    "SHELL",
    "XDG_DATA_DIRS",
]


def which(p: str) -> bool:
    return (
        subprocess.run(["which", p], stdout=subprocess.DEVNULL).returncode == 0
    )


def list_deb_packages() -> list[str]:
    if which("apt"):
        r: str = subprocess.check_output(
            ["apt", "list", "--installed"], stderr=subprocess.DEVNULL
        ).decode()
        r2: list[str] = [i.strip() for i in r.split("\n")]

        return r2

    return []


def get_important_envars() -> dict[str, str]:
    return {i: os.environ[i] for i in important_envars if i in os.environ}


def list_usb_devices() -> list[str]:
    if which("lsusb"):
        r: str = subprocess.check_output(
            ["lsusb"], stderr=subprocess.DEVNULL
        ).decode()
        r2: list[str] = [i.strip() for i in r.split("\n")]
        r2 = [i for i in r2 if i]

        return r2

    return []


def list_rpm_packages() -> list[str]:
    if which("rpm"):
        r: str = subprocess.check_output(
            ["rpm", "-qa"], stderr=subprocess.DEVNULL
        ).decode()
        r2: list[str] = [i.strip() for i in r.split("\n")]

        return r2

    return []


def scan_py_path() -> dict[str, str]:
    op = {}
    for i in sys.path:
        if not i:
            continue
        if not os.path.exists(i):
            continue
        if not os.path.isdir(i):
            continue
        op[i] = bip39_hash(
            code_hash.hash_dir(i, i).hexdigest(), num_words=6, separator="-"
        )
    return op


def get_pip_freeze_versions() -> dict[str, str]:
    try:
        if which("uv"):
            r: str = subprocess.check_output(
                ["uv", "pip", "freeze"], stderr=subprocess.DEVNULL
            ).decode()
            r2: list[str] = [i.strip() for i in r.split("\n")]

            versions = {}
            for i in r2:
                if not i:
                    continue
                try:
                    k, v = i.split("==")
                    versions[k] = v
                except ValueError:
                    pass

            return versions

    except Exception:
        pass

    if which("pip"):
        r: str = subprocess.check_output(
            ["pip", "freeze"], stderr=subprocess.DEVNULL
        ).decode()
        r2: list[str] = [i.strip() for i in r.split("\n")]

        versions = {}
        for i in r2:
            if not i:
                continue
            try:
                k, v = i.split("==")
                versions[k] = v
            except ValueError:
                pass

        return versions

    return {}


def build_environment():
    e: dict[str, Any] = {}

    e["app-code-hash"] = bip39_hash(
        code_hash.get_code_hash(), num_words=6, separator="-"
    )
    e["env-vars"] = get_important_envars()

    e["pip-versions"] = get_pip_freeze_versions()

    e["python-path-dirs-state"] = scan_py_path()

    d = list_deb_packages()
    if d:
        e["apt-packages"] = d

    # Untested, ai generated and manually reviewed
    try:
        d = list_rpm_packages()
        if d:
            e["rpm-packages"] = d
    except Exception:
        logger.exception("Failed to list rpm packages")

    d = list_usb_devices()
    if d:
        e["usb-devices"] = d

    if os.path.exists("/etc/os-release"):
        osrelease: dict[str, str] = {}
        with open("/etc/os-release") as f:
            for i in f:
                k, v = i.strip().split("=")
                osrelease[k] = v
        e["os-release"] = osrelease

    return e


def go():
    current_env = build_environment()

    ld = get_logdir()
    snapshot_fn = os.path.join(ld, "environment-snapshot.yaml")
    log_fn = os.path.join(ld, "environment.log")

    old = ""
    if os.path.exists(snapshot_fn):
        with open(snapshot_fn) as f:
            try:
                old = yaml.load(f.read(), Loader=yaml.SafeLoader)
            except Exception:
                logger.exception("Failed to read environment snapshot")

    old_log = ""
    if os.path.exists(log_fn):
        with open(log_fn) as f:
            old_log = f.read()

    if len(old_log) > 10000000:
        old_log = old_log[-5000000:]
        with open(log_fn, "w") as f:
            f.write(old_log)

    if old != current_env:
        diff = jsonpatch.make_patch(old, current_env)
        if diff:
            with open(snapshot_fn, "w") as f:
                f.write(yaml.dump(current_env, sort_keys=False))

            if old:
                with open(log_fn, "a") as f:
                    f.write(
                        "Date: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n"
                    )
                    f.write(diff.to_string())
                    f.write("\n\n")
