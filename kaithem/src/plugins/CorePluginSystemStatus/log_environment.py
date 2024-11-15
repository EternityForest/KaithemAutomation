"""Logs changes in the environment such as package versions"""

import difflib
import os
import subprocess
import time

import structlog
import yaml

from kaithem.api.util import get_logdir

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


def which(p) -> bool:
    return (
        subprocess.run(["which", p], stdout=subprocess.DEVNULL).returncode == 0
    )


def list_deb_packages():
    if which("apt"):
        r: str = subprocess.check_output(
            ["apt", "list", "--installed"], stderr=subprocess.DEVNULL
        ).decode()
        r2: list[str] = [i.strip() for i in r.split("\n")]

        return r2

    return []


def get_important_envars():
    return {i: os.environ[i] for i in important_envars if i in os.environ}


def list_usb_devices():
    if which("lsusb"):
        r: str = subprocess.check_output(
            ["lsusb"], stderr=subprocess.DEVNULL
        ).decode()
        r2: list[str] = [i.strip() for i in r.split("\n")]
        r2 = [i for i in r2 if i]

        return r2

    return []


def list_rpm_packages():
    if which("rpm"):
        r: str = subprocess.check_output(
            ["rpm", "-qa"], stderr=subprocess.DEVNULL
        ).decode()
        r2: list[str] = [i.strip() for i in r.split("\n")]

        return r2

    return []


def get_pip_freeze_versions():
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


def build_environment():
    e = {}

    e["env-vars"] = get_important_envars()

    e["pip-versions"] = get_pip_freeze_versions()

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
        e["os-release"] = {}
        with open("/etc/os-release") as f:
            for i in f.readlines():
                k, v = i.strip().split("=")
                e["os-release"][k] = v

    return e


def go():
    current_env = yaml.dump(build_environment(), sort_keys=True)

    ld = get_logdir()
    snapshot_fn = os.path.join(ld, "environment-snapshot.yaml")
    log_fn = os.path.join(ld, "environment.log")

    old = ""
    if os.path.exists(snapshot_fn):
        with open(snapshot_fn) as f:
            old = f.read()

    old_log = ""
    if os.path.exists(log_fn):
        with open(log_fn) as f:
            old_log = f.read()

    if len(old_log) > 10000000:
        old_log = old_log[-5000000:]
        with open(log_fn, "w") as f:
            f.write(old_log)

    if old != current_env:
        diff = list(
            difflib.unified_diff(
                old.split("\n"),
                current_env.split("\n"),
                fromfile="old",
                tofile="new",
            )
        )

        with open(snapshot_fn, "w") as f:
            f.write(current_env)

        if old:
            with open(log_fn, "a") as f:
                f.write("\n\n")
                f.write("Date: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                f.write("\n".join(diff))
