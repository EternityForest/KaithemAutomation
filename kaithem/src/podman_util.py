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
- Helpers for listing, tagging, pulling, removing, pruning, exporting, and
  loading images back these tasks in the podman manager UI.
- Only rootless podman is supported (running as a normal user).
"""

import json
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
from kaithem.src import alerts

logger = structlog.get_logger(__name__)

CONTAINER_PREFIX = "kaithem-temp-"
CLEANUP_INTERVAL = 60 * 60
CLEANUP_MAX_AGE = 60 * 60 * 24 * 365

# Anything older than this is considered stale by ``prune``.  One week.
PRUNE_MAX_AGE = "168h"

v = os.path.expandvars("$HOME/.local/share/kaithem-containers/")

# Scratch space for image archives.  Deliberately on disk (not the vardir,
# which may be tmpfs) because exported images can be large.
IMAGE_TMP_DIR = os.path.join(v, "tmp")

try:
    os.makedirs(os.path.join(v, "podman", "conf"), exist_ok=True)
    os.makedirs(os.path.join(v, "podman", "storage"), exist_ok=True)
    os.makedirs(IMAGE_TMP_DIR, exist_ok=True)

    if not os.path.exists(os.path.join(v, "podman", "conf", "registries.conf")):
        with open(
            os.path.join(v, "podman", "conf", "registries.conf"), "w"
        ) as f:
            f.write("unqualified-search-registries = ['docker.io']\n")

    if not os.path.exists(os.path.join(v, "podman", "conf", "storage.conf")):
        with open(os.path.join(v, "podman", "conf", "storage.conf"), "w") as f:
            f.write(
                "[storage]\n"
                'rootless_storage_path = "$KAITHEM_PODMAN_STORAGE"\n'
                'driver = "overlay"\n'
                "[storage.options.pull_options]\n"
                'use_hard_links="true"\n'
                'enable_partial_images="true"\n'
            )

except Exception:
    logger.exception("Failed to create dir for podman_util")


env_extras = {
    "CONTAINERS_REGISTRIES_CONF": os.path.join(
        v, "podman", "conf", "registries.conf"
    ),
    "KAITHEM_PODMAN_STORAGE": os.path.join(v, "podman", "storage"),
    "CONTAINERS_STORAGE_CONF": os.path.join(
        v, "podman", "conf", "storage.conf"
    ),
}


def resolve_image_name(image: str):
    if ":" not in image:
        return f"{image}:latest"
    return image


def _podman(*args: str) -> list[str]:
    podman = shutil.which("podman")
    if not podman:
        raise RuntimeError("podman not found")
    return [podman, *args]


def _podman_run(
    *args: str, env: dict[str, str] | None = None, **kwargs: Any
) -> subprocess.Popen[bytes]:
    return subprocess.Popen[bytes](
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
    image = resolve_image_name(image)
    r = _podman_run("image", "exists", image)
    r.communicate()
    return r.returncode == 0


def _pull_image(image: str) -> None:
    """Pull the image if missing, raising an info alert while downloading."""
    image = resolve_image_name(image)

    alert = alerts.Alert(
        f"podman_pull_{image}",
        priority="info",
        description=f"Pulling image {image}",
        trip_delay=1,
    )
    alert.trip()

    try:
        _podman_quick_run("pull", image)
    except Exception:
        _alert(f"podman_pull_{image}", "error", traceback.format_exc())
        raise RuntimeError(f"Failed to pull image {image}")
    else:
        alert.clear()


def list_images() -> list[dict[str, Any]]:
    """Return local images grouped by image ID.

    Podman prints one row per tag and repeats the image's full tag list in
    every row, so rows are grouped by ID and their names unioned.

    Each entry is ``{"id", "names", "size", "created"}``.
    """
    out = _podman_quick_run("images", "--format", "json")
    try:
        raw = json.loads(out)
    except ValueError as e:
        raise RuntimeError(f"Could not parse podman image list: {e}")

    images: dict[str, dict[str, Any]] = {}
    for row in raw:
        image_id = row.get("Id")
        if not image_id:
            continue
        entry = images.setdefault(
            image_id,
            {
                "id": image_id,
                "names": [],
                "size": row.get("Size", 0),
                "created": row.get("Created", 0),
            },
        )
        for name in row.get("Names") or []:
            if name not in entry["names"]:
                entry["names"].append(name)
    return list(images.values())


def image_architecture(image: str) -> str:
    """Return the architecture (e.g. ``amd64``) of a local image."""
    if not image:
        raise ValueError("Image must be provided")
    out = _podman_quick_run(
        "image", "inspect", "--format", "{{.Architecture}}", image
    )
    return out.strip()


def add_image_tag(image: str, new_tag: str) -> None:
    """Add another tag pointing at an existing local image."""
    if not image:
        raise ValueError("Image must be provided")
    if not new_tag:
        raise ValueError("New tag must be provided")
    _podman_quick_run("tag", image, new_tag)


def pull_image(image: str) -> None:
    """Pull the latest version of an image by tag, showing a progress alert."""
    if not image:
        raise ValueError("Image must be provided")
    _pull_image(image)


def prune(max_age: str = PRUNE_MAX_AGE) -> dict[str, str]:
    """Remove stopped containers and unused images older than ``max_age``.

    ``max_age`` is a podman duration such as ``"168h"`` (one week).  Running
    containers are never pruned.  Returns the podman output for each step.
    """
    return {
        "containers": _podman_quick_run(
            "container", "prune", "--force", "--filter", f"until={max_age}"
        ),
        "images": _podman_quick_run(
            "image", "prune", "--all", "--force", "--filter", f"until={max_age}"
        ),
    }


def export_image(image: str, path: str) -> None:
    """Write ``image`` to ``path`` as an OCI archive with zstd:chunked layers.

    The image's reference is preserved inside the archive so ``load_image``
    can restore the tag.
    """
    if not image:
        raise ValueError("Image must be provided")
    if not path:
        raise ValueError("Destination path must be provided")
    _podman_quick_run(
        "push",
        "--compression-format",
        "zstd:chunked",
        f"containers-storage:{image}",
        f"oci-archive:{path}:{image}",
    )


def load_image(path: str) -> str:
    """Load an image from an archive produced by :func:`export_image`."""
    if not path:
        raise ValueError("Archive path must be provided")
    return _podman_quick_run("load", "-i", path)


def remove_image(image: str) -> str:
    """Remove a local image by reference (tag or ID).

    If the image still has other tags, only the given reference is removed
    and the underlying image is kept; it is deleted once its last tag goes
    away.  Podman refuses to remove an image in use by a container.
    """
    if not image:
        raise ValueError("Image must be provided")
    return _podman_quick_run("rmi", image)


def _container_name(name: str) -> str:
    return f"{CONTAINER_PREFIX}{name}"


# Containers this process started.  Attached runs keep a Popen handle so we
# can wait on them; detached runs only keep the name.  Either way, stopping
# means removing the container by name, because signalling the ``podman run``
# client is not reliable.
_running: dict[str, subprocess.Popen[bytes]] = {}
_running_names: set[str] = set()
_running_lock = threading.RLock()


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
    publish: list[tuple[int, int]] | None = None,
    track: bool = False,
) -> subprocess.Popen[bytes] | None:
    """Start a container with the settings and bindings you pass to it.

    bindings: dict of host_path -> container_path
    publish: list of (host_port, container_port) pairs
    detach: run in the background and return None
    track: remember a detached container so ``stop_container`` can stop it.
        Attached containers are always tracked.

    Returns a Popen handle if not detached, else None.
    """

    image = resolve_image_name(image)
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
        "--replace",
        "--detach" if detach else "--interactive",
        "--workdir",
        workdir,
    )
    for host, ctr in (bindings or {}).items():
        cmd += ["--mount", f"type=bind,src={host},dst={ctr}"]
    for host_port, ctr_port in publish or []:
        cmd += ["--publish", f"{host_port}:{ctr_port}"]
    for k, v in (env or {}).items():
        cmd += ["--env", f"{k}={v}"]
    cmd += [image]
    if args:
        cmd += args

    try:
        p = subprocess.Popen(
            cmd,
            env={**os.environ, **env_extras},
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

    if not detach or track:
        # Track the running container so it can be shut off at exit.
        with _running_lock:
            _running_names.add(name)
            if not detach:
                _running[name] = p
    return p


def container_exists(name: str) -> bool:
    """Return whether a container with this name exists (any state)."""
    r = _podman_run("container", "exists", _container_name(name))
    r.communicate()
    return r.returncode == 0


def container_status(name: str) -> str:
    """Return podman's status string (e.g. ``running``), or ``missing``."""
    try:
        out = _podman_quick_run(
            "container",
            "inspect",
            "--format",
            "{{.State.Status}}",
            _container_name(name),
        )
    except Exception:
        return "missing"
    return out.strip()


def container_logs(name: str, follow: bool = False) -> subprocess.Popen[bytes]:
    """Return a Popen streaming a container's logs (stdout+stderr merged)."""
    cmd = _podman("logs", _container_name(name))
    if follow:
        cmd.append("--follow")
    return subprocess.Popen(
        cmd,
        env={**os.environ, **env_extras},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def remove_container(name: str) -> None:
    """Remove a container by name.  Missing containers are ignored."""
    try:
        _podman_quick_run("rm", "--force", _container_name(name))
    except Exception:
        logger.debug("Container %s not present", name)
    with _running_lock:
        _running.pop(name, None)
        _running_names.discard(name)


def stop_container(name: str) -> None:
    with _running_lock:
        p = _running.pop(name, None)
        _running_names.discard(name)

    # Signalling the ``podman run`` client does not reliably stop the
    # container it started, so remove the container itself; the attached
    # client then exits on its own.  A container started in a previous
    # process has no handle here but still needs removing, so always try.
    try:
        _podman_quick_run("rm", "--force", _container_name(name))
    except Exception:
        if p is not None:
            logger.exception("Failed to remove container %s", name)
            p.terminate()

    if p is not None:
        try:
            p.wait(timeout=10)
        except Exception:
            logger.exception("Failed to stop container %s", name)
            try:
                p.kill()
            except Exception:
                pass


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
                    "{{.Created.Unix}}",
                    line,
                )

                created = int(inspect.strip())
                if time.time() - created > CLEANUP_MAX_AGE:
                    _podman_quick_run("rm", "--force", line)

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
        names = set(_running) | set(_running_names)
    for name in names:
        stop_container(name)
