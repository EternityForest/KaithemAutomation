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
    command = ["bun", "install"]

    [app]
    command = ["bun", "run", "start"]

or, for a project that only builds static files::

    [scripts]
    image = "docker.io/library/nginx:1.27-alpine"

    [scripts.build]
    command = ["sh", "-c", "cp -r src/* dist/"]

    [app]
    type = "staticfiles"
    source = "dist"

Parsing and validation are kept completely separate from running
anything, so a broken config fails loudly on load instead of at build
time.
"""

from __future__ import annotations

import os
import tomllib
from typing import Literal, TypedDict

import structlog

logger = structlog.get_logger(__name__)

#: Name of the config file, relative to the project folder.
CONFIG_FILENAME = "container-app.toml"

#: Reserved script name that runs the build.  Kept out of the user
#: runnable actions so it is never started by accident.
BUILD_SCRIPT = "build"

#: Key inside ``[scripts]`` that sets the default image.  Not a script.
DEFAULT_IMAGE_KEY = "image"

#: App types understood by the runtime.
AppType = Literal["command", "staticfiles"]


class ConfigError(ValueError):
    """Raised when a ``container-app.toml`` is missing or invalid."""


class ScriptConfig(TypedDict):
    """One named command that can be exec'd inside a container."""

    name: str
    image: str
    command: list[str]


class CommandApp(TypedDict):
    """An app served by a long running command inside a container."""

    kind: Literal["command"]
    image: str
    command: list[str]


class StaticFilesApp(TypedDict):
    """An app served as static files straight from Kaithem."""

    kind: Literal["staticfiles"]
    source: str


#: How a project is served.
AppConfig = CommandApp | StaticFilesApp


class ContainerAppConfig(TypedDict):
    """A fully resolved ``container-app.toml``."""

    build: ScriptConfig | None
    scripts: dict[str, ScriptConfig]
    app: AppConfig


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


def _parse_script(
    name: str, value: object, default_image: str | None
) -> ScriptConfig:
    if name == DEFAULT_IMAGE_KEY:
        raise ConfigError(f"'{DEFAULT_IMAGE_KEY}' is a reserved script name")
    where = f"scripts.{name}"
    table = _require_table(value, where)
    _reject_unknown(table, {"command", "image"}, where)
    command = _require_command(table.get("command"), f"{where}.command")
    image = _resolve_image(table, where, default_image)
    return {"name": name, "image": image, "command": command}


def _parse_app(value: object, default_image: str | None) -> AppConfig:
    where = "app"
    if value is None:
        raise ConfigError("Missing required [app] table")
    table = _require_table(value, where)
    _reject_unknown(table, {"type", "command", "source", "image"}, where)

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
        command = _require_command(table.get("command"), "app.command")
        image = _resolve_image(table, where, default_image)
        return {"kind": "command", "image": image, "command": command}

    if has_command:
        raise ConfigError("A staticfiles app cannot also have a run command")
    source = _require_string(table.get("source"), "app.source")
    return {"kind": "staticfiles", "source": source}


def parse_config(raw: object) -> ContainerAppConfig:
    """Validate an already-parsed TOML table into a config object.

    Kept separate from :func:`load_config` so it can be unit tested
    without touching the disk.
    """
    table = _require_table(raw, "")
    _reject_unknown(table, {"scripts", "app"}, "")

    scripts_raw = _require_table(table.get("scripts", {}), "scripts")
    default_image = _optional_string(scripts_raw, DEFAULT_IMAGE_KEY, "scripts")

    scripts: dict[str, ScriptConfig] = {}
    for name, value in scripts_raw.items():
        if name == DEFAULT_IMAGE_KEY:
            continue
        scripts[name] = _parse_script(name, value, default_image)

    build = scripts.pop(BUILD_SCRIPT, None)
    app = _parse_app(table.get("app"), default_image)

    return {"build": build, "scripts": scripts, "app": app}


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
