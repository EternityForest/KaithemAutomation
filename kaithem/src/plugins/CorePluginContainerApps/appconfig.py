# SPDX-License-Identifier: GPL-3.0-or-later
"""Parse and validate ``container-app.toml`` project configs.

A container app project describes itself with a small TOML file in its
project folder.  The file names a default container image, optional named
scripts that are exec'd inside a container, and how the finished project
is served (either static files Kaithem serves, or a command run in a
container).

Example::

    # container-app.toml
    [scripts]
    image = "docker.io/oven/bun:1.4.4-slim"

    [scripts.build]
    [[scripts.build.command]]
    image = "docker.io/library/rust:1.80-slim"
    command = ["cargo", "build", "--release"]

    [[scripts.build.command]]
    command = ["bun", "install"]

    [scripts.watch]
    background = true
    [[scripts.watch.command]]
    command = ["bun", "run", "dev"]

    [[app.command]]
    command = ["bun", "run", "start"]

or, for a project that only builds static files::

    [scripts]
    image = "docker.io/library/nginx:1.27-alpine"

    [scripts.build]
    [[scripts.build.command]]
    command = ["sh", "-c", "cp -r src/* dist/"]

    [app]
    type = "staticfiles"
    source = "dist"

or, for a project with no app at all, just manually triggered scripts
(for example firmware to flash onto a microcontroller)::

    [scripts]
    image = "docker.io/library/rust:1.80-slim"

    [scripts.flash]
    [[scripts.flash.command]]
    command = ["cargo", "run", "--bin", "flash"]

Every script is a list of command steps that run in series.  Each step
may name its own ``image``; a step without one uses the ``[scripts]``
default.  A script marked ``background = true`` may run alongside other
commands; a normal script runs on its own and can be cancelled.  The
legacy ``[[scripts.name]]`` table list is also accepted and means a
foreground script.

An app is optional.  When present, its run command is a list too: the
final step is the long running process, and the steps before it run to
completion first.  A command app is reachable over the web through a
path proxy unless it sets ``[app] web = false``, which is how a UIless
service is declared; a staticfiles app is always served on the web.

The optional ``[env]`` table adds variables to every script's
environment.  Values are strings and may reference predefined variables
with a ``${NAME}`` expansion; the only predefined variable is
``IMAGE_ARCH``, the architecture (e.g. ``amd64``) of the image a command
is about to run in.  Unknown references are rejected on load.

Parsing and validation are kept completely separate from running
anything, so a broken config fails loudly on load instead of at build
time.
"""

from __future__ import annotations

import os
import re
import tomllib
from typing import Any, Final, Literal, NotRequired, TypedDict

import structlog

logger = structlog.get_logger(__name__)

#: Name of the config file, relative to the project folder.
CONFIG_FILENAME = "container-app.toml"

#: Reserved script name used for the app command in snapshots and events.
APP_SCRIPT_NAME = "app"

#: Key inside ``[scripts]`` that sets the default image.  Not a script.
DEFAULT_IMAGE_KEY = "image"

#: App types understood by the runtime.
AppType = Literal["command", "staticfiles"]

#: Variables that may be referenced as ``${NAME}`` in an ``[env]`` value.
#: ``IMAGE_ARCH`` is the architecture (e.g. ``amd64``) of the image a
#: command is about to run in.
PREDEFINED_VARS: Final[tuple[str, ...]] = ("IMAGE_ARCH",)

#: Matches ``${NAME}`` references inside an ``[env]`` value.
_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(ValueError):
    """Raised when a ``container-app.toml`` is missing or invalid."""


class CommandStep(TypedDict):
    """One command in a script, run in the order it is listed.

    A step marked ``dap = true`` is a debug entry point: its ``command``
    is the complete debugger invocation (adapter and all) and must speak
    DAP over stdio.  The optional ``launch`` table is free-form DAP
    ``launch`` arguments the bridge merges into the browser's launch
    request, so a debugger that needs to be told what to debug (such as
    ``debugpy.adapter``) can be pointed at the target.
    """

    image: str
    command: list[str]
    dap: bool
    launch: NotRequired[dict[str, Any]]


class ScriptConfig(TypedDict):
    """A named sequence of command steps run one after another."""

    name: str
    steps: list[CommandStep]
    background: bool


class CommandApp(TypedDict):
    """An app served by a long running command inside a container.

    Only the final step stays running; the steps before it run to
    completion to set the container up.  ``web`` says whether the app is
    reachable over the web through a path proxy; a UIless service sets
    ``[app] web = false``.
    """

    kind: Literal["command"]
    steps: list[CommandStep]
    web: bool


class StaticFilesApp(TypedDict):
    """An app served as static files straight from Kaithem."""

    kind: Literal["staticfiles"]
    source: str


#: How a project is served.
AppConfig = CommandApp | StaticFilesApp


class ContainerAppConfig(TypedDict):
    """A fully resolved ``container-app.toml``."""

    scripts: dict[str, ScriptConfig]
    app: AppConfig | None
    env: dict[str, str]


def _location(where: str, key: str) -> str:
    return f"{where}.{key}" if where else key


def _reject_unknown(table: dict[str, object], allowed: set[str], where: str):
    for key in table:
        if key not in allowed:
            raise ConfigError(f"Unknown key '{_location(where, key)}'")


def _require_table(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"[{where}] must be a table")
    for key in value:
        if not isinstance(key, str):
            raise ConfigError(f"[{where}] has a non-string key")
    return value


def _require_string(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"'{where}' must be a string")
    value = value.strip()
    if not value:
        raise ConfigError(f"'{where}' must not be empty")
    return value


def _require_command(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"'{where}' must be a non-empty list of strings")
    parts: list[str] = []
    for index, part in enumerate(value):
        if not isinstance(part, str) or not part:
            raise ConfigError(f"'{where}[{index}]' must be a non-empty string")
        parts.append(part)
    return parts


def _optional_string(
    table: dict[str, object], key: str, where: str
) -> str | None:
    if key not in table:
        return None
    return _require_string(table[key], _location(where, key))


def _resolve_image(
    table: dict[str, object],
    where: str,
    default_image: str | None,
) -> str:
    image = _optional_string(table, "image", where)
    if image:
        return image
    if default_image:
        return default_image
    raise ConfigError(
        f"'{where}' has no image; set '{where}.image' or "
        f"[scripts].{DEFAULT_IMAGE_KEY}"
    )


def _optional_bool(
    table: dict[str, object], key: str, where: str, default: bool = False
) -> bool:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, bool):
        raise ConfigError(f"'{_location(where, key)}' must be a boolean")
    return value


def _optional_table(
    table: dict[str, object], key: str, where: str
) -> dict[str, object] | None:
    if key not in table:
        return None
    return _require_table(table[key], _location(where, key))


def _parse_step(
    value: object, where: str, default_image: str | None
) -> CommandStep:
    table = _require_table(value, where)
    _reject_unknown(table, {"command", "image", "dap", "launch"}, where)
    command = _require_command(table.get("command"), f"{where}.command")
    image = _resolve_image(table, where, default_image)
    dap = _optional_bool(table, "dap", where)
    launch = _optional_table(table, "launch", where)
    if launch is not None and not dap:
        raise ConfigError(
            f"'{where}.launch' only applies to a step marked 'dap = true'"
        )
    step: CommandStep = {"image": image, "command": command, "dap": dap}
    if launch is not None:
        step["launch"] = dict(launch)
    return step


def _parse_steps(
    value: object, where: str, default_image: str | None
) -> list[CommandStep]:
    """Parse a non-empty list of command steps that run in order."""
    if not isinstance(value, list) or not value:
        raise ConfigError(
            f"'{where}' must be a non-empty list of [[{where}]] tables"
        )
    return [
        _parse_step(entry, f"{where}[{index}]", default_image)
        for index, entry in enumerate(value)
    ]


def _validate_template(value: str, where: str) -> str:
    """Reject ``${NAME}`` references to variables we do not define."""
    for match in _VAR_RE.finditer(value):
        name = match.group(1)
        if name not in PREDEFINED_VARS:
            raise ConfigError(
                f"'{where}' references unknown variable '${{{name}}}'; "
                f"known variables: {', '.join(PREDEFINED_VARS)}"
            )
    return value


def expand_env(value: str, variables: dict[str, str]) -> str:
    """Expand ``${NAME}`` references in an ``[env]`` value.

    Only the names in :data:`PREDEFINED_VARS` are known; a reference to
    anything else is a config error.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise ConfigError(f"Unknown variable '${{{name}}}'")
        return variables[name]

    return _VAR_RE.sub(replace, value)


def _parse_env(value: object) -> dict[str, str]:
    """Parse the ``[env]`` table of extra variables every script gets."""
    if value is None:
        return {}
    table = _require_table(value, "env")
    env: dict[str, str] = {}
    for key, raw in table.items():
        where = _location("env", key)
        env[key] = _validate_template(_require_string(raw, where), where)
    return env


def _parse_script(
    name: str, value: object, default_image: str | None
) -> ScriptConfig:
    if name == DEFAULT_IMAGE_KEY:
        raise ConfigError(f"'{DEFAULT_IMAGE_KEY}' is a reserved script name")
    if name == APP_SCRIPT_NAME:
        raise ConfigError(f"'{APP_SCRIPT_NAME}' is a reserved script name")
    where = f"scripts.{name}"
    if isinstance(value, dict):
        table = _require_table(value, where)
        _reject_unknown(table, {"background", "command", "image"}, where)
        background = _optional_bool(table, "background", where)
        image = _optional_string(table, "image", where) or default_image
        steps = _parse_steps(table.get("command"), f"{where}.command", image)
    else:
        background = False
        steps = _parse_steps(value, where, default_image)
    return {"name": name, "steps": steps, "background": background}


def _parse_app(value: object, default_image: str | None) -> AppConfig | None:
    where = "app"
    if value is None:
        return None
    table = _require_table(value, where)
    _reject_unknown(table, {"type", "command", "source", "image", "web"}, where)

    app_type = _optional_string(table, "type", where)
    if app_type is not None and app_type not in ("command", "staticfiles"):
        raise ConfigError(
            f"'app.type' must be 'command' or 'staticfiles', got {app_type!r}"
        )

    has_command = "command" in table
    has_source = "source" in table
    if app_type is None:
        if has_command and not has_source:
            app_type = "command"
        elif has_source and not has_command:
            app_type = "staticfiles"
        else:
            raise ConfigError(
                "[app] must set 'command' (run in a container) or "
                "'source' (serve static files), but not both"
            )

    if app_type == "command":
        if has_source:
            raise ConfigError(
                "[app] cannot combine a run command with a static source"
            )
        app_default = _optional_string(table, "image", where) or default_image
        steps = _parse_steps(table.get("command"), "app.command", app_default)
        web = _optional_bool(table, "web", where, default=True)
        return {"kind": "command", "steps": steps, "web": web}

    if has_command:
        raise ConfigError("A staticfiles app cannot also have a run command")
    if not _optional_bool(table, "web", where, default=True):
        raise ConfigError("A staticfiles app is always served on the web")
    source = _require_string(table.get("source"), "app.source")
    return {"kind": "staticfiles", "source": source}


def parse_config(raw: object) -> ContainerAppConfig:
    """Validate an already-parsed TOML table into a config object.

    Kept separate from :func:`load_config` so it can be unit tested
    without touching the disk.
    """
    table = _require_table(raw, "")
    _reject_unknown(table, {"scripts", "app", "env"}, "")

    scripts_raw = _require_table(table.get("scripts", {}), "scripts")
    default_image = _optional_string(scripts_raw, DEFAULT_IMAGE_KEY, "scripts")

    scripts: dict[str, ScriptConfig] = {}
    for name, value in scripts_raw.items():
        if name == DEFAULT_IMAGE_KEY:
            continue
        scripts[name] = _parse_script(name, value, default_image)

    app = _parse_app(table.get("app"), default_image)
    env = _parse_env(table.get("env"))

    return {"scripts": scripts, "app": app, "env": env}


def config_path(project_folder: str) -> str:
    """Return the absolute path of the config for a project folder."""
    return os.path.join(os.path.abspath(project_folder), CONFIG_FILENAME)


def load_config(project_folder: str) -> ContainerAppConfig:
    """Read and validate ``container-app.toml`` from a project folder."""
    path = config_path(project_folder)
    try:
        with open(path, "rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(
            f"No {CONFIG_FILENAME} in the project folder"
        ) from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"{CONFIG_FILENAME} is not valid TOML: {exc}"
        ) from exc
    try:
        return parse_config(raw)
    except ConfigError as exc:
        raise ConfigError(f"{CONFIG_FILENAME}: {exc}") from None
