# SPDX-License-Identifier: GPL-3.0-or-later
"""Bun/Node container runtime.

Runs a plain ``package.json`` project as a rootless podman container using
a stock Bun image (``oven/bun:1.4.4-slim`` by default).  The project must
stay a completely normal, standalone runnable project: all build output
lands back in the project folder and the only special bit Kaithem adds is
a portable ``node_modules`` symlink and a shared package cache mount.
"""

from __future__ import annotations

import json
import os
import platform
import shutil

import structlog

from kaithem.api.util import get_vardir
from kaithem.src import podman_util

from .runtime import ContainerProjectRuntime

logger = structlog.get_logger(__name__)

#: Default image used for both building and running.
DEFAULT_IMAGE = "oven/bun:1.4.4-slim"

#: Path inside the container where the shared Bun cache is mounted.
CACHE_MOUNT = "/bun-cache"

#: Default TCP port dev mode publishes.
DEFAULT_DEV_PORT = 8790

# Container images are always Linux, so ``node_modules`` only needs to
# vary by architecture to stay portable between machines.
CONTAINER_OS = "linux"

_MACHINE_ALIASES = {
    "x86_64": "amd64",
    "x64": "amd64",
    "aarch64": "arm64",
    "armv7l": "arm",
}


def _normalize_arch(arch: str) -> str:
    arch = (arch or "").strip().lower()
    return _MACHINE_ALIASES.get(arch, arch)


def node_modules_directory_name(architecture: str) -> str:
    """Return the portable ``node_modules_<os>_<arch>`` directory name."""
    return f"node_modules_{CONTAINER_OS}_{_normalize_arch(architecture)}"


class NodeRuntime(ContainerProjectRuntime):
    """Run a ``package.json`` project with Bun."""

    def __init__(
        self,
        project_folder: str,
        data_dir: str,
        run_image: str = DEFAULT_IMAGE,
        build_image: str = DEFAULT_IMAGE,
        build_command: str | None = None,
        start_command: str | None = None,
        dev_command: str | None = None,
        dev_port: int = DEFAULT_DEV_PORT,
    ):
        super().__init__(project_folder, data_dir)
        self._run_image = run_image or DEFAULT_IMAGE
        self._build_image = build_image or DEFAULT_IMAGE
        self._build_command = build_command or None
        self._start_command = start_command or None
        self._dev_command = dev_command or None
        self._dev_port = int(dev_port)
        if self._dev_port <= 0 or self._dev_port > 65535:
            raise ValueError(f"Invalid dev port {self._dev_port!r}")

    # -- Configuration --------------------------------------------------

    def get_run_image(self) -> str:
        return self._run_image

    def get_build_image(self) -> str:
        return self._build_image

    def dev_port(self) -> int:
        return self._dev_port

    def _architecture(self) -> str:
        """Architecture the project will run as, for the symlink name."""
        try:
            arch = podman_util.image_architecture(self._build_image)
            if arch:
                return arch
        except Exception:
            logger.debug(
                "Could not inspect architecture of %s",
                self._build_image,
                exc_info=True,
            )
        return platform.machine()

    def _package_json(self) -> dict:
        path = os.path.join(self.project_folder, "package.json")
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return {}
        except ValueError as exc:
            raise ValueError(f"Invalid package.json in {path}: {exc}") from exc
        if not isinstance(data, dict):
            return {}
        return data

    def _has_script(self, name: str) -> bool:
        scripts = self._package_json().get("scripts")
        return isinstance(scripts, dict) and name in scripts

    # -- Hooks ----------------------------------------------------------

    def environment(self) -> dict[str, str]:
        return {"BUN_INSTALL_CACHE_DIR": CACHE_MOUNT}

    def extra_bindings(self) -> dict[str, str]:
        cache_dir = os.path.join(get_vardir(), "cache", "bun")
        os.makedirs(cache_dir, exist_ok=True)
        return {cache_dir: CACHE_MOUNT}

    def build_steps(self) -> list[list[str]]:
        if self._build_command:
            return [["sh", "-c", self._build_command]]
        steps = [["bun", "install"]]
        if self._has_script("build"):
            steps.append(["bun", "run", "build"])
        return steps

    def run_args(self) -> list[str]:
        if self._start_command:
            return ["sh", "-c", self._start_command]
        return ["bun", "run", "start"]

    def dev_args(self) -> list[str]:
        if self._dev_command:
            return ["sh", "-c", self._dev_command]
        return ["bun", "run", "dev"]

    def prepare(self) -> None:
        """Force ``node_modules`` to be a portable architecture symlink.

        The project must stay portable across machines, so ``node_modules``
        is never a real directory; if it is one (or points somewhere
        unexpected) it is replaced with a symlink to
        ``node_modules_<os>_<arch>``.  The link target is created as an
        empty directory so package managers that resolve through the link
        (Bun, npm) do not fail on a dangling symlink.
        """
        modules = os.path.join(self.project_folder, "node_modules")
        target = node_modules_directory_name(self._architecture())
        target_path = os.path.join(self.project_folder, target)

        if os.path.islink(modules):
            if os.readlink(modules) != target:
                os.remove(modules)
                os.symlink(target, modules)
        else:
            if os.path.isdir(modules):
                self.on_message(
                    f"node_modules was a real directory; replacing it with "
                    f"a symlink to {target}"
                )
                _rmtree(modules)
            elif os.path.exists(modules):
                os.remove(modules)
            os.symlink(target, modules)

        os.makedirs(target_path, exist_ok=True)

    def is_built(self) -> bool:
        if self._read_build_marker() is None:
            return False
        modules = os.path.join(self.project_folder, "node_modules")
        return os.path.islink(modules)

    def build_artifacts(self) -> list[str]:
        artifacts = [
            self._marker_path(),
            os.path.join(self.project_folder, "node_modules"),
            os.path.join(self.project_folder, "dist"),
        ]
        for entry in os.listdir(self.project_folder):
            if entry.startswith("node_modules_"):
                artifacts.append(os.path.join(self.project_folder, entry))
        return artifacts


def _rmtree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
