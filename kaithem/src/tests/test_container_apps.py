# SPDX-License-Identifier: GPL-3.0-or-later
"""Fast checks for the container app resources and their config parser.

These do not build or run containers; the full stack is covered by the
Playwright end to end tests.  Here we verify that the plugin registered
both resource types, that their schemas validate, and that the
``container-app.toml`` parser accepts the shipped template and rejects
broken configs.
"""

from __future__ import annotations

import json
import os

import pytest

from kaithem.api import resource_types
from kaithem.src import podman_util
from kaithem.src.plugins import CorePluginContainerApps as plugin
from kaithem.src.plugins.CorePluginContainerApps import appconfig

APP_TYPE = "container_app"
INSTANCE_TYPE = "container_app_instance"


def _app_type():
    assert APP_TYPE in resource_types.resource_types
    return resource_types.resource_types[APP_TYPE]


def _instance_type():
    assert INSTANCE_TYPE in resource_types.resource_types
    return resource_types.resource_types[INSTANCE_TYPE]


def _create(resource_type, data: dict) -> dict:
    created = resource_type.on_create_request(
        "testmodule",
        "myapp",
        {"name": "myapp", "data": json.dumps(data)},
    )
    assert created["resource"]["type"] == resource_type.type
    return created


# -- Resource types -----------------------------------------------------


def test_container_app_type_registered():
    assert _app_type().title == "Container App"


def test_container_app_instance_type_registered():
    assert _instance_type().title == "Container App Instance"


def test_app_loads_before_instance():
    """Apps must load first so an instance can find its app."""
    assert _app_type().priority < _instance_type().priority


def test_app_default_is_valid():
    created = _create(_app_type(), plugin.APP_DEFAULT)
    assert created["data"]["service_user"] == "__guest__"
    assert created["data"]["permissions"] == ["view_status"]


def test_instance_default_is_valid():
    created = _create(_instance_type(), plugin.INSTANCE_DEFAULT)
    assert created["data"]["boot"] is True
    assert created["data"]["app"] == ""


def test_instance_requires_app():
    data = dict(plugin.INSTANCE_DEFAULT)
    del data["app"]
    with pytest.raises(Exception):
        _create(_instance_type(), data)


def test_instance_name_must_be_slug():
    data = dict(plugin.INSTANCE_DEFAULT)
    data["name"] = "Not A Slug"
    with pytest.raises(Exception):
        _create(_instance_type(), data)


def test_app_rejects_unknown_key():
    data = dict(plugin.APP_DEFAULT)
    data["subdomain"] = "legacy"
    with pytest.raises(Exception):
        _create(_app_type(), data)


# -- Config parser ------------------------------------------------------

STATIC_APP = {
    "scripts": {
        "image": "docker.io/oven/bun:1-slim",
        "build": {"command": ["bun", "run", "ci"]},
    },
    "app": {"type": "staticfiles", "source": "dist"},
}


def test_parse_staticfiles_app():
    config = appconfig.parse_config(STATIC_APP)
    assert config["app"] == {"kind": "staticfiles", "source": "dist"}
    assert config["build"] is not None
    assert config["build"]["image"] == "docker.io/oven/bun:1-slim"
    assert config["build"]["command"] == ["bun", "run", "ci"]


def test_build_is_kept_out_of_user_scripts():
    """``build`` is reserved, so it never shows up as a runnable action."""
    config = appconfig.parse_config(STATIC_APP)
    assert "build" not in config["scripts"]


def test_parse_command_app_infers_type():
    config = appconfig.parse_config(
        {
            "scripts": {"image": "docker.io/library/python:3-slim"},
            "app": {"command": ["python", "main.py"]},
        }
    )
    assert config["app"]["kind"] == "command"
    assert config["app"]["image"] == "docker.io/library/python:3-slim"
    assert config["app"]["command"] == ["python", "main.py"]


def test_app_can_override_image():
    config = appconfig.parse_config(
        {
            "scripts": {"image": "docker.io/library/python:3-slim"},
            "app": {"command": ["python", "main.py"], "image": "custom:1"},
        }
    )
    assert config["app"]["image"] == "custom:1"


def test_named_scripts_are_parsed():
    config = appconfig.parse_config(
        {
            "scripts": {
                "image": "docker.io/library/python:3-slim",
                "migrate": {"command": ["python", "migrate.py"]},
            },
            "app": {"command": ["python", "main.py"]},
        }
    )
    assert set(config["scripts"]) == {"migrate"}
    assert config["scripts"]["migrate"]["image"] == (
        "docker.io/library/python:3-slim"
    )


def test_unknown_key_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {"scripts": {"image": "x"}, "app": {"source": "dist"}, "extra": 1}
        )


def test_missing_image_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config({"app": {"command": ["run"]}})


def test_staticfiles_app_needs_no_image():
    config = appconfig.parse_config({"app": {"source": "dist"}})
    assert config["app"] == {"kind": "staticfiles", "source": "dist"}


def test_command_and_source_conflict():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {"image": "x"},
                "app": {"command": ["run"], "source": "dist"},
            }
        )


def test_missing_app_table_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config({"scripts": {"image": "x"}})


def test_empty_command_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {"image": "x"},
                "app": {"command": []},
            }
        )


def test_default_image_must_be_a_string():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {"image": {"command": ["x"]}},
                "app": {"source": "dist"},
            }
        )


# -- Shipped template ---------------------------------------------------


def test_shipped_template_parses():
    """The bundled starter project must always be valid."""
    config = appconfig.load_config(plugin.TEMPLATE_DIR)
    assert config["app"]["kind"] == "staticfiles"
    assert config["build"] is not None


def test_template_has_expected_files():
    expected = [
        "container-app.toml",
        "index.html",
        "package.json",
        "tsconfig.json",
        "vite.config.ts",
        "src/main.ts",
        "scripts/check-platform.ts",
    ]
    for name in expected:
        path = os.path.join(plugin.TEMPLATE_DIR, *name.split("/"))
        assert os.path.isfile(path), f"missing template file {name}"


# -- Streaming execs ----------------------------------------------------


class _FakePopen:
    """Stand-in for the ``podman`` client started by ``exec_container``."""


def _exec_command(monkeypatch, **kwargs) -> list[str]:
    """Return the ``podman`` command ``exec_container`` would run."""
    captured: dict[str, list[str]] = {}

    def fake_popen(cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        return _FakePopen()

    monkeypatch.setattr(podman_util, "_podman", lambda *a: ["podman", *a])
    monkeypatch.setattr(podman_util.subprocess, "Popen", fake_popen)
    podman_util.exec_container("demo", ["echo", "hi"], **kwargs)
    return captured["cmd"]


def test_exec_allocates_a_tty_when_requested(monkeypatch):
    """A TTY makes the command line-buffer its output, so logs stream."""
    cmd = _exec_command(monkeypatch, tty=True)
    assert "--tty" in cmd
    assert "--interactive" in cmd


def test_exec_has_no_tty_by_default(monkeypatch):
    assert "--tty" not in _exec_command(monkeypatch)


def test_detached_exec_ignores_tty(monkeypatch):
    """A detached exec has no output to stream, so no TTY is needed."""
    cmd = _exec_command(monkeypatch, tty=True, detach=True)
    assert "--detach" in cmd
    assert "--tty" not in cmd
