# SPDX-License-Identifier: GPL-3.0-or-later
"""Container backed app runtimes.

A container app project describes itself with a ``container-app.toml``
file (see :mod:`appconfig`).  Every script is a list of command steps that
run in series, so a build can use one image for one step and a different
image for the next.  Each command is ``podman exec``'d into a long lived
"keepalive" container, so running several commands in turn reuses one
container and its writable layer instead of paying to create a fresh
container every time.

Foreground scripts run one at a time; background scripts and the app may
run alongside them.  Every command keeps its own log, tagged with the
command that produced it, so the UI can route each line to its console.

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
import os
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any, Final, Literal

import structlog

from kaithem.api.util import get_vardir
from kaithem.src import podman_util

from .appconfig import (
    APP_SCRIPT_NAME,
    CommandApp,
    CommandStep,
    ContainerAppConfig,
    ScriptConfig,
    load_config,
)

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
MessageCallback = Callable[[str, str], None]
CommandCallback = Callable[[str, str, int | None], None]

#: Script name reserved for the app command in snapshots and events.
APP_COMMAND: Final = APP_SCRIPT_NAME

#: Run status of a manually triggered script.
CommandStatus = Literal["stopped", "running", "exited", "failed"]


class CommandState:
    """Everything known about one app or script command.

    The runtime keeps one of these per script plus one for the app, so the
    UI can build its launch buttons and consoles from a single list and
    every log line can be routed to the console that produced it.
    """

    def __init__(self, name: str, steps: list[CommandStep], background: bool):
        self.name = name
        self.steps = steps
        self.background = background
        self.status: str = "stopped"
        self.exit_code: int | None = None
        self.proc: subprocess.Popen[bytes] | None = None
        self.cancel = threading.Event()
        self.thread: threading.Thread | None = None
        self.log: deque[str] = deque(maxlen=LOG_BUFFER_LINES)

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "background": self.background,
            "status": self.status,
            "exit_code": self.exit_code,
            "log": list(self.log),
        }


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


def _step_images(steps: list[CommandStep]) -> list[str]:
    """Return the distinct images used by steps, in first-seen order."""
    images: list[str] = []
    for step in steps:
        if step["image"] not in images:
            images.append(step["image"])
    return images


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
        self.data_dir = os.path.abspath(data_dir)
        self.base_path = base_path
        self._ipc_dir = os.path.join(runtime_dir(owner_id), "ipc")

        # Guards ``_status``, ``_error``, ``_want_running`` and ``_dev``;
        # separate from the other locks so a status read never blocks on
        # container I/O.
        self._state_lock = threading.RLock()
        self._status: ContainerStatus = "stopped"
        self._error: str | None = None
        self._want_running = False
        self._dev = False

        self._sessions: dict[str, ContainerSession] = {}
        self._session_lock = threading.Lock()
        # Only one foreground script may run at a time.  Background scripts
        # and the app never take this lock.
        self._foreground_lock = threading.Lock()

        # Guards the command states and their logs.
        self._command_lock = threading.RLock()
        self._commands: dict[str, CommandState] = {}

        self._message_callbacks: list[MessageCallback] = []
        self._command_callbacks: list[CommandCallback] = []
        self._status_callbacks: list[StatusCallback] = []
        self._notify_lock = threading.Lock()

        self.config: ContainerAppConfig
        self.reload_config()

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
    def supports_run(self) -> bool:
        """Whether the app is a command run inside a container."""
        app = self.config["app"]
        return app is not None and app["kind"] == "command"

    @property
    def app_kind(self) -> str | None:
        app = self.config["app"]
        return None if app is None else app["kind"]

    @property
    def run_images(self) -> list[str]:
        """Distinct images used by the run steps, in order."""
        app = self.config["app"]
        if app is None or app["kind"] != "command":
            return []
        return _step_images(app["steps"])

    @property
    def scripts(self) -> dict[str, ScriptConfig]:
        """Named commands the project exposes as runnable actions."""
        return self.config["scripts"]

    def get_commands(self) -> list[dict[str, Any]]:
        """Snapshot every command, with the app always first."""
        with self._command_lock:
            names: list[str] = []
            if APP_COMMAND in self._commands:
                names.append(APP_COMMAND)
            names.extend(name for name in self._commands if name != APP_COMMAND)
            return [self._commands[name].snapshot() for name in names]

    def get_command_log(self, name: str) -> list[str]:
        """Return a copy of one command's buffered log lines."""
        with self._command_lock:
            state = self._commands.get(name)
            return list(state.log) if state is not None else []

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
        if app is None or app["kind"] != "staticfiles":
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

    # -- Log and command plumbing ---------------------------------------

    def _emit(self, name: str, message: str) -> None:
        """Append one output line to a command's log and notify listeners."""
        if not isinstance(message, str):
            raise TypeError("message must be a string")
        with self._command_lock:
            state = self._commands.get(name)
            if state is None:
                return
            state.log.append(message)
        with self._notify_lock:
            callbacks = list(self._message_callbacks)
        for callback in callbacks:
            try:
                callback(name, message)
            except Exception:
                logger.exception("Container app log callback failed")

    def _set_command_state(
        self, name: str, status: str, exit_code: int | None = None
    ) -> None:
        """Update a command's run status and notify listeners."""
        with self._command_lock:
            state = self._commands.get(name)
            if state is None:
                return
            state.status = status
            state.exit_code = exit_code
        with self._notify_lock:
            callbacks = list(self._command_callbacks)
        for callback in callbacks:
            try:
                callback(name, status, exit_code)
            except Exception:
                logger.exception("Container app command callback failed")

    def add_message_callback(self, callback: MessageCallback) -> None:
        with self._notify_lock:
            self._message_callbacks.append(callback)

    def remove_message_callback(self, callback: MessageCallback) -> None:
        with self._notify_lock:
            if callback in self._message_callbacks:
                self._message_callbacks.remove(callback)

    def add_command_callback(self, callback: CommandCallback) -> None:
        with self._notify_lock:
            self._command_callbacks.append(callback)

    def remove_command_callback(self, callback: CommandCallback) -> None:
        with self._notify_lock:
            if callback in self._command_callbacks:
                self._command_callbacks.remove(callback)

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
        with self._command_lock:
            app_state = self._commands.get(APP_COMMAND)
            if app_state is not None:
                app_state.status = status
        with self._notify_lock:
            status_callbacks = list(self._status_callbacks)
            command_callbacks = list(self._command_callbacks)
        for callback in status_callbacks:
            try:
                callback(status)
            except Exception:
                logger.exception("Container app status callback failed")
        if app_state is not None:
            for callback in command_callbacks:
                try:
                    callback(APP_COMMAND, status, app_state.exit_code)
                except Exception:
                    logger.exception("Container app command callback failed")

    # -- Config state ---------------------------------------------------

    def is_built(self) -> bool:
        """Whether a usable app exists on disk.

        Building is a manual developer action, so a command app is always
        startable; a static app is only usable once its output directory
        exists.
        """
        app = self.config["app"]
        if app is None:
            return False
        if app["kind"] == "staticfiles":
            return os.path.isdir(self.static_source_dir())
        return True

    def reload_config(self) -> None:
        config = load_config(self.project_folder)
        self._sync_commands(config)
        self.config = config

    def _sync_commands(self, config: ContainerAppConfig) -> None:
        """Match the command states to the scripts in a fresh config."""
        app = config["app"]
        desired: dict[str, tuple[list[CommandStep], bool]] = {}
        if app is not None and app["kind"] == "command":
            desired[APP_COMMAND] = (app["steps"], True)
        for name, script in config["scripts"].items():
            desired[name] = (script["steps"], script["background"])

        stale: list[CommandState] = []
        with self._command_lock:
            for name, state in self._commands.items():
                if name in desired:
                    state.steps, state.background = desired[name]
                else:
                    stale.append(state)
            for state in stale:
                self._commands.pop(state.name, None)
            for name, (steps, background) in desired.items():
                if name in self._commands:
                    continue
                state = CommandState(name, steps, background)
                if name == APP_COMMAND:
                    state.status = self._status
                self._commands[name] = state

        for state in stale:
            self._cancel_state(state)
            if state.name == APP_COMMAND:
                with self._state_lock:
                    self._want_running = False

    def _cancel_state(self, state: CommandState) -> None:
        """Ask a running command to stop and kill its exec client."""
        state.cancel.set()
        with self._command_lock:
            proc = state.proc
        if proc is None:
            return
        try:
            proc.kill()
        except Exception:
            logger.debug("Failed to kill command client", exc_info=True)

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

        Does nothing but launch the command; it never builds.  Building
        is always a manual developer action.
        """
        app = self.config["app"]
        if app is None or app["kind"] != "command":
            raise RuntimeError("This project has no run command")

        state = self._app_state()
        state.cancel.clear()
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

    def _app_state(self) -> CommandState:
        with self._command_lock:
            state = self._commands.get(APP_COMMAND)
        if state is None:
            raise RuntimeError("This project has no run command")
        return state

    def _launch(self, app: CommandApp) -> None:
        """Run the setup steps, then keep the final step running."""
        state = self._app_state()
        steps = app["steps"]
        for step in steps[:-1]:
            code = self._run_attached(state, step)
            if code != 0:
                raise RuntimeError(
                    f"Setup command failed with exit code {code}"
                )
        self._launch_persistent(state, steps[-1])

    def _launch_persistent(
        self, state: CommandState, step: CommandStep
    ) -> None:
        session = self._session(step["image"])
        proc = session.exec(
            list(step["command"]),
            env=self.get_environment(),
            workdir="/app",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            tty=True,
        )
        assert proc.stdout is not None
        with self._command_lock:
            state.proc = proc
            state.exit_code = None
        with self._state_lock:
            status: ContainerStatus = "dev" if self._dev else "running"
        self._set_command_state(APP_COMMAND, status, None)
        self._set_status(status)
        thread = threading.Thread(
            target=self._monitor,
            args=(state, proc, step),
            daemon=True,
            name=f"capp-mon-{session.name}",
        )
        with self._command_lock:
            state.thread = thread
        thread.start()

    def _monitor(
        self,
        state: CommandState,
        proc: subprocess.Popen[bytes],
        step: CommandStep,
    ) -> None:
        """Stream the app's output and restart it if it dies."""
        stdout = proc.stdout
        assert stdout is not None
        for raw in stdout:
            self._emit(
                APP_COMMAND,
                raw.decode("utf-8", "replace").rstrip("\r\n"),
            )
        code = proc.wait()

        with self._command_lock:
            if state.proc is not proc:
                # Superseded by a newer launch or an explicit stop.
                return
            state.proc = None
            state.exit_code = code
        with self._state_lock:
            want_running = self._want_running

        if not want_running:
            self._set_status("stopped")
            return

        self.set_error_state(f"App exited with code {code}")
        self._emit(APP_COMMAND, f"App exited with code {code}; restarting")
        self._set_command_state(APP_COMMAND, state.status, code)
        time.sleep(RESTART_DELAY)
        with self._state_lock:
            if not self._want_running:
                self._set_status("stopped")
                return
        try:
            self._launch_persistent(state, step)
        except Exception as exc:
            logger.exception("Failed to restart container app")
            self.set_error_state(str(exc))
            self._set_status("stopped")

    def stop(self) -> None:
        """Stop the app and every script command.

        Safe to call when already stopped.
        """
        with self._state_lock:
            self._want_running = False

        self._stop_all_commands()
        for session in self._sessions_snapshot():
            try:
                session.stop()
            except Exception:
                logger.exception("Failed to stop container session")

        with self._command_lock:
            app_state = self._commands.get(APP_COMMAND)
            if app_state is not None and app_state.proc is not None:
                try:
                    app_state.proc.wait(timeout=15)
                except Exception:
                    logger.debug("Killing stuck exec client", exc_info=True)
                    try:
                        app_state.proc.kill()
                    except Exception:
                        pass
                app_state.proc = None
        self._set_status("stopped")

    def _stop_all_commands(self) -> None:
        """Cancel every running command and wait for its thread."""
        with self._command_lock:
            states = list(self._commands.values())
        for state in states:
            self._cancel_state(state)
        for state in states:
            thread = state.thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=10)

    def _sessions_snapshot(self) -> list[ContainerSession]:
        with self._session_lock:
            return list(self._sessions.values())

    def delete_runtime(self) -> None:
        """Stop every command and delete the runtime's containers.

        The project files are left untouched.
        """
        self.stop()
        for session in self._sessions_snapshot():
            try:
                session.remove()
            except Exception:
                logger.exception("Failed to remove container session")
        with self._session_lock:
            self._sessions.clear()

    def _run_steps(self, state: CommandState, steps: list[CommandStep]) -> int:
        """Run steps in order, stopping at the first failure or cancel.

        Returns the exit code of the first failing step, or 0 when every
        step succeeded.
        """
        for step in steps:
            if state.cancel.is_set():
                return -1
            code = self._run_attached(state, step)
            if code != 0 or state.cancel.is_set():
                return code
        return 0

    def _run_attached(self, state: CommandState, step: CommandStep) -> int:
        """Run a command to completion, streaming its output to its log."""
        session = self._session(step["image"])
        command = step["command"]
        self._emit(state.name, f"$ {' '.join(command)}")
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
        with self._command_lock:
            state.proc = proc
            if state.cancel.is_set():
                proc.kill()
        for raw in proc.stdout:
            self._emit(
                state.name,
                raw.decode("utf-8", "replace").rstrip("\r\n"),
            )
        code = proc.wait()
        with self._command_lock:
            if state.proc is proc:
                state.proc = None
        return code

    def run_script(self, name: str) -> None:
        """Start a named script.

        Foreground scripts run one at a time and stream their output to
        their own log.  A background script may run alongside other
        commands; starting any script returns immediately.
        """
        if name == APP_COMMAND:
            raise ValueError("'app' is not a script")
        with self._command_lock:
            state = self._commands.get(name)
            if state is None:
                raise KeyError(f"No script named {name!r}")
            background = state.background
            if state.status == "running":
                raise RuntimeError(f"Script {name!r} is already running")

        if not background:
            if not self._foreground_lock.acquire(blocking=False):
                raise RuntimeError(
                    "Another foreground command is already running"
                )
        try:
            self._prepare_dirs()
            with self._command_lock:
                if state.status == "running":
                    raise RuntimeError(f"Script {name!r} is already running")
                state.cancel.clear()
                state.exit_code = None
                state.status = "running"
                state.log.clear()
            self._set_command_state(name, "running", None)
            thread = threading.Thread(
                target=self._run_script_thread,
                args=(state, background),
                daemon=True,
                name=f"capp-action-{name}",
            )
            with self._command_lock:
                state.thread = thread
            thread.start()
        except Exception:
            if not background:
                self._foreground_lock.release()
            raise

    def _run_script_thread(self, state: CommandState, background: bool) -> None:
        name = state.name
        try:
            self._emit(name, f"Running action {name}")
            code = self._run_steps(state, state.steps)
            if state.cancel.is_set():
                self._emit(name, f"Action {name} canceled")
                self._set_command_state(name, "stopped", None)
            elif code == 0:
                self._emit(name, f"Action {name} exited with code 0")
                self._set_command_state(name, "exited", 0)
            else:
                self._emit(name, f"Action {name} exited with code {code}")
                self._set_command_state(name, "failed", code)
        except Exception as exc:
            logger.exception("Container app action failed")
            self._emit(name, f"Action {name} failed: {exc}")
            self._set_command_state(name, "failed", None)
        finally:
            with self._command_lock:
                state.proc = None
                state.thread = None
            if not background:
                self._foreground_lock.release()

    def stop_script(self, name: str) -> None:
        """Cancel a running script, or stop the app by its special name."""
        if name == APP_COMMAND:
            self.stop()
            return
        with self._command_lock:
            state = self._commands.get(name)
        if state is None:
            raise KeyError(f"No script named {name!r}")
        self._cancel_state(state)

    def close(self) -> None:
        """Stop everything this runtime started and remove its containers."""
        try:
            self.delete_runtime()
        except Exception:
            logger.exception("Failed to close container runtime")
