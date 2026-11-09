"""Tests for the BlueZ D-Bus wrapper's change tracking.

These tests never touch D-Bus.  They cover the pieces that decide whether
WebSocket clients get an update: signal subscriptions, the message filter and
the snapshot fingerprint.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from dbus_fast import Message, MessageType

from kaithem.src.plugins.CorePluginBluetooth.bluez import (
    _SIGNAL_MATCH_RULES,
    DISCOVERING_REFRESH_INTERVAL,
    IDLE_REFRESH_INTERVAL,
    BluezError,
    BluezManager,
    _LeAdvertisement,
    _snapshot_signature,
)


def _payload(
    devices: list[dict[str, Any]] | None = None,
    updated: float = 0.0,
) -> dict[str, Any]:
    return {
        "available": True,
        "error": None,
        "agent_registered": True,
        "agent_error": None,
        "adapters": [],
        "adapter": None,
        "devices": devices or [],
        "updated": updated,
    }


def _device(address: str = "AA:BB:CC:DD:EE:01") -> dict[str, Any]:
    return {"address": address, "name": "Test device"}


def _signal(
    path: str = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01",
    interface: str = "org.freedesktop.DBus.Properties",
    member: str = "PropertiesChanged",
) -> Message:
    return Message.new_signal(
        path=path,
        interface=interface,
        member=member,
        signature="",
        body=[],
    )


class _FakeBus:
    """Records AddMatch calls; the real bus is never involved."""

    def __init__(self) -> None:
        self.sent: list[Message] = []

    async def call(self, message: Message) -> Message:
        self.sent.append(message)
        return Message(
            message_type=MessageType.METHOD_RETURN,
            serial=1,
            reply_serial=message.serial or 1,
        )


class TestSnapshotSignature:
    def test_ignores_volatile_fields(self) -> None:
        first = _payload([_device()], updated=1.0)
        second = _payload([_device()], updated=99.0)
        second["revision"] = 7
        assert _snapshot_signature(first) == _snapshot_signature(second)

    def test_notices_device_changes(self) -> None:
        first = _payload([_device()])
        second = _payload([_device(), _device("AA:BB:CC:DD:EE:02")])
        assert _snapshot_signature(first) != _snapshot_signature(second)


class TestPublish:
    def test_only_real_changes_emit_events(self) -> None:
        manager = BluezManager()

        event = manager._publish_locked(_payload([_device()]))
        assert event is not None
        assert event["revision"] == 1
        assert (
            event["snapshot"]["devices"][0]["address"] == _device()["address"]
        )

        # A poll that found nothing new must not wake up the browsers.
        assert (
            manager._publish_locked(_payload([_device()], updated=5.0)) is None
        )
        assert manager._snapshot["revision"] == 1

        event = manager._publish_locked(
            _payload([_device(), _device("AA:BB:CC:DD:EE:02")])
        )
        assert event is not None
        assert event["revision"] == 2

    def test_event_snapshot_is_a_copy(self) -> None:
        manager = BluezManager()
        payload = _payload([_device()])
        event = manager._publish_locked(payload)
        assert event is not None
        payload["devices"].clear()
        assert len(event["snapshot"]["devices"]) == 1
        assert len(manager._snapshot["devices"]) == 1


class TestMessageFilter:
    def test_accepts_bluez_property_changes(self, monkeypatch) -> None:
        manager = BluezManager()
        calls: list[bool] = []
        monkeypatch.setattr(
            manager, "_schedule_refresh", lambda: calls.append(True)
        )

        assert manager._on_message(_signal()) is True
        assert calls == [True]

    def test_accepts_object_manager_signals_at_root(self, monkeypatch) -> None:
        manager = BluezManager()
        calls: list[bool] = []
        monkeypatch.setattr(
            manager, "_schedule_refresh", lambda: calls.append(True)
        )

        # BlueZ announces new adapters and devices from its "/" root.
        added = _signal(
            path="/",
            interface="org.freedesktop.DBus.ObjectManager",
            member="InterfacesAdded",
        )
        assert manager._on_message(added) is True
        assert calls == [True]

    def test_ignores_unrelated_signals(self, monkeypatch) -> None:
        manager = BluezManager()
        calls: list[bool] = []
        monkeypatch.setattr(
            manager, "_schedule_refresh", lambda: calls.append(True)
        )

        unrelated_path = _signal(path="/org/freedesktop/other")
        unrelated_member = _signal(member="NameOwnerChanged")
        method_call = Message(
            message_type=MessageType.METHOD_CALL,
            path="/org/bluez",
            interface="org.bluez.AgentManager1",
            member="RegisterAgent",
        )

        assert manager._on_message(unrelated_path) is False
        assert manager._on_message(unrelated_member) is False
        assert manager._on_message(method_call) is False
        assert calls == []


class TestSignalSubscriptions:
    async def test_subscribes_every_match_rule(self) -> None:
        manager = BluezManager()
        bus = _FakeBus()
        await manager._subscribe_signals(bus)  # type: ignore[arg-type]

        assert len(bus.sent) == len(_SIGNAL_MATCH_RULES)
        assert all(message.member == "AddMatch" for message in bus.sent)
        assert [message.body[0] for message in bus.sent] == list(
            _SIGNAL_MATCH_RULES
        )


class TestPollInterval:
    def test_polls_faster_while_discovering(self) -> None:
        manager = BluezManager()
        assert manager._poll_interval() == IDLE_REFRESH_INTERVAL

        manager._snapshot = {"adapters": [{"discovering": True}]}
        assert manager._poll_interval() == DISCOVERING_REFRESH_INTERVAL


def _adapter_objects(
    discovering: bool, powered: bool = True, path: str = "/org/bluez/hci0"
) -> dict[str, Any]:
    return {
        path: {
            "org.bluez.Adapter1": {
                "Address": "00:11:22:33:44:55",
                "Powered": powered,
                "Discovering": discovering,
            }
        }
    }


def _install_discovery_fakes(
    manager: BluezManager,
    monkeypatch: pytest.MonkeyPatch,
    adapter_path: str,
    discovering_after: bool,
    call_error: BluezError | None = None,
) -> list[str]:
    """Replace the D-Bus round trips with an in-memory adapter.

    Returns the D-Bus members that were called, in order.
    """
    members: list[str] = []

    async def fake_call(
        interface: str,
        member: str,
        path: str = "/",
        signature: str | None = None,
        body: list[Any] | None = None,
    ) -> Any:
        members.append(member)
        if call_error is not None:
            raise call_error
        return None

    async def fake_refresh() -> None:
        manager._snapshot = {
            "adapters": [
                {
                    "path": adapter_path,
                    "powered": True,
                    "discovering": discovering_after,
                    "discovering_owned": adapter_path
                    in manager._discovery_adapters,
                }
            ]
        }

    monkeypatch.setattr(manager, "_call", fake_call)
    monkeypatch.setattr(manager, "_refresh", fake_refresh)
    monkeypatch.setattr(manager, "_adapter_path", lambda: adapter_path)
    return members


class TestDiscoveryOwnership:
    def test_marks_only_sessions_this_connection_owns(self) -> None:
        manager = BluezManager()
        path = "/org/bluez/hci0"
        manager._discovery_adapters.add(path)

        adapters, _, _ = manager._parse_objects(_adapter_objects(True))
        assert adapters[0]["discovering"] is True
        assert adapters[0]["discovering_owned"] is True

        other, _, _ = manager._parse_objects(
            _adapter_objects(True, path="/org/bluez/hci1")
        )
        assert other[0]["discovering_owned"] is False

    def test_forgets_a_session_bluez_has_already_ended(self) -> None:
        manager = BluezManager()
        path = "/org/bluez/hci0"
        manager._discovery_adapters.add(path)

        adapters, _, _ = manager._parse_objects(_adapter_objects(False))
        assert adapters[0]["discovering_owned"] is False
        assert path not in manager._discovery_adapters

    def test_forgets_a_session_when_the_adapter_powers_off(self) -> None:
        manager = BluezManager()
        path = "/org/bluez/hci0"
        manager._discovery_adapters.add(path)

        adapters, _, _ = manager._parse_objects(
            _adapter_objects(False, powered=False)
        )
        assert adapters[0]["discovering_owned"] is False
        assert path not in manager._discovery_adapters


class TestSetDiscovering:
    async def test_start_records_ownership(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        path = "/org/bluez/hci0"
        members = _install_discovery_fakes(
            manager, monkeypatch, path, discovering_after=True
        )

        await manager._async_set_discovering(True)

        assert members == ["StartDiscovery"]
        assert manager._discovery_adapters == {path}

    async def test_start_does_nothing_when_already_owned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        path = "/org/bluez/hci0"
        manager._discovery_adapters.add(path)
        members = _install_discovery_fakes(
            manager, monkeypatch, path, discovering_after=True
        )

        await manager._async_set_discovering(True)

        assert members == []
        assert manager._discovery_adapters == {path}

    async def test_start_reports_when_bluez_stays_idle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        path = "/org/bluez/hci0"
        _install_discovery_fakes(
            manager, monkeypatch, path, discovering_after=False
        )

        with pytest.raises(BluezError) as caught:
            await manager._async_set_discovering(True)

        assert caught.value.name == "Failed"
        assert path not in manager._discovery_adapters

    async def test_stop_skips_the_call_when_no_session_is_owned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        path = "/org/bluez/hci0"
        members = _install_discovery_fakes(
            manager, monkeypatch, path, discovering_after=True
        )

        # Another application is scanning, but this manager has no session.
        await manager._async_set_discovering(False)

        assert members == []
        assert path not in manager._discovery_adapters

    async def test_stop_releases_ownership(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        path = "/org/bluez/hci0"
        manager._discovery_adapters.add(path)
        members = _install_discovery_fakes(
            manager, monkeypatch, path, discovering_after=True
        )

        await manager._async_set_discovering(False)

        assert members == ["StopDiscovery"]
        assert path not in manager._discovery_adapters

    async def test_stop_tolerates_a_session_bluez_already_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        path = "/org/bluez/hci0"
        manager._discovery_adapters.add(path)
        _install_discovery_fakes(
            manager,
            monkeypatch,
            path,
            discovering_after=False,
            call_error=BluezError(
                "org.bluez.Error.Failed", "No discovery started"
            ),
        )

        await manager._async_set_discovering(False)

        assert path not in manager._discovery_adapters

    async def test_stop_surfaces_real_failures(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        path = "/org/bluez/hci0"
        manager._discovery_adapters.add(path)
        _install_discovery_fakes(
            manager,
            monkeypatch,
            path,
            discovering_after=True,
            call_error=BluezError(
                "org.bluez.Error.NotPermitted", "Operation not permitted"
            ),
        )

        with pytest.raises(BluezError) as caught:
            await manager._async_set_discovering(False)

        assert caught.value.name == "org.bluez.Error.NotPermitted"
        assert path in manager._discovery_adapters


class _FakeExportBus:
    """Tracks exported object paths the way dbus-fast does."""

    def __init__(self) -> None:
        self.exported: set[str] = set()
        self.unexported: list[str] = []

    def export(self, path: str, interface: object) -> None:
        if path in self.exported:
            raise ValueError(f"Interface already exported at {path}")
        self.exported.add(path)

    def unexport(self, path: str) -> None:
        self.unexported.append(path)
        self.exported.discard(path)


_ADVERTISING_ADAPTER = "/org/bluez/hci0"


def _install_advertising_fakes(
    manager: BluezManager,
    monkeypatch: pytest.MonkeyPatch,
    error: BluezError | None = None,
) -> tuple[list[str], _FakeExportBus, str]:
    """Replace RegisterAdvertisement with an in-memory bus."""
    members: list[str] = []
    bus = _FakeExportBus()

    async def fake_call(
        interface: str,
        member: str,
        path: str = "/",
        signature: str | None = None,
        body: list[Any] | None = None,
    ) -> Any:
        members.append(member)
        if error is not None:
            raise error
        return None

    def fake_schedule_refresh() -> None:
        return None

    monkeypatch.setattr(manager, "_call", fake_call)
    monkeypatch.setattr(manager, "_schedule_refresh", fake_schedule_refresh)
    manager._bus = bus
    return (
        members,
        bus,
        manager._advertisement_path(_ADVERTISING_ADAPTER),
    )


class TestAdvertisingRecovery:
    async def test_enable_registers_and_records_the_advertisement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        members, bus, path = _install_advertising_fakes(manager, monkeypatch)

        await manager._async_set_advertising(_ADVERTISING_ADAPTER, True)

        assert members == ["RegisterAdvertisement"]
        assert path in bus.exported
        assert _ADVERTISING_ADAPTER in manager._advertisements

    async def test_enable_replaces_a_stale_export(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        members, bus, path = _install_advertising_fakes(manager, monkeypatch)
        bus.exported.add(path)

        await manager._async_set_advertising(_ADVERTISING_ADAPTER, True)

        assert bus.unexported == [path]
        assert path in bus.exported
        assert members == ["RegisterAdvertisement"]
        assert _ADVERTISING_ADAPTER in manager._advertisements

    async def test_already_exists_counts_as_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        members, bus, path = _install_advertising_fakes(
            manager,
            monkeypatch,
            error=BluezError("org.bluez.Error.AlreadyExists", "Already Exists"),
        )

        await manager._async_set_advertising(_ADVERTISING_ADAPTER, True)

        assert members == ["RegisterAdvertisement"]
        assert path in bus.exported
        assert _ADVERTISING_ADAPTER in manager._advertisements

    async def test_enable_failure_unexports_the_object(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        _members, bus, path = _install_advertising_fakes(
            manager,
            monkeypatch,
            error=BluezError("org.bluez.Error.NotReady", "Not ready"),
        )

        with pytest.raises(BluezError):
            await manager._async_set_advertising(_ADVERTISING_ADAPTER, True)

        assert path not in bus.exported
        assert _ADVERTISING_ADAPTER not in manager._advertisements

    def test_snapshot_pruning_unexports_the_released_object(self) -> None:
        manager = BluezManager()
        bus = _FakeExportBus()
        path = manager._advertisement_path(_ADVERTISING_ADAPTER)
        bus.exported.add(path)
        manager._bus = bus
        manager._advertisements[_ADVERTISING_ADAPTER] = _LeAdvertisement(
            manager, _ADVERTISING_ADAPTER
        )

        adapters, _, _ = manager._parse_objects(_adapter_objects(True))

        assert adapters[0]["advertising"] is False
        assert _ADVERTISING_ADAPTER not in manager._advertisements
        assert path not in bus.exported
        assert bus.unexported == [path]

    async def test_release_unexports_the_object(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        _members, bus, path = _install_advertising_fakes(manager, monkeypatch)
        bus.exported.add(path)
        manager._advertisements[_ADVERTISING_ADAPTER] = _LeAdvertisement(
            manager, _ADVERTISING_ADAPTER
        )
        manager._loop = asyncio.get_running_loop()

        manager._on_advertisement_released(_ADVERTISING_ADAPTER)
        await asyncio.sleep(0)

        assert _ADVERTISING_ADAPTER not in manager._advertisements
        assert path not in bus.exported

    async def test_enable_again_cycles_the_registration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        members, bus, path = _install_advertising_fakes(manager, monkeypatch)

        await manager._async_set_advertising(_ADVERTISING_ADAPTER, True)
        await manager._async_set_advertising(_ADVERTISING_ADAPTER, True)

        # A second request must reach the controller, otherwise a stale
        # advertisement could never be revived.
        assert members == [
            "RegisterAdvertisement",
            "UnregisterAdvertisement",
            "RegisterAdvertisement",
        ]
        assert path in bus.exported
        assert _ADVERTISING_ADAPTER in manager._advertisements

    async def test_forget_re_registers_the_advertisement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        members, bus, path = _install_advertising_fakes(manager, monkeypatch)
        device_address = "AA:BB:CC:DD:EE:01"
        device_path = f"{_ADVERTISING_ADAPTER}/dev_AA_BB_CC_DD_EE_01"
        manager._snapshot = {
            "devices": [
                {
                    "address": device_address,
                    "adapter": _ADVERTISING_ADAPTER,
                }
            ]
        }
        manager._device_paths = {device_address: device_path}

        async def fake_refresh() -> None:
            return None

        monkeypatch.setattr(manager, "_refresh", fake_refresh)
        await manager._async_set_advertising(_ADVERTISING_ADAPTER, True)
        members.clear()

        await manager._async_forget(device_address)

        assert members == [
            "RemoveDevice",
            "UnregisterAdvertisement",
            "RegisterAdvertisement",
        ]
        assert path in bus.exported
        assert _ADVERTISING_ADAPTER in manager._advertisements


class TestBluezRestart:
    """A restarted bluetoothd forgets everything registered with it."""

    @staticmethod
    def _owner_changed(name: str) -> Message:
        return Message.new_signal(
            path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus",
            member="NameOwnerChanged",
            signature="sss",
            body=[name, ":1.2", ":1.9"],
        )

    async def test_name_owner_changed_signals_a_restart(self) -> None:
        manager = BluezManager()
        manager._loop = asyncio.get_running_loop()
        manager._bluez_changed = asyncio.Event()

        assert manager._on_message(self._owner_changed("org.bluez")) is True
        await asyncio.sleep(0)

        assert manager._bluez_changed.is_set()

    async def test_name_owner_changed_for_other_services_is_ignored(
        self,
    ) -> None:
        manager = BluezManager()
        manager._loop = asyncio.get_running_loop()
        manager._bluez_changed = asyncio.Event()

        assert manager._on_message(self._owner_changed("org.example")) is False
        await asyncio.sleep(0)

        assert not manager._bluez_changed.is_set()

    def test_name_owner_changed_without_a_connection_is_harmless(
        self,
    ) -> None:
        manager = BluezManager()

        assert manager._on_message(self._owner_changed("org.bluez")) is True

    async def test_restore_re_registers_a_requested_advertisement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        members, bus, path = _install_advertising_fakes(manager, monkeypatch)
        manager._snapshot = {"adapters": [{"path": _ADVERTISING_ADAPTER}]}
        manager._advertising_adapters.add(_ADVERTISING_ADAPTER)

        await manager._restore_advertisements()

        assert members == ["RegisterAdvertisement"]
        assert path in bus.exported
        assert _ADVERTISING_ADAPTER in manager._advertisements

    async def test_restore_skips_an_adapter_that_is_gone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        members, _bus, _path = _install_advertising_fakes(manager, monkeypatch)
        manager._snapshot = {"adapters": [{"path": _ADVERTISING_ADAPTER}]}
        manager._advertising_adapters.add("/org/bluez/hci7")

        await manager._restore_advertisements()

        assert members == []

    async def test_disabling_advertising_drops_the_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = BluezManager()
        _install_advertising_fakes(manager, monkeypatch)

        await manager._async_set_advertising(_ADVERTISING_ADAPTER, True)
        assert _ADVERTISING_ADAPTER in manager._advertising_adapters

        await manager._async_set_advertising(_ADVERTISING_ADAPTER, False)
        assert _ADVERTISING_ADAPTER not in manager._advertising_adapters
