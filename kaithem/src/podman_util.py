# SPDX-License-Identifier: GPL-3.0-or-later
"""Rootless podman wrapper.

Runs containers as a normal user. You pass the settings and bindings;
this module handles image pulling, failure alerts, and container cleanup.

- Images are pulled automatically if missing. While downloading, an info
  priority alert tells us. Failures raise alerts.
- Bindings are checked to exist before starting. Bindings are made
  writable via overlayfs so they work rootless.
- Containers are named with a ``kaithem-temp-`` prefix.
- Every hour (starting an hour after the system loads), any container with
  that prefix that hasn't been touched in a year is deleted.
- Images are never auto-pruned.
- Containers get stdin and stdout exposed as pipes.
- Containers registered with this module are shut off at exit via the
  kaithem.api lifespan hook.
- Only rootless podman is supported (running as a normal user).
"""

import os
import shutil
import subprocess
import threading
import time
import traceback
from typing import Any, BinaryIO

import structlog
from scullery import messagebus

from kaithem.api.lifespan import at_shutdown
from kaithem.api.util import get_vardir
from kaithem.src import alerts

logger = structlog.get_logger(__name__)

CONTAINER_PREFIX = "kaithem-temp-"
CLEANUP_INTERVAL = 60 * 60
CLEANUP_MAX_AGE = 60 * 60 * 24 * 365


try:
    v = os.path.expandvars("$HOME/.local/share/kaithem-containers/")
    os.makedirs(os.path.join(v, "podman", "conf"), exist_ok=True)
    os.makedirs(os.path.join(v, "podman", "graph"), exist_ok=True)
    os.makedirs(os.path.join(v, "podman", "containers"), exist_ok=True)

    if not os.path.exists(os.path.join(v, "podman", "conf", "registries.conf")):
        with open(
            os.path.join(v, "podman", "conf", "registries.conf"), "w"
        ) as f:
            f.write("unqualified-search-registries = ['docker.io']\n")

    if not os.path.exists(os.path.join(v, "podman", "conf", "storage.conf")):
        with open(os.path.join(v, "podman", "conf", "storage.conf"), "w") as f:
            f.write(
                "[storage]\n"
                'graphroot = "$KAITHEM_PODMAN_GRAPH"\n'
                'runroot = "$KAITHEM_PODMAN_RUN"\n'
                'driver = "overlay"\n'
                '[storage.options.pull_options]\n"'
                'use_hard_links="true"\n'
                'enable_partial_images="true"\n'
            )

except Exception:
    logger.exception("Failed to create dir for podman_util")


env_extras = {
    "CONTAINERS_REGISTRIES_CONF": os.path.join(
        get_vardir(), "podman", "conf", "registries.conf"
    ),
    "KAITHEM_PODMAN_GRAPH": os.path.join(get_vardir(), "podman", "graph"),
    "KAITHEM_PODMAN_RUN": os.path.join(get_vardir(), "podman", "containers"),
    "CONTAINERS_STORAGE_CONF": os.path.join(
        get_vardir(), "podman", "conf", "storage.conf"
    ),
}


def _podman(*args: str) -> list[str]:
    podman = shutil.which("podman")
    if not podman:
        raise RuntimeError("podman not found")
    return [podman, *args]


def _podman_run(
    *args: str, env: dict[str, str] | None = None, **kwargs: Any
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        _podman(*args),
        env={**os.environ, **env_extras, **(env or {})},
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,
    )


def _podman_quick_run(*args: str) -> str:
    p = _podman_run(*args)
    o, e = p.communicate()
    if not p.returncode == 0:
        raise RuntimeError(e[-1024:].decode("utf-8", errors="ignore"))

    return o.decode()


def _alert(name: str, priority: str, description: str) -> None:
    """Raise an alert with the given priority."""
    try:
        messagebus.post_message(
            "/system/notifications/errors",
            f"Podman alert: {description}",
        )
    except Exception:
        logger.exception("Failed to raise alert")


def _image_exists(image: str) -> bool:
    r = _podman_run("image", "exists", image)
    return r.returncode == 0


def _pull_image(image: str) -> None:
    """Pull the image if missing, raising an info alert while downloading."""
    if _image_exists(image):
        return

    alert = alerts.Alert(
        f"podman_pull_{image}",
        priority="info",
        description=f"Pulling image {image}",
    )
    alert.trip()

    try:
        _podman_quick_run("pull", image)
    except Exception:
        _alert(f"podman_pull_{image}", "error", traceback.format_exc())
        raise RuntimeError(f"Failed to pull image {image}")
    else:
        alert.clear()


def _container_name(name: str) -> str:
    return f"{CONTAINER_PREFIX}{name}"


def run_container(
    image: str,
    name: str,
    bindings: dict[str, str] | None = None,
    env: dict[str, str] | None = None,
    workdir: str = "/",
    stdin: BinaryIO | int | None = None,
    stdout: BinaryIO | int | None = None,
    stderr: BinaryIO | int | None = None,
    args: list[str] | None = None,
    detach: bool = False,
) -> subprocess.Popen[bytes] | None:
    """Start a container with the settings and bindings you pass to it.

    bindings: dict of host_path -> container_path
    Returns a Popen handle if not detached, else None.
    """

    if bindings:
        for host in bindings:
            if not os.path.exists(host):
                _alert(
                    f"podman_bind_{host}",
                    "error",
                    f"Binding path {host} does not exist",
                )
                raise RuntimeError(f"Binding path {host} does not exist")

    cmd = _podman(
        "run",
        "--name",
        _container_name(name),
        "--storage-driver=overlay",
        "--rm",
        "--detach" if detach else "--interactive",
        "--workdir",
        workdir,
    )
    for host, ctr in (bindings or {}).items():
        cmd += ["--mount", f"type=bind,src={host},dst={ctr}"]
    for k, v in (env or {}).items():
        cmd += ["--env", f"{k}={v}"]
    cmd += [image]
    if args:
        cmd += args

    try:
        p = subprocess.Popen(
            cmd,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
        )
    except Exception:
        logger.exception("Failed to start container %s", name)
        _alert(
            f"podman_run_{name}",
            "error",
            f"Failed to start container {name}",
        )
        raise

    if not detach:
        # Track the running container so it can be shut off at exit.
        with _running_lock:
            _running[name] = p
    return p


_running: dict[str, subprocess.Popen[bytes]] = {}
_running_lock = threading.RLock()


def stop_container(name: str) -> None:
    with _running_lock:
        p = _running.pop(name, None)
    if p is not None:
        try:
            p.terminate()
            p.wait(timeout=10)
        except Exception:
            logger.exception("Failed to stop container %s, retrying", name)
            _podman_run("kill", _container_name(name))


def _cleanup() -> None:
    """Delete containers with our prefix that haven't been touched in a year."""
    try:
        r = _podman_quick_run(
            "ps",
            "-a",
            "--filter",
            f"name={CONTAINER_PREFIX}",
            "--format",
            "{{.Names}}",
        )

        for line in r.splitlines():
            line = line.strip()
            if not line.startswith(CONTAINER_PREFIX):
                continue
            try:
                inspect = _podman_quick_run(
                    "container",
                    "inspect",
                    "--format",
                    "{{.Created}}",
                    line,
                )

                created = inspect.strip()
                if (
                    time.time() - time.mktime(time.strptime(created))
                    > CLEANUP_MAX_AGE
                ):
                    _podman_run("rm", "-f", line)

            except Exception:
                logger.exception("Cleanup error")

    except Exception:
        logger.exception("Failed to cleanup podman containers")


def _cleanup_loop() -> None:
    # Start an hour after the system loads.
    time.sleep(60 * 60)
    while True:
        try:
            _cleanup()
        except Exception:
            logger.exception("Failed to cleanup podman containers")
        time.sleep(CLEANUP_INTERVAL)


threading.Thread(
    target=_cleanup_loop, daemon=True, name="podman_cleanup"
).start()


@at_shutdown
def _shutdown() -> None:
    with _running_lock:
        for name in list(_running):
            stop_container(name)
