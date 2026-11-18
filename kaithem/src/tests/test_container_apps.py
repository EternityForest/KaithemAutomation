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
from kaithem.src.plugins.CorePluginContainerApps import appconfig, runtime

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
    created = _create(_app_type(), plugin.resource_types.APP_DEFAULT)
    assert created["data"]["service_user"] == "__guest__"
    assert created["data"]["permissions"] == ["view_status"]


def test_instance_default_is_valid():
    created = _create(_instance_type(), plugin.resource_types.INSTANCE_DEFAULT)
    assert created["data"]["boot"] is True
    assert created["data"]["app"] == ""


def test_instance_requires_app():
    data = dict(plugin.resource_types.INSTANCE_DEFAULT)
    del data["app"]
    with pytest.raises(Exception):
        _create(_instance_type(), data)


def test_instance_name_must_be_slug():
    data = dict(plugin.resource_types.INSTANCE_DEFAULT)
    data["name"] = "Not A Slug"
    with pytest.raises(Exception):
        _create(_instance_type(), data)


def test_app_rejects_unknown_key():
    data = dict(plugin.resource_types.APP_DEFAULT)
    data["subdomain"] = "legacy"
    with pytest.raises(Exception):
        _create(_app_type(), data)


# -- Config parser ------------------------------------------------------

STATIC_APP = {
    "scripts": {
        "image": "docker.io/oven/bun:1-slim",
        "build": [{"command": ["bun", "run", "ci"]}],
    },
    "app": {"type": "staticfiles", "source": "dist"},
}


def test_parse_staticfiles_app():
    config = appconfig.parse_config(STATIC_APP)
    assert config["app"] == {"kind": "staticfiles", "source": "dist"}
    build = config["scripts"]["build"]
    assert build["background"] is False
    assert build["steps"] == [
        {"image": "docker.io/oven/bun:1-slim", "command": ["bun", "run", "ci"]}
    ]


def test_build_is_an_ordinary_script():
    """``build`` is never special; it is a script the developer runs."""
    config = appconfig.parse_config(STATIC_APP)
    assert "build" in config["scripts"]
    assert config["scripts"]["build"]["name"] == "build"


def test_parse_command_app_infers_type():
    config = appconfig.parse_config(
        {
            "scripts": {"image": "docker.io/library/python:3-slim"},
            "app": {"command": [{"command": ["python", "main.py"]}]},
        }
    )
    assert config["app"]["kind"] == "command"
    assert config["app"]["steps"] == [
        {
            "image": "docker.io/library/python:3-slim",
            "command": ["python", "main.py"],
        }
    ]


def test_app_can_override_image():
    config = appconfig.parse_config(
        {
            "scripts": {"image": "docker.io/library/python:3-slim"},
            "app": {
                "image": "custom:1",
                "command": [{"command": ["python", "main.py"]}],
            },
        }
    )
    assert config["app"]["steps"][0]["image"] == "custom:1"


def test_named_scripts_are_parsed():
    config = appconfig.parse_config(
        {
            "scripts": {
                "image": "docker.io/library/python:3-slim",
                "migrate": [{"command": ["python", "migrate.py"]}],
            },
            "app": {"command": [{"command": ["python", "main.py"]}]},
        }
    )
    assert set(config["scripts"]) == {"migrate"}
    assert config["scripts"]["migrate"]["steps"][0]["image"] == (
        "docker.io/library/python:3-slim"
    )


def test_multi_step_build_keeps_order_and_images():
    """A build can mix images; steps run in the order they are listed."""
    config = appconfig.parse_config(
        {
            "scripts": {
                "image": "docker.io/oven/bun:1-slim",
                "build": [
                    {
                        "image": "docker.io/library/rust:1.80-slim",
                        "command": ["cargo", "build", "--release"],
                    },
                    {"command": ["bun", "run", "ci"]},
                ],
            },
            "app": {"type": "staticfiles", "source": "dist"},
        }
    )
    assert config["scripts"]["build"]["steps"] == [
        {
            "image": "docker.io/library/rust:1.80-slim",
            "command": ["cargo", "build", "--release"],
        },
        {
            "image": "docker.io/oven/bun:1-slim",
            "command": ["bun", "run", "ci"],
        },
    ]


def test_app_steps_keep_order():
    """The app command is a step list; the last step is the long runner."""
    config = appconfig.parse_config(
        {
            "scripts": {"image": "docker.io/oven/bun:1-slim"},
            "app": {
                "type": "command",
                "command": [
                    {"command": ["bun", "install"]},
                    {"command": ["bun", "run", "start"]},
                ],
            },
        }
    )
    assert config["app"]["kind"] == "command"
    assert [step["command"] for step in config["app"]["steps"]] == [
        ["bun", "install"],
        ["bun", "run", "start"],
    ]


def test_empty_step_list_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {"image": "x"},
                "app": {"command": []},
            }
        )


def test_empty_build_step_list_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {"image": "x", "build": []},
                "app": {"type": "staticfiles", "source": "dist"},
            }
        )


def test_unknown_key_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {"scripts": {"image": "x"}, "app": {"source": "dist"}, "extra": 1}
        )


def test_missing_image_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config({"app": {"command": [{"command": ["run"]}]}})


def test_staticfiles_app_needs_no_image():
    config = appconfig.parse_config({"app": {"source": "dist"}})
    assert config["app"] == {"kind": "staticfiles", "source": "dist"}


def test_command_and_source_conflict():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {"image": "x"},
                "app": {"command": [{"command": ["run"]}], "source": "dist"},
            }
        )


def test_app_is_optional():
    """A project may exist only to offer manually triggered scripts."""
    config = appconfig.parse_config({"scripts": {"image": "x"}})
    assert config["app"] is None
    assert config["scripts"] == {}


def test_scripts_only_project_parses():
    config = appconfig.parse_config(
        {
            "scripts": {
                "image": "docker.io/library/rust:1.80-slim",
                "flash": [{"command": ["cargo", "run", "--bin", "flash"]}],
            }
        }
    )
    assert config["app"] is None
    assert config["scripts"]["flash"]["steps"][0]["command"] == [
        "cargo",
        "run",
        "--bin",
        "flash",
    ]


def test_background_flag_is_parsed():
    config = appconfig.parse_config(
        {
            "scripts": {
                "image": "x",
                "watch": {
                    "background": True,
                    "command": [{"command": ["bun", "run", "dev"]}],
                },
            }
        }
    )
    assert config["scripts"]["watch"]["background"] is True
    assert config["scripts"]["watch"]["steps"][0]["command"] == [
        "bun",
        "run",
        "dev",
    ]


def test_background_flag_must_be_boolean():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {
                    "image": "x",
                    "watch": {
                        "background": "yes",
                        "command": [{"command": ["x"]}],
                    },
                }
            }
        )


def test_app_script_name_is_reserved():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {"scripts": {"image": "x", "app": [{"command": ["x"]}]}}
        )


def test_script_unknown_key_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {
                    "image": "x",
                    "watch": {
                        "background": True,
                        "command": [{"command": ["x"]}],
                        "daemon": True,
                    },
                }
            }
        )


def test_empty_command_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {"image": "x"},
                "app": {"command": [{"command": []}]},
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


# -- Container naming ---------------------------------------------------


def test_container_name_depends_on_owner_and_image():
    """Same owner and image share a container; either one differs."""
    shared = runtime.container_name("app:m:r", "docker.io/oven/bun:1")
    assert shared == runtime.container_name("app:m:r", "docker.io/oven/bun:1")
    assert shared != runtime.container_name(
        "app:m:r", "docker.io/library/rust:1"
    )
    assert shared != runtime.container_name(
        "instance:m:r", "docker.io/oven/bun:1"
    )


# -- Shipped template ---------------------------------------------------


def test_shipped_template_parses():
    """The bundled starter project must always be valid."""
    config = appconfig.load_config(plugin.resource_types.TEMPLATE_DIR)
    assert config["app"]["kind"] == "staticfiles"
    assert "build" in config["scripts"]


def test_template_has_expected_files():
    expected = [
        "container-app.toml",
        "index.html",
        "package.json",
        "tsconfig.json",
        "build.ts",
        "src/main.ts",
        "scripts/check-platform.ts",
    ]
    for name in expected:
        path = os.path.join(
            plugin.resource_types.TEMPLATE_DIR, *name.split("/")
        )
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
