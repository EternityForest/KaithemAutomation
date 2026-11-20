# SPDX-License-Identifier: GPL-3.0-or-later
"""Fast checks for the container app resources and their config parser.

These do not build or run containers; the full stack is covered by the
Playwright end to end tests.  Here we verify that the plugin registered
both resource types, that their schemas validate, and that the
``container-app.toml`` parser accepts the shipped template and rejects
broken configs.
"""

from __future__ import annotations

import asyncio
import io
import json
import os

import pytest

from kaithem.api import resource_types
from kaithem.src import podman_util
from kaithem.src.plugins import CorePluginContainerApps as plugin
from kaithem.src.plugins.CorePluginContainerApps import (
    appconfig,
    dap_bridge,
    runtime,
)

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
        {
            "image": "docker.io/oven/bun:1-slim",
            "command": ["bun", "run", "ci"],
            "dap": False,
        }
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
            "dap": False,
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
            "dap": False,
        },
        {
            "image": "docker.io/oven/bun:1-slim",
            "command": ["bun", "run", "ci"],
            "dap": False,
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


# -- [app] web ----------------------------------------------------------


def test_command_app_web_defaults_true():
    config = appconfig.parse_config(
        {
            "scripts": {"image": "x"},
            "app": {"command": [{"command": ["run"]}]},
        }
    )
    assert config["app"]["web"] is True


def test_command_app_can_opt_out_of_the_web():
    """A UIless service sets ``web = false`` and gets no path proxy."""
    config = appconfig.parse_config(
        {
            "scripts": {"image": "x"},
            "app": {"web": False, "command": [{"command": ["run"]}]},
        }
    )
    assert config["app"]["web"] is False


def test_staticfiles_app_cannot_opt_out_of_the_web():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {"app": {"type": "staticfiles", "source": "dist", "web": False}}
        )


def test_app_web_must_be_boolean():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {"image": "x"},
                "app": {"web": "no", "command": [{"command": ["run"]}]},
            }
        )


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


# -- [env] --------------------------------------------------------------


def test_env_is_parsed():
    config = appconfig.parse_config(
        {
            "scripts": {"image": "docker.io/library/python:3-slim"},
            "env": {"UV_PROJECT_ENVIRONMENT": ".venv-${IMAGE_ARCH}"},
        }
    )
    assert config["env"] == {"UV_PROJECT_ENVIRONMENT": ".venv-${IMAGE_ARCH}"}


def test_env_defaults_to_empty():
    config = appconfig.parse_config({"scripts": {"image": "x"}})
    assert config["env"] == {}


def test_env_unknown_variable_is_rejected():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {"image": "x"},
                "env": {"FOO": "${NOPE}"},
            }
        )


def test_env_values_must_be_strings():
    with pytest.raises(appconfig.ConfigError):
        appconfig.parse_config(
            {
                "scripts": {"image": "x"},
                "env": {"FOO": 3},
            }
        )


def test_expand_env_replaces_known_variable():
    assert (
        appconfig.expand_env(".venv-${IMAGE_ARCH}", {"IMAGE_ARCH": "amd64"})
        == ".venv-amd64"
    )


def test_expand_env_leaves_plain_dollar_alone():
    assert appconfig.expand_env("$HOME", {"IMAGE_ARCH": "amd64"}) == "$HOME"


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
    config = appconfig.load_config(
        plugin.resource_types.TEMPLATES["bun-lit-static"]
    )
    assert config["app"]["kind"] == "staticfiles"
    assert "build" in config["scripts"]


def test_templates_are_registered():
    names = plugin.resource_types.TEMPLATES
    assert "bun-lit-static" in names
    assert "uv-python" in names
    for name, path in names.items():
        assert os.path.isdir(path), f"missing template directory {name}"


def test_uv_template_parses():
    """The uv Python template must always be valid."""
    config = appconfig.load_config(
        plugin.resource_types.TEMPLATES["uv-python"]
    )
    assert config["app"]["kind"] == "command"
    assert config["app"]["web"] is False
    assert "sync" in config["scripts"]
    assert "sync-offline" in config["scripts"]
    assert config["env"]["UV_PROJECT_ENVIRONMENT"] == ".venv-${IMAGE_ARCH}"
    assert config["env"]["UV_CACHE_DIR"] == ".cache/uv"


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
            plugin.resource_types.TEMPLATES["bun-lit-static"],
            *name.split("/"),
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


# -- Image architecture -------------------------------------------------


def test_get_image_arch_pulls_a_missing_image(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(podman_util, "_image_exists", lambda image: False)
    monkeypatch.setattr(
        podman_util,
        "_pull_image",
        lambda image: calls.append(f"pull:{image}"),
    )
    monkeypatch.setattr(
        podman_util, "image_architecture", lambda image: "amd64"
    )
    assert podman_util.get_image_arch("docker.io/library/python:3-slim") == (
        "amd64"
    )
    assert calls == ["pull:docker.io/library/python:3-slim"]


def test_get_image_arch_skips_pull_when_present(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(podman_util, "_image_exists", lambda image: True)
    monkeypatch.setattr(
        podman_util, "_pull_image", lambda image: calls.append("pull")
    )
    monkeypatch.setattr(
        podman_util, "image_architecture", lambda image: "arm64"
    )
    assert podman_util.get_image_arch("alpine") == "arm64"
    assert calls == []


def test_run_container_pulls_only_when_missing(monkeypatch):
    """Runs must never go looking for a newer image than the local one."""
    captured: dict[str, list[str]] = {}

    def fake_popen(cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        return _FakePopen()

    monkeypatch.setattr(podman_util, "_podman", lambda *a: ["podman", *a])
    monkeypatch.setattr(podman_util.subprocess, "Popen", fake_popen)
    podman_util.run_container("alpine", "demo", detach=True, track=True)
    assert "--pull=missing" in captured["cmd"]


# -- DAP debug entry points ---------------------------------------------


def _config_with_step(step: dict) -> dict:
    """Parse a config whose ``run`` script has exactly one command step."""
    return appconfig.parse_config(
        {
            "scripts": {
                "image": "docker.io/library/python:3-slim",
                "run": {"command": [step]},
            }
        }
    )


def test_dap_defaults_to_false():
    config = _config_with_step({"command": ["python", "app.py"]})
    assert config["scripts"]["run"]["steps"][0]["dap"] is False


def test_dap_can_be_enabled():
    config = _config_with_step({"command": ["python", "app.py"], "dap": True})
    assert config["scripts"]["run"]["steps"][0]["dap"] is True


def test_dap_must_be_boolean():
    with pytest.raises(appconfig.ConfigError):
        _config_with_step({"command": ["python", "app.py"], "dap": "yes"})


def test_dap_launch_is_free_form():
    config = _config_with_step(
        {
            "command": ["python", "-m", "debugpy.adapter"],
            "dap": True,
            "launch": {"program": "main.py", "args": ["--verbose"]},
        }
    )
    step = config["scripts"]["run"]["steps"][0]
    assert step["launch"] == {"program": "main.py", "args": ["--verbose"]}


def test_dap_launch_requires_dap():
    with pytest.raises(appconfig.ConfigError):
        _config_with_step(
            {"command": ["python", "app.py"], "launch": {"program": "main.py"}}
        )


def test_dap_launch_must_be_a_table():
    with pytest.raises(appconfig.ConfigError):
        _config_with_step(
            {"command": ["python", "app.py"], "dap": True, "launch": "main.py"}
        )


def test_command_state_reports_dap():
    """A step marked ``dap`` marks the whole command as debuggable."""
    steps = [
        {"image": "x", "command": ["setup"], "dap": False},
        {"image": "x", "command": ["python", "app.py"], "dap": True},
    ]
    state = runtime.CommandState("run", steps, background=False)
    snapshot = state.snapshot()
    assert snapshot["dap"] is True
    assert snapshot["dap_id"] is None


def test_command_state_without_dap_step():
    steps = [{"image": "x", "command": ["python", "app.py"], "dap": False}]
    state = runtime.CommandState("run", steps, background=False)
    snapshot = state.snapshot()
    assert snapshot["dap"] is False
    assert snapshot["dap_id"] is None


def _bridge() -> dap_bridge.DapBridge:
    return dap_bridge.DapBridge(
        None,
        ["python", "-m", "debugpy.adapter"],
        {},
        workdir="/app",
        launch={"program": "main.py"},
    )


def _capture(bridge: dap_bridge.DapBridge):
    """Capture what the bridge writes to the adapter and to the browser."""
    written: list[dict] = []
    emitted: list[str] = []
    bridge._write = written.append  # type: ignore[method-assign]
    bridge._to_browser = emitted.append  # type: ignore[method-assign]
    return written, emitted


def test_dap_message_roundtrip():
    buf = io.BytesIO()
    dap_bridge._write_dap_message(
        buf, {"seq": 1, "type": "request", "command": "initialize"}
    )
    buf.seek(0)
    body = dap_bridge._read_dap_message(buf)
    assert json.loads(body) == {
        "seq": 1,
        "type": "request",
        "command": "initialize",
    }


def test_dap_read_returns_none_at_end_of_stream():
    assert dap_bridge._read_dap_message(io.BytesIO(b"")) is None


def test_dap_synthetic_response_echoes_request():
    request = {"seq": 7, "type": "request", "command": "initialize"}
    response = dap_bridge._synthetic_response(request)
    assert response["request_seq"] == 7
    assert response["command"] == "initialize"
    assert response["success"] is True


def test_dap_registry_roundtrip():
    bridge = _bridge()
    bridge_id = dap_bridge.register(bridge)
    try:
        assert dap_bridge.get(bridge_id) is bridge
    finally:
        dap_bridge.unregister(bridge_id)
    assert dap_bridge.get(bridge_id) is None


def test_dap_initialize_is_forwarded_once():
    bridge = _bridge()
    written, emitted = _capture(bridge)
    init = {"seq": 1, "type": "request", "command": "initialize"}
    bridge.from_browser(json.dumps(init))
    assert written == [init]
    assert emitted == []


def test_dap_reinitialize_replays_initialized_event():
    """A second browser must not re-initialize the adapter."""
    bridge = _bridge()
    bridge._initialized = True
    written, emitted = _capture(bridge)
    bridge.from_browser(
        json.dumps({"seq": 2, "type": "request", "command": "initialize"})
    )
    assert written == []
    response = json.loads(emitted[0])
    assert response["type"] == "response"
    assert response["command"] == "initialize"
    assert response["request_seq"] == 2
    assert json.loads(emitted[1])["event"] == "initialized"


def test_dap_configuration_done_waits_for_launch():
    """debugpy needs launch before configurationDone, so it is buffered."""
    bridge = _bridge()
    written, emitted = _capture(bridge)
    done = {"seq": 3, "type": "request", "command": "configurationDone"}
    bridge.from_browser(json.dumps(done))
    assert written == []
    assert emitted == []

    bridge.from_browser(
        json.dumps({"seq": 4, "type": "request", "command": "launch"})
    )
    assert len(written) == 2
    assert written[0]["command"] == "launch"
    assert written[0]["arguments"] == {"program": "main.py", "cwd": "/app"}
    assert written[1] == done


def test_dap_launch_without_launch_table_is_forwarded_as_is():
    """A step with no ``launch`` table leaves the browser's launch alone."""
    bridge = dap_bridge.DapBridge(None, ["mydebugger"], {}, workdir="/app")
    written, _ = _capture(bridge)
    bridge.from_browser(
        json.dumps({"seq": 4, "type": "request", "command": "launch"})
    )
    assert written[0]["command"] == "launch"
    assert written[0]["arguments"] == {}


def test_dap_launch_browser_values_win():
    """Browser-supplied launch arguments override the step's table."""
    bridge = _bridge()
    written, _ = _capture(bridge)
    bridge.from_browser(
        json.dumps(
            {
                "seq": 4,
                "type": "request",
                "command": "launch",
                "arguments": {"program": "other.py"},
            }
        )
    )
    assert written[0]["arguments"] == {"program": "other.py", "cwd": "/app"}


class _FakeProc:
    def __init__(self):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(b"")

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


class _FakeSession:
    def __init__(self):
        self.calls: list[list[str]] = []

    def exec(self, args, **kwargs):
        self.calls.append(list(args))
        return _FakeProc()


def test_dap_start_runs_step_command_verbatim():
    """The step's command is the complete debugger invocation."""
    session = _FakeSession()
    bridge = dap_bridge.DapBridge(
        session, ["python", "-m", "debugpy.adapter"], {}, workdir="/app"
    )
    bridge.start()
    try:
        assert session.calls == [["python", "-m", "debugpy.adapter"]]
    finally:
        bridge.stop()


def test_dap_repeated_launch_is_answered():
    bridge = _bridge()
    bridge._launched = True
    written, emitted = _capture(bridge)
    bridge.from_browser(
        json.dumps({"seq": 5, "type": "request", "command": "launch"})
    )
    assert written == []
    assert json.loads(emitted[0])["command"] == "launch"


def test_dap_repeated_configuration_done_is_answered():
    bridge = _bridge()
    bridge._configuration_done = True
    written, emitted = _capture(bridge)
    bridge.from_browser(
        json.dumps(
            {"seq": 6, "type": "request", "command": "configurationDone"}
        )
    )
    assert written == []
    assert json.loads(emitted[0])["command"] == "configurationDone"


def test_dap_ignores_non_requests():
    bridge = _bridge()
    written, emitted = _capture(bridge)
    bridge.from_browser(json.dumps({"seq": 1, "type": "event"}))
    bridge.from_browser("not json")
    bridge.from_browser("[]")
    assert written == []
    assert emitted == []


def test_dap_detach_keeps_adapter_state():
    """Detaching must not lose the adapter's initialize/launch state."""
    bridge = _bridge()
    bridge._initialized = True
    bridge._launched = True
    bridge._configuration_done = True
    bridge._browser_busy = True
    bridge.detach()
    assert bridge._browser_busy is False
    assert bridge._browser_loop is None
    assert bridge._browser_queue is None
    assert bridge._initialized is True
    assert bridge._launched is True
    assert bridge._configuration_done is True


def test_dap_to_browser_without_a_browser_is_a_noop():
    bridge = _bridge()
    bridge._to_browser("hello")


def test_dap_stop_without_adapter_is_safe():
    bridge = _bridge()
    bridge.stop()
    assert bridge.is_running() is False


class _FakeBridge:
    """Minimal stand-in for ``dap_bridge.DapBridge`` in route tests."""

    def __init__(self) -> None:
        self.received: list[str] = []
        self.detached = False
        self.loop = None
        self.queue = None
        self.got = asyncio.Event()

    def acquire_browser(self, loop, queue) -> None:
        self.loop = loop
        self.queue = queue

    def from_browser(self, text: str) -> None:
        self.received.append(text)
        self.got.set()

    def detach(self) -> None:
        self.detached = True


async def test_dap_websocket_bridges_browser_and_adapter(monkeypatch):
    """Browser messages reach the bridge; bridge messages reach the browser."""
    from kaithem.api.web import quart_app
    from kaithem.src.plugins.CorePluginContainerApps import api, dap_bridge

    fake = _FakeBridge()
    monkeypatch.setattr(api, "_authorized_ws", lambda: True)
    monkeypatch.setattr(dap_bridge, "get", lambda bridge_id: fake)
    client = quart_app.test_client()

    async with client.websocket("/containerapps/dap/abc") as ws:
        message = '{"seq": 1, "type": "request", "command": "initialize"}'
        await ws.send(message)
        await asyncio.wait_for(fake.got.wait(), timeout=5)
        assert fake.received == [message]

        # Adapter -> browser
        fake.loop.call_soon_threadsafe(fake.queue.put_nowait, '{"type": "event"}')
        assert await asyncio.wait_for(ws.receive(), timeout=5) == (
            '{"type": "event"}'
        )

    await asyncio.sleep(0.05)
    assert fake.detached is True


async def test_dap_websocket_rejects_unknown_bridge(monkeypatch):
    from kaithem.api.web import quart_app
    from kaithem.src.plugins.CorePluginContainerApps import api

    monkeypatch.setattr(api, "_authorized_ws", lambda: True)
    client = quart_app.test_client()

    with pytest.raises(Exception):
        async with client.websocket("/containerapps/dap/missing") as ws:
            await ws.receive()
