# SPDX-License-Identifier: GPL-3.0-or-later
"""Container backed app runtimes.

A container app project describes itself with a ``container-app.toml``
file (see :mod:`appconfig`).  Each command it defines is ``podman exec``'d
into a long lived "keepalive" container, so running several commands in
turn reuses one container and its writable layer instead of paying to
create a fresh container every time.

A container is named from the owning resource id and the image it runs,
so a :class:`ContainerRuntime` that asks for the same image under the same
owner shares a container, and one that asks for a different image gets its
own.  Containers are only ever ``podman stop``ped, never recreated, so a
stop/start cycle is nearly free.

No custom images are ever built.  A build step and the run command may use
different stock images, and every build artifact lands back inside the
project folder, so a project stays a normal, standalone runnable project
and needs no platform specific data at runtime.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Final, Literal

import structlog

from kaithem.api.util import get_vardir
from kaithem.src import podman_util

from .appconfig import CommandApp, ContainerAppConfig, ScriptConfig, load_config

logger = structlog.get_logger(__name__)

#: The runtime status reported to the UI.
ContainerStatus = Literal["stopped", "loading", "running", "dev"]

_STATUS_VALUES: Final[tuple[ContainerStatus, ...]] = (
    "stopped",
    "loading",
    "running",
    "dev",
)

#: How many log lines to keep per runtime.
LOG_BUFFER_LINES: Final = 2000

#: Prefix for generated container names.  ``podman_util`` adds its own
#: ``kaithem-temp-`` prefix on top of this.
NAME_PREFIX: Final = "capp-"

#: Path, inside the container, where the app is expected to serve.
SERVER_SOCKET: Final = "/ipc/server.sock"

#: Seconds to wait before restarting an app command that exited.
RESTART_DELAY: Final = 2.0

#: PID 1 of a keepalive container.  Overriding the entrypoint means a
#: container is kept alive no matter what the image's default is.
KEEPALIVE_ENTRYPOINT: Final = "sleep"
KEEPALIVE_ARGS: Final = ["infinity"]

StatusCallback = Callable[[ContainerStatus], None]
LogCallback = Callable[[str], None]


def kaithem_local_address() -> str:
    """Return the ``http://127.0.0.1:<port>`` Kaithem itself serves on.

    Used as ``KAITHEM_ADDRESS``.  Apps only need it if they can reach the
    host directly (host networking or published ports).
    """
    # Imported lazily: ``config`` pulls in a lot and is not needed until a
    # runtime asks for its environment.
    from kaithem.src.config import config

    port = config.get("http_port", 8000)
    return f"http://127.0.0.1:{port}"


def _owner_digest(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode("utf-8")).hexdigest()


def container_name(owner_id: str, image: str) -> str:
    """Return the deterministic container name for an owner and image.

    The name is derived only from the owning resource id and the image, so
    every command that uses the same owner and image shares one container.
    """
    if not owner_id:
        raise ValueError("owner_id is required")
    if not image:
        raise ValueError("image is required")
    key = f"{owner_id}\n{podman_util.resolve_image_name(image)}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"{NAME_PREFIX}{digest[:12]}"


def runtime_dir(owner_id: str) -> str:
    """Return the per-owner scratch directory (holds the app's socket)."""
    return os.path.join(
        get_vardir(), "container_apps", _owner_digest(owner_id)[:12]
    )


def sandbox_dir(owner_id: str) -> str:
    """Return an ephemeral ``/data`` directory for the app's dev runtime.

    Dev runs are for experimenting, so they get a throwaway data folder
    under the vardir sandbox instead of the module's own data, and nothing
    they write can end up in a real instance's storage.
    """
    if not owner_id:
        raise ValueError("owner_id is required")
    return os.path.join(
        get_vardir(),
        "sandbox",
        "container_apps",
        _owner_digest(owner_id)[:12],
        "data",
    )


class ContainerSession:
    """One long lived container that commands are exec'd into.

    The container runs ``sleep infinity`` as PID 1 and every command is
    run with ``podman exec``.  The container is created once and then only
    ever stopped and started, so its writable layer survives a restart.
    """

    def __init__(
        self,
        owner_id: str,
        image: str,
        bindings: dict[str, str],
        workdir: str = "/app",
    ):
        self.owner_id = owner_id
        self.image = image
        self.name = container_name(owner_id, image)
        self.bindings = dict(bindings)
        self.workdir = workdir
        # Serialises create/start so two commands never race to make the
        # same container.
        self._lock = threading.RLock()

    def ensure_running(self) -> None:
        """Make sure the keepalive container is up, creating it if needed."""
        with self._lock:
            status = podman_util.container_status(self.name)
            if status == "running":
                return
            if status == "missing":
                self._create()
            else:
                podman_util.start_container(self.name)

    def _create(self) -> None:
        for host in self.bindings:
            os.makedirs(host, exist_ok=True)
        proc = podman_util.run_container(
            image=self.image,
            name=self.name,
            bindings=self.bindings,
            workdir=self.workdir,
            args=list(KEEPALIVE_ARGS),
            entrypoint=KEEPALIVE_ENTRYPOINT,
            detach=True,
            track=True,
            # Keep the container so a stop/start cycle is free.
            remove_on_exit=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc is not None
        # ``--detach`` makes podman print the id and exit, so this returns
        # quickly; reading it turns a launch failure into an exception
        # instead of a silently missing container.
        _out, err = proc.communicate(timeout=120)
        if proc.returncode != 0:
            detail = err.decode("utf-8", "replace").strip()
            raise RuntimeError(
                f"Failed to start container {self.name}: {detail}"
            )

    def exec(
        self,
        args: list[str],
        env: dict[str, str] | None = None,
        workdir: str | None = None,
        stdin: int | None = None,
        stdout: int | None = None,
        stderr: int | None = None,
        tty: bool = False,
    ) -> subprocess.Popen[bytes]:
        """Run a command in the container, starting it first if needed.

        ``tty`` allocates a pseudo terminal so the command line buffers
        its output instead of block buffering it; use it for commands
        whose output is streamed live.
        """
        if not args:
            raise ValueError("args is required")
        with self._lock:
            self.ensure_running()
        return podman_util.exec_container(
            self.name,
            args,
            env=env,
            workdir=workdir if workdir is not None else self.workdir,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            tty=tty,
        )

    def stop(self) -> None:
        """Stop the container, keeping it and its writable layer around."""
        with self._lock:
            podman_util.stop_keep(self.name)

    def remove(self) -> None:
        """Delete the container entirely."""
        with self._lock:
            podman_util.remove_container(self.name)

    def running(self) -> bool:
        return podman_util.container_running(self.name)


class ContainerRuntime:
    """Run one project folder as a container through ``podman_util``.

    ``project_folder`` becomes ``/app`` in every container and is where a
    build must put its output.  ``data_dir`` becomes ``/data`` and is the
    only persistent place the app is expected to write.

    ``base_path`` is the URL prefix the app is reachable at; it is passed
    to the container as ``BASE_PATH`` so the app can build its own links.
    """

    def __init__(
        self,
        owner_id: str,
        project_folder: str,
        data_dir: str,
        base_path: str,
    ):
        if not owner_id:
            raise ValueError("owner_id is required")
        if not project_folder:
            raise ValueError("project_folder is required")
        if not data_dir:
            raise ValueError("data_dir is required")
        if not base_path:
            raise ValueError("base_path is required")

        self.owner_id = owner_id
        self.project_folder = os.path.abspath(project_folder)
        self.config: ContainerAppConfig
        self.reload_config()

        self.data_dir = os.path.abspath(data_dir)
        self.base_path = base_path

        self._ipc_dir = os.path.join(runtime_dir(owner_id), "ipc")

        # Guards ``_status``, ``_error``, ``_app_proc``, ``_want_running``
        # and ``_dev``; separate from the session locks so a status read
        # never blocks on container I/O.
        self._state_lock = threading.RLock()
        self._status: ContainerStatus = "stopped"
        self._error: str | None = None
        self._want_running = False
        self._dev = False
        self._app_proc: subprocess.Popen[bytes] | None = None

        self._sessions: dict[str, ContainerSession] = {}
        self._session_lock = threading.Lock()
        self._build_lock = threading.Lock()
        self._action_lock = threading.Lock()

        self._log: deque[str] = deque(maxlen=LOG_BUFFER_LINES)
        self._log_callbacks: list[LogCallback] = []
        self._status_callbacks: list[StatusCallback] = []
        self._notify_lock = threading.Lock()

        #: Set by the owning resource so the app can call back into
        #: Kaithem.  Apps that never connect to the server ignore it.
        self.api_key: str | None = None

    # -- Introspection --------------------------------------------------

    @property
    def status(self) -> ContainerStatus:
        with self._state_lock:
            return self._status

    @property
    def error(self) -> str | None:
        with self._state_lock:
            return self._error

    @property
    def is_dev_mode(self) -> bool:
        with self._state_lock:
            return self._dev

    @property
    def supports_build(self) -> bool:
        """Whether the project defines a build command."""
        return self.config["build"] is not None

    @property
    def supports_run(self) -> bool:
        """Whether the app is a command run inside a container."""
        return self.config["app"]["kind"] == "command"

    @property
    def app_kind(self) -> str:
        return self.config["app"]["kind"]

    @property
    def build_image(self) -> str | None:
        build = self.config["build"]
        return build["image"] if build else None

    @property
    def run_image(self) -> str | None:
        app = self.config["app"]
        if app["kind"] == "command":
            return app["image"]
        return None

    @property
    def scripts(self) -> dict[str, ScriptConfig]:
        """Named commands the project exposes as runnable actions."""
        return self.config["scripts"]

    @property
    def ipc_dir(self) -> str:
        """Directory bound to ``/ipc``; holds the app's server socket."""
        return self._ipc_dir

    def unix_target(self) -> str:
        """Return the proxy target for the app's server socket."""
        return f"unix://{os.path.join(self._ipc_dir, 'server.sock')}"

    def static_source_dir(self) -> str:
        """Absolute path of the directory a static app is served from."""
        app = self.config["app"]
        if app["kind"] != "staticfiles":
            raise RuntimeError("This project is not a static file app")
        return os.path.join(self.project_folder, app["source"])

    def container_names(self) -> list[str]:
        with self._session_lock:
            return [session.name for session in self._sessions.values()]

    def get_environment(self) -> dict[str, str]:
        """Return the environment every command runs with."""
        env: dict[str, str] = {
            "SERVER_ADDRESS": SERVER_SOCKET,
            "BASE_PATH": self.base_path,
            "KAITHEM_ADDRESS": kaithem_local_address(),
        }
        if self.api_key:
            env["KAITHEM_API_KEY"] = self.api_key
        return env

    # -- Log plumbing ---------------------------------------------------

    def on_message(self, message: str) -> None:
        """Report a line of build or runtime output."""
        if not isinstance(message, str):
            raise TypeError("message must be a string")
        with self._notify_lock:
            self._log.append(message)
            callbacks = list(self._log_callbacks)
        for callback in callbacks:
            try:
                callback(message)
            except Exception:
                logger.exception("Container app log callback failed")

    def get_log(self) -> list[str]:
        """Return a copy of the buffered log lines."""
        with self._notify_lock:
            return list(self._log)

    def add_log_callback(self, callback: LogCallback) -> None:
        with self._notify_lock:
            self._log_callbacks.append(callback)

    def remove_log_callback(self, callback: LogCallback) -> None:
        with self._notify_lock:
            if callback in self._log_callbacks:
                self._log_callbacks.remove(callback)

    def add_status_callback(self, callback: StatusCallback) -> None:
        with self._notify_lock:
            self._status_callbacks.append(callback)

    def remove_status_callback(self, callback: StatusCallback) -> None:
        with self._notify_lock:
            if callback in self._status_callbacks:
                self._status_callbacks.remove(callback)

    def set_error_state(self, error: str | None) -> None:
        """Set or clear the error shown next to the app in the UI."""
        if error is not None and not isinstance(error, str):
            raise TypeError("error must be a string or None")
        with self._state_lock:
            self._error = error

    def _set_status(self, status: ContainerStatus) -> None:
        if status not in _STATUS_VALUES:
            raise ValueError(f"Invalid status {status!r}")
        with self._state_lock:
            if self._status == status:
                return
            self._status = status
        with self._notify_lock:
            callbacks = list(self._status_callbacks)
        for callback in callbacks:
            try:
                callback(status)
            except Exception:
                logger.exception("Container app status callback failed")

    # -- Build state ----------------------------------------------------

    def _marker_path(self) -> str:
        return os.path.join(self.project_folder, ".kaithem-build.json")

    def is_build_complete(self) -> bool:
        """Whether the build command (if any) has been run."""
        if self.config["build"] is None:
            return True
        return os.path.exists(self._marker_path())

    def is_built(self) -> bool:
        """Whether a usable build exists on disk."""
        if not self.is_build_complete():
            return False
        if self.config["app"]["kind"] == "staticfiles":
            return os.path.isdir(self.static_source_dir())
        return True

    def _write_build_marker(self) -> None:
        build = self.config["build"]
        data = {
            "build_image": build["image"] if build else None,
            "time": int(time.time()),
        }
        with open(self._marker_path(), "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def reload_config(self):
        self.config = load_config(self.project_folder)

    # -- Lifecycle ------------------------------------------------------

    def _prepare_dirs(self) -> None:
        os.makedirs(self.project_folder, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self._ipc_dir, exist_ok=True)

    def _bindings(self) -> dict[str, str]:
        return {
            self.project_folder: "/app",
            self.data_dir: "/data",
            self._ipc_dir: "/ipc",
        }

    def _session(self, image: str) -> ContainerSession:
        key = podman_util.resolve_image_name(image)
        with self._session_lock:
            session = self._sessions.get(key)
            if session is None:
                session = ContainerSession(
                    self.owner_id, image, self._bindings()
                )
                self._sessions[key] = session
            return session

    def start(self, dev: bool = False) -> None:
        """Run the app command inside a container.

        Does nothing but launch the command; it never builds.
        """
        app = self.config["app"]
        if app["kind"] != "command":
            raise RuntimeError("This project has no run command")

        with self._state_lock:
            self._want_running = True
            self._dev = dev
        self._set_status("loading")
        try:
            self._prepare_dirs()
            self._launch(app)
        except Exception as exc:
            with self._state_lock:
                self._want_running = False
            self.set_error_state(str(exc))
            self._set_status("stopped")
            raise
        self.set_error_state(None)

    def _launch(self, app: CommandApp) -> None:
        session = self._session(app["image"])
        proc = session.exec(
            list(app["command"]),
            env=self.get_environment(),
            workdir="/app",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            tty=True,
        )
        assert proc.stdout is not None
        with self._state_lock:
            self._app_proc = proc
            status: ContainerStatus = "dev" if self._dev else "running"
        self._set_status(status)
        threading.Thread(
            target=self._monitor,
            args=(proc,),
            daemon=True,
            name=f"capp-mon-{session.name}",
        ).start()

    def _monitor(self, proc: subprocess.Popen[bytes]) -> None:
        """Stream an app command's output and restart it if it dies."""
        stdout = proc.stdout
        assert stdout is not None
        for raw in stdout:
            self.on_message(raw.decode("utf-8", "replace").rstrip("\r\n"))
        code = proc.wait()

        with self._state_lock:
            if self._app_proc is not proc:
                # Superseded by a newer launch or an explicit stop.
                return
            self._app_proc = None
            want_running = self._want_running

        if not want_running:
            self._set_status("stopped")
            return

        self.set_error_state(f"App exited with code {code}")
        self.on_message(f"App exited with code {code}; restarting")
        time.sleep(RESTART_DELAY)
        with self._state_lock:
            if not self._want_running:
                self._set_status("stopped")
                return
        try:
            app = self.config["app"]
            assert app["kind"] == "command"
            self._launch(app)
        except Exception as exc:
            logger.exception("Failed to restart container app")
            self.set_error_state(str(exc))
            self._set_status("stopped")

    def stop(self) -> None:
        """Stop the app command.  Safe to call when already stopped."""
        with self._state_lock:
            self._want_running = False
            proc = self._app_proc

        for session in self._sessions_snapshot():
            try:
                session.stop()
            except Exception:
                logger.exception("Failed to stop container session")

        if proc is not None:
            try:
                proc.wait(timeout=15)
            except Exception:
                logger.debug("Killing stuck exec client", exc_info=True)
                try:
                    proc.kill()
                except Exception:
                    pass
        with self._state_lock:
            self._app_proc = None
        self._set_status("stopped")

    def _sessions_snapshot(self) -> list[ContainerSession]:
        with self._session_lock:
            return list(self._sessions.values())

    def delete_runtime(self) -> None:
        """Stop the app and delete its containers.

        The project files and build artifacts are left untouched.
        """
        self.stop()
        for session in self._sessions_snapshot():
            try:
                session.remove()
            except Exception:
                logger.exception("Failed to remove container session")
        with self._session_lock:
            self._sessions.clear()

    def build(self) -> None:
        """Run the project's build command, restarting the app afterwards.

        A build happens in the build image and must only ever produce
        platform independent output inside ``/app``.
        """
        build = self.config["build"]
        if build is None:
            self.on_message("Nothing to build")
            return

        with self._build_lock:
            was_running = self.status in ("running", "dev")
            was_dev = self._dev
            self.stop()
            self._set_status("loading")
            self.on_message(f"Building with {build['image']}")
            try:
                self._prepare_dirs()
                code = self._run_attached(build["image"], build["command"])
                if code != 0:
                    raise RuntimeError(
                        f"Build command failed with exit code {code}"
                    )
                self._write_build_marker()
                self.set_error_state(None)
            except Exception as exc:
                self.on_message(f"Build failed: {exc}")
                self.set_error_state(str(exc))
                self._set_status("stopped")
                raise

            self.on_message("Build complete")
            if was_running:
                self.start(dev=was_dev)
            else:
                self._set_status("stopped")

    def _run_attached(self, image: str, command: list[str]) -> int:
        """Run a command to completion, streaming its output to the log."""
        session = self._session(image)
        self.on_message(f"$ {' '.join(command)}")
        proc = session.exec(
            list(command),
            env=self.get_environment(),
            workdir="/app",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            tty=True,
        )
        assert proc.stdout is not None
        for raw in proc.stdout:
            self.on_message(raw.decode("utf-8", "replace").rstrip("\r\n"))
        return proc.wait()

    def run_script(self, name: str) -> None:
        """Run a named action script in a container.

        The command runs in the background and streams its output to the
        log, so the caller is not blocked by a long running script.  Only
        one action runs at a time.
        """
        script = self.config["scripts"].get(name)
        if script is None:
            raise KeyError(f"No script named {name!r}")
        if not self._action_lock.acquire(blocking=False):
            raise RuntimeError("Another action is already running")
        try:
            self._prepare_dirs()
            threading.Thread(
                target=self._run_script_thread,
                args=(script,),
                daemon=True,
                name=f"capp-action-{name}",
            ).start()
        except Exception:
            self._action_lock.release()
            raise

    def _run_script_thread(self, script: ScriptConfig) -> None:
        try:
            self.on_message(f"Running action {script['name']}")
            code = self._run_attached(script["image"], script["command"])
            self.on_message(f"Action {script['name']} exited with code {code}")
        except Exception as exc:
            logger.exception("Container app action failed")
            self.on_message(f"Action {script['name']} failed: {exc}")
        finally:
            self._action_lock.release()

    def clean(self) -> None:
        """Delete build artifacts, leaving the source project alone."""
        self.stop()
        marker = self._marker_path()
        if os.path.exists(marker):
            os.remove(marker)
        if self.config["app"]["kind"] == "staticfiles":
            source = self.static_source_dir()
            if os.path.isdir(source) and self.config["build"] is not None:
                shutil.rmtree(source, ignore_errors=True)
        self.on_message("Cleaned build artifacts")
        self._set_status("stopped")

    def close(self) -> None:
        """Stop everything this runtime started and remove its containers."""
        try:
            self.delete_runtime()
        except Exception:
            logger.exception("Failed to close container runtime")
