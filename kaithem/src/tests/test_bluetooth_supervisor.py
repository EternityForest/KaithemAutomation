"""Tests for the Bluetooth supervisor (settings, alerts, auto-connect).

These tests never touch D-Bus.  They exercise the pure-Python layer with a
fake manager and a fake alert factory.
"""

from __future__ import annotations

import copy
import json
import time
from typing import Any

import pytest

from kaithem.src.plugins.CorePluginBluetooth.bluez import BluezError
from kaithem.src.plugins.CorePluginBluetooth.supervisor import (
    BluetoothSettings,
    BluetoothSupervisor,
    DeviceAlertsManager,
    DeviceSupervisor,
    DeviceTransition,
    default_device_config,
    validate_local_name,
)

ADDRESS = "AA:BB:CC:DD:EE:01"
OTHER = "AA:BB:CC:DD:EE:02"


def _device(
    address: str = ADDRESS,
    *,
    paired: bool = True,
    connected: bool = False,
    blocked: bool = False,
    battery: int | None = None,
    rssi: int | None = None,
) -> dict[str, Any]:
    return {
        "address": address,
        "paired": paired,
        "connected": connected,
        "blocked": blocked,
        "battery": battery,
        "rssi": rssi,
        "alias": "Headphones",
        "name": "Headphones",
    }


class FakeAlert:
    def __init__(self, name: str, priority: str, description: str) -> None:
        self.name = name
        self.priority = priority
        self.description = description
        self.messages: list[str] = []
        self.cleared = 0
        self.closed = 0

    def trip(self, message: str = "") -> None:
        self.messages.append(message)

    def clear(self) -> None:
        self.cleared += 1

    def close(self) -> None:
        self.closed += 1


class FakeAlertFactory:
    def __init__(self) -> None:
        self.created: list[FakeAlert] = []

    def __call__(self, name: str, priority: str, description: str) -> FakeAlert:
        alert = FakeAlert(name, priority, description)
        self.created.append(alert)
        return alert

    def by_key(self, key: str) -> FakeAlert:
        matches = [alert for alert in self.created if key in alert.name]
        assert matches, f"no alert matching {key!r}"
        return matches[-1]


class FakeManager:
    def __init__(self, devices: list[dict[str, Any]] | None = None) -> None:
        self.devices = devices or []
        self.listeners: set[Any] = set()
        self.connect_calls: list[tuple[str, float | None]] = []

    def snapshot(self) -> dict[str, Any]:
        return {
            "available": True,
            "error": None,
            "devices": copy.deepcopy(self.devices),
        }

    def connect(
        self, address: str, timeout: float | None = None
    ) -> dict[str, Any]:
        self.connect_calls.append((address, timeout))
        return self.snapshot()

    def add_listener(self, listener: Any) -> None:
        self.listeners.add(listener)

    def remove_listener(self, listener: Any) -> None:
        self.listeners.discard(listener)


def _settings(tmp_path) -> BluetoothSettings:
    return BluetoothSettings(str(tmp_path / "bluetooth.json"))


def _supervisor(
    tmp_path,
    devices: list[dict[str, Any]],
    *,
    factory: FakeAlertFactory | None = None,
) -> tuple[BluetoothSupervisor, FakeManager]:
    manager = FakeManager(devices)
    supervisor = BluetoothSupervisor(
        manager,  # type: ignore[arg-type]
        settings=_settings(tmp_path),
        alerts_manager=DeviceAlertsManager(factory or FakeAlertFactory()),
        connect_cooldown=0.0,
        connect_timeout=1.0,
    )
    return supervisor, manager


class TestValidateLocalName:
    def test_accepts_identifier(self) -> None:
        assert validate_local_name("  headphones  ") == "headphones"
        assert validate_local_name("_speaker_2") == "_speaker_2"

    def test_empty_is_none(self) -> None:
        assert validate_local_name("   ") is None
        assert validate_local_name(None) is None

    def test_rejects_non_identifier(self) -> None:
        with pytest.raises(BluezError):
            validate_local_name("my speaker")
        with pytest.raises(BluezError):
            validate_local_name("2speaker")
        with pytest.raises(BluezError):
            validate_local_name("class")

    def test_rejects_wrong_type_and_long_names(self) -> None:
        with pytest.raises(BluezError):
            validate_local_name(5)
        with pytest.raises(BluezError):
            validate_local_name("a" * 65)


class TestBluetoothSettings:
    def test_roundtrip_and_persistence(self, tmp_path) -> None:
        settings = _settings(tmp_path)
        assert settings.get(ADDRESS) is None

        config = settings.set(ADDRESS, {"auto_connect": True})
        assert config == {
            "auto_connect": True,
            "alerts": False,
            "name": None,
        }
        settings.set(ADDRESS, {"name": "headphones", "alerts": True})

        reloaded = BluetoothSettings(settings.path)
        assert reloaded.get(ADDRESS) == {
            "auto_connect": True,
            "alerts": True,
            "name": "headphones",
        }

    def test_get_returns_copy(self, tmp_path) -> None:
        settings = _settings(tmp_path)
        settings.set(ADDRESS, {"auto_connect": True})
        config = settings.get(ADDRESS)
        assert config is not None
        config["auto_connect"] = False
        assert settings.get(ADDRESS)["auto_connect"] is True

    def test_remove(self, tmp_path) -> None:
        settings = _settings(tmp_path)
        settings.set(ADDRESS, {"auto_connect": True})
        assert settings.remove(ADDRESS) is True
        assert settings.remove(ADDRESS) is False
        assert settings.get(ADDRESS) is None

    def test_rejects_bad_input(self, tmp_path) -> None:
        settings = _settings(tmp_path)
        with pytest.raises(BluezError):
            settings.set("not-an-address", {"auto_connect": True})
        with pytest.raises(BluezError):
            settings.set(ADDRESS, {"nope": True})
        with pytest.raises(BluezError):
            settings.set(ADDRESS, {"auto_connect": "yes"})

    def test_rejects_duplicate_names(self, tmp_path) -> None:
        settings = _settings(tmp_path)
        settings.set(ADDRESS, {"name": "headphones"})
        with pytest.raises(BluezError):
            settings.set(OTHER, {"name": "HeadPhones"})
        # The same device may keep its own name.
        assert settings.set(ADDRESS, {"name": "headphones"})["name"] == (
            "headphones"
        )

    def test_corrupt_file_is_ignored(self, tmp_path) -> None:
        path = tmp_path / "bluetooth.json"
        path.write_text("{ not json", encoding="utf-8")
        settings = BluetoothSettings(str(path))
        assert settings.configs() == {}

    def test_invalid_entries_are_skipped(self, tmp_path) -> None:
        path = tmp_path / "bluetooth.json"
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "devices": {
                        ADDRESS: {"auto_connect": True},
                        "bogus": {"auto_connect": True},
                        OTHER: {"auto_connect": "yes"},
                    },
                }
            ),
            encoding="utf-8",
        )
        settings = BluetoothSettings(str(path))
        assert settings.configs() == {
            ADDRESS: default_device_config() | {"auto_connect": True}
        }


class TestDeviceSupervisor:
    def test_reports_transitions(self) -> None:
        supervisor = DeviceSupervisor(ADDRESS, default_device_config())
        first = supervisor.process_device(_device())
        assert first.first_observation
        assert not first.became_connected

        connected = supervisor.process_device(_device(connected=True))
        assert connected.became_connected
        assert not connected.became_disconnected

        same = supervisor.process_device(_device(connected=True))
        assert not same.became_connected
        assert not same.became_disconnected

        gone = supervisor.process_device(_device(connected=False))
        assert gone.became_disconnected

        missing = supervisor.process_device(None)
        assert not missing.became_disconnected

    def test_config_copy_isolation(self) -> None:
        config = default_device_config()
        supervisor = DeviceSupervisor(ADDRESS, config)
        config["alerts"] = True
        assert supervisor.config["alerts"] is False
        supervisor.config["name"] = "mutated"
        assert supervisor.config["name"] is None


def _device_transition(**kwargs: bool) -> DeviceTransition:
    return DeviceTransition(**kwargs)


def _process_metadata(
    alerts: DeviceAlertsManager,
    device: dict[str, Any],
    *,
    transition: DeviceTransition | None = None,
    enabled: bool = True,
) -> None:
    alerts.process_device_metadata(
        ADDRESS,
        "headphones",
        device,
        transition or _device_transition(),
        enabled,
    )


class TestDeviceAlerts:
    def test_no_alerts_when_disabled(self) -> None:
        factory = FakeAlertFactory()
        alerts = DeviceAlertsManager(factory)
        _process_metadata(
            alerts,
            _device(battery=5, rssi=-90, connected=True),
            enabled=False,
        )
        assert factory.created == []

    def test_battery_alert_trips_once_and_clears(self) -> None:
        factory = FakeAlertFactory()
        alerts = DeviceAlertsManager(factory)
        _process_metadata(alerts, _device(battery=10))
        alert = factory.by_key("battery low")
        assert alert.priority == "warning"
        assert len(alert.messages) == 1

        _process_metadata(alerts, _device(battery=8))
        assert len(alert.messages) == 1

        _process_metadata(alerts, _device(battery=80))
        assert alert.cleared == 1

    def test_rssi_alert_requires_connection(self) -> None:
        factory = FakeAlertFactory()
        alerts = DeviceAlertsManager(factory)
        _process_metadata(alerts, _device(rssi=-90, connected=False))
        assert factory.created == []

        _process_metadata(alerts, _device(rssi=-90, connected=True))
        assert factory.by_key("signal weak").priority == "warning"

    def test_disconnect_alert_is_error(self) -> None:
        factory = FakeAlertFactory()
        alerts = DeviceAlertsManager(factory)
        _process_metadata(
            alerts,
            _device(connected=False),
            transition=_device_transition(became_disconnected=True),
        )
        alert = factory.by_key("disconnected")
        assert alert.priority == "error"

        _process_metadata(
            alerts,
            _device(connected=True),
            transition=_device_transition(became_connected=True),
        )
        assert alert.cleared == 1

    def test_disabling_alerts_closes_them(self) -> None:
        factory = FakeAlertFactory()
        alerts = DeviceAlertsManager(factory)
        _process_metadata(alerts, _device(battery=10))
        alert = factory.by_key("battery low")
        _process_metadata(alerts, _device(battery=10), enabled=False)
        assert alert.closed == 1
        assert factory.created == [alert]


class TestBluetoothSupervisor:
    def test_decorates_snapshot_with_defaults(self, tmp_path) -> None:
        supervisor, _ = _supervisor(tmp_path, [_device()])
        decorated = supervisor.decorate_snapshot(supervisor.manager.snapshot())
        assert decorated["devices"][0]["config"] == default_device_config()
        assert decorated["devices"][0]["seen"] is True
        assert "config" not in supervisor.manager.snapshot()["devices"][0]

    def test_unseen_configured_device_is_included(self, tmp_path) -> None:
        supervisor, _ = _supervisor(tmp_path, [])
        supervisor.update_device_config(ADDRESS, {"name": "headphones"})

        decorated = supervisor.decorate_snapshot(supervisor.manager.snapshot())
        devices = {device["address"]: device for device in decorated["devices"]}
        assert set(devices) == {ADDRESS}
        placeholder = devices[ADDRESS]
        assert placeholder["seen"] is False
        assert placeholder["connected"] is False
        assert placeholder["config"] == {
            "auto_connect": False,
            "alerts": False,
            "name": "headphones",
        }

    def test_seen_device_is_not_duplicated(self, tmp_path) -> None:
        supervisor, _ = _supervisor(tmp_path, [_device()])
        supervisor.update_device_config(ADDRESS, {"auto_connect": True})

        decorated = supervisor.decorate_snapshot(supervisor.manager.snapshot())
        assert len(decorated["devices"]) == 1
        assert decorated["devices"][0]["seen"] is True
        assert decorated["devices"][0]["config"]["auto_connect"] is True

    def test_config_events_carry_config(self, tmp_path) -> None:
        supervisor, _ = _supervisor(tmp_path, [_device()])
        events: list[dict[str, Any]] = []
        supervisor.add_listener(events.append)

        supervisor.update_device_config(ADDRESS, {"auto_connect": True})
        config_events = [event for event in events if event["type"] == "config"]
        assert config_events[-1] == {
            "type": "config",
            "address": ADDRESS,
            "config": {
                "auto_connect": True,
                "alerts": False,
                "name": None,
            },
        }
        snapshot_events = [
            event for event in events if event["type"] == "snapshot"
        ]
        assert snapshot_events[-1]["snapshot"]["devices"][0]["seen"] is True

        supervisor.remove_device(ADDRESS)
        config_events = [event for event in events if event["type"] == "config"]
        assert config_events[-1]["config"] == default_device_config()
        assert supervisor.get_device_config(ADDRESS) is None

    def test_forget_clears_alerts(self, tmp_path) -> None:
        factory = FakeAlertFactory()
        supervisor, _ = _supervisor(
            tmp_path, [_device(battery=5)], factory=factory
        )
        supervisor.update_device_config(ADDRESS, {"alerts": True})
        supervisor.tick()
        alert = factory.by_key("battery low")
        supervisor.remove_device(ADDRESS)
        assert alert.closed == 1

    def test_auto_connect_only_for_paired_offline_devices(
        self, tmp_path
    ) -> None:
        supervisor, manager = _supervisor(
            tmp_path,
            [
                _device(ADDRESS, paired=True, connected=False),
                _device(OTHER, paired=False),
            ],
        )
        supervisor.update_device_config(ADDRESS, {"auto_connect": True})
        supervisor.update_device_config(OTHER, {"auto_connect": True})

        supervisor.tick()
        _wait_until(lambda: manager.connect_calls)
        assert manager.connect_calls[0][0] == ADDRESS
        assert manager.connect_calls[0][1] == 1.0

    def test_auto_connect_skips_connected_and_blocked(self, tmp_path) -> None:
        supervisor, manager = _supervisor(
            tmp_path,
            [
                _device(ADDRESS, connected=True),
                _device(OTHER, blocked=True),
            ],
        )
        for address in (ADDRESS, OTHER):
            supervisor.update_device_config(address, {"auto_connect": True})
        supervisor.tick()
        time.sleep(0.1)
        assert manager.connect_calls == []

    def test_auto_connect_respects_cooldown(self, tmp_path) -> None:
        supervisor, manager = _supervisor(tmp_path, [_device()])
        supervisor.connect_cooldown = 3600.0
        supervisor.update_device_config(ADDRESS, {"auto_connect": True})

        supervisor.tick()
        _wait_until(lambda: len(manager.connect_calls) == 1)
        supervisor.tick()
        time.sleep(0.1)
        assert len(manager.connect_calls) == 1


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before the timeout")


class TestConfigApi:
    async def test_config_roundtrip(self) -> None:
        from .helpers import make_client

        client = await make_client()
        path = f"/bluetooth/api/devices/{ADDRESS}/config"

        response = await client.get(path)
        assert response.status_code == 200
        assert (await response.get_json())["config"] == (
            default_device_config()
        )

        response = await client.post(path, json={"auto_connect": True})
        assert response.status_code == 200
        payload = await response.get_json()
        assert payload["config"] == (
            default_device_config() | {"auto_connect": True}
        )
        assert payload["snapshot"]["available"] in (True, False)
        # The fake address is not reported by BlueZ, but its saved settings
        # still put it in the snapshot as an unseen device.
        snapshot_devices = {
            device["address"]: device
            for device in payload["snapshot"]["devices"]
        }
        assert snapshot_devices[ADDRESS]["seen"] is False
        assert snapshot_devices[ADDRESS]["config"]["auto_connect"] is True

        response = await client.get(path)
        assert (await response.get_json())["config"] == (
            default_device_config() | {"auto_connect": True}
        )

        response = await client.post(path, json={"name": "bad name"})
        assert response.status_code == 400
        assert (await response.get_json())["error"] == "InvalidArguments"

        response = await client.delete(path)
        assert response.status_code == 200

        response = await client.get(path)
        assert (await response.get_json())["config"] == (
            default_device_config()
        )

    async def test_requires_admin(self) -> None:
        from kaithem.src import quart_app

        client = quart_app.app.test_client(use_cookies=True)
        response = await client.get(f"/bluetooth/api/devices/{ADDRESS}/config")
        assert response.status_code == 403
