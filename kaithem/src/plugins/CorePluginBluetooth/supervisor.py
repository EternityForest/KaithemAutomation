# SPDX-License-Identifier: GPL-3.0-or-later
"""Server-side device supervision for the Bluetooth console.

This module owns per-device configuration, automatic reconnection, and
Kaithem alerts.  It has no Quart or Kaithem web imports so the web layer only
has to decorate snapshots and forward config updates.

Configuration lives in ``<vardir>/core.settings/bluetooth-<hostname>.json``.
The hostname disambiguates backups restored on machines with a different set
of paired devices.  Each device entry looks like::

    {"auto_connect": true, "alerts": false, "name": "headphones"}
"""

from __future__ import annotations

import copy
import json
import keyword
import logging
import os
import socket
import tempfile
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol, TypedDict

from kaithem.api.util import get_vardir
from kaithem.src import alerts

from .bluez import BluezError, BluezManager

logger = logging.getLogger(__name__)

CONFIG_VERSION = 1
TICK_INTERVAL = 5.0
CONNECT_COOLDOWN = 30.0
CONNECT_TIMEOUT = 30.0
LOW_BATTERY_PERCENT = 20
WEAK_RSSI_DBM = -68
MAX_NAME_LENGTH = 64

_CONFIG_KEYS = ("auto_connect", "alerts", "name")


class DeviceConfig(TypedDict):
    auto_connect: bool
    alerts: bool
    name: str | None


class AlertLike(Protocol):
    def trip(self, message: str = "") -> None: ...

    def clear(self) -> None: ...

    def close(self) -> None: ...


AlertFactory = Callable[[str, str, str], AlertLike]


def default_device_config() -> DeviceConfig:
    return {"auto_connect": False, "alerts": False, "name": None}


def _default_alert_factory(
    name: str, priority: str, description: str
) -> AlertLike:
    return alerts.Alert(
        name,
        priority=priority,
        description=description,
        trip_delay=10,
        auto_ack=True,
    )


def _normalize_address(address: str) -> str:
    return address.strip().upper()


def _valid_address(address: str) -> bool:
    if len(address) != 17:
        return False
    parts = address.split(":")
    return len(parts) == 6 and all(
        len(part) == 2 and all(char in "0123456789ABCDEF" for char in part)
        for part in parts
    )


def validate_local_name(name: Any) -> str | None:
    """Validate a user-facing local name against Python identifier rules."""
    if name is None:
        return None
    if not isinstance(name, str):
        raise BluezError("InvalidArguments", "Device name must be a string")
    stripped = name.strip()
    if stripped == "":
        return None
    if len(stripped) > MAX_NAME_LENGTH:
        raise BluezError(
            "InvalidArguments",
            f"Device name must be at most {MAX_NAME_LENGTH} characters",
        )
    if not stripped.isidentifier() or keyword.iskeyword(stripped):
        raise BluezError(
            "InvalidArguments",
            "Device name must be a Python identifier and not a keyword",
        )
    return stripped


class BluetoothSettings:
    """Load, validate, and atomically persist per-device configuration."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or default_settings_path()
        self._lock = threading.RLock()
        self._devices: dict[str, DeviceConfig] = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            self._devices = {}
            if not os.path.exists(self.path):
                return
            try:
                with open(self.path, encoding="utf-8") as file:
                    data = json.load(file)
            except (OSError, ValueError):
                logger.exception(
                    "Could not read Bluetooth settings from %s", self.path
                )
                return
            if not isinstance(data, dict):
                logger.error(
                    "Bluetooth settings in %s are not a JSON object",
                    self.path,
                )
                return
            raw_devices = data.get("devices")
            if not isinstance(raw_devices, dict):
                logger.error(
                    "Bluetooth settings in %s have no devices mapping",
                    self.path,
                )
                return
            for raw_address, raw_config in raw_devices.items():
                try:
                    address = _normalize_address(str(raw_address))
                    if not _valid_address(address):
                        raise ValueError(f"invalid address {raw_address!r}")
                    self._devices[address] = _parse_device_config(raw_config)
                except (TypeError, ValueError, BluezError):
                    logger.exception(
                        "Ignoring invalid Bluetooth config for %s",
                        raw_address,
                    )

    def configs(self) -> dict[str, DeviceConfig]:
        with self._lock:
            return copy.deepcopy(self._devices)

    def get(self, address: str) -> DeviceConfig | None:
        with self._lock:
            config = self._devices.get(_normalize_address(address))
            return copy.deepcopy(config) if config is not None else None

    def set(self, address: str, values: dict[str, Any]) -> DeviceConfig:
        """Apply a partial update and persist it."""
        normalized = _normalize_address(address)
        if not _valid_address(normalized):
            raise BluezError(
                "InvalidArguments", f"Invalid Bluetooth address {address}"
            )
        if not isinstance(values, dict):
            raise BluezError("InvalidArguments", "Config must be an object")
        with self._lock:
            current = self._devices.get(normalized) or default_device_config()
            merged = self._merge(normalized, current, values)
            new_devices = copy.deepcopy(self._devices)
            new_devices[normalized] = merged
            self._write(new_devices)
            self._devices = new_devices
            return copy.deepcopy(merged)

    def remove(self, address: str) -> bool:
        normalized = _normalize_address(address)
        with self._lock:
            if normalized not in self._devices:
                return False
            new_devices = copy.deepcopy(self._devices)
            del new_devices[normalized]
            self._write(new_devices)
            self._devices = new_devices
            return True

    def _merge(
        self,
        address: str,
        current: DeviceConfig,
        values: dict[str, Any],
    ) -> DeviceConfig:
        merged: DeviceConfig = copy.deepcopy(current)
        for key, raw in values.items():
            if key not in _CONFIG_KEYS:
                raise BluezError(
                    "InvalidArguments", f"Unknown device config key {key}"
                )
            if key in ("auto_connect", "alerts"):
                if not isinstance(raw, bool):
                    raise BluezError(
                        "InvalidArguments", f"{key} must be a boolean"
                    )
                merged[key] = raw
            else:
                merged["name"] = validate_local_name(raw)

        name = merged["name"]
        if name is not None:
            for other_address, other in self._devices.items():
                if (
                    other_address != address
                    and other["name"] is not None
                    and other["name"].lower() == name.lower()
                ):
                    raise BluezError(
                        "InvalidArguments",
                        f"Device name {name!r} is already in use",
                    )
        return merged

    def _write(self, devices: dict[str, DeviceConfig]) -> None:
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        payload = {"version": CONFIG_VERSION, "devices": devices}
        fd, temporary = tempfile.mkstemp(
            dir=directory, prefix=".bluetooth-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


def _parse_device_config(raw: Any) -> DeviceConfig:
    if not isinstance(raw, dict):
        raise TypeError("device config must be an object")
    unknown = set(raw) - set(_CONFIG_KEYS)
    if unknown:
        raise ValueError(f"unknown keys: {sorted(unknown)}")
    return {
        "auto_connect": _parse_bool(raw.get("auto_connect", False)),
        "alerts": _parse_bool(raw.get("alerts", False)),
        "name": validate_local_name(raw.get("name")),
    }


def _parse_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise TypeError("expected a boolean")
    return value


def default_settings_path() -> str:
    hostname = socket.gethostname() or "unknown"
    hostname = hostname.replace(os.sep, "_").replace("/", "_")
    return os.path.join(
        get_vardir(), "core.settings", f"bluetooth-{hostname}.json"
    )


class DeviceSupervisor:
    """Track one configured device's config and connection state."""

    def __init__(self, address: str, config: DeviceConfig) -> None:
        self.address = _normalize_address(address)
        self._lock = threading.RLock()
        self._config = copy.deepcopy(config)
        self._connected: bool | None = None

    @property
    def config(self) -> DeviceConfig:
        with self._lock:
            return copy.deepcopy(self._config)

    def update_config(self, config: DeviceConfig) -> None:
        with self._lock:
            self._config = copy.deepcopy(config)


class DeviceAlertsManager:
    """Turn device metadata and transitions into Kaithem alerts."""

    def __init__(self, alert_factory: AlertFactory | None = None) -> None:
        self._lock = threading.RLock()
        self._alert_factory = alert_factory or _default_alert_factory
        self._alerts: dict[str, dict[str, AlertLike]] = {}
        self._tripped: dict[str, set[str]] = {}

    def process_device_metadata(
        self,
        address: str,
        label: str,
        device: dict[str, Any] | None,
        enabled: bool,
    ) -> None:
        """Trip or clear alerts for one metadata update."""
        normalized = _normalize_address(address)
        with self._lock:
            if not enabled:
                self._clear(normalized)
                return

            if device is None:
                self._clear_alert(normalized, "battery")
                self._clear_alert(normalized, "rssi")
                self._trip(
                    normalized,
                    "disconnected",
                    "error",
                    f"{label} disconnected",
                    "The device is no longer connected.",
                    "Bluetooth device disconnected",
                )
                return

            battery = device.get("battery")
            if (
                isinstance(battery, (int, float))
                and battery < LOW_BATTERY_PERCENT
            ):
                self._trip(
                    normalized,
                    "battery",
                    "warning",
                    f"{label} battery low",
                    f"Battery is at {battery}% (below {LOW_BATTERY_PERCENT}%).",
                    "Low Bluetooth device battery",
                )
            else:
                self._clear_alert(normalized, "battery")

            rssi = device.get("rssi")
            connected = bool(device.get("connected"))
            if (
                connected
                and isinstance(rssi, (int, float))
                and rssi < WEAK_RSSI_DBM
            ):
                self._trip(
                    normalized,
                    "rssi",
                    "warning",
                    f"{label} signal weak",
                    f"RSSI is {rssi} dBm (below {WEAK_RSSI_DBM} dBm).",
                    "Weak Bluetooth signal",
                )
            else:
                self._clear_alert(normalized, "rssi")

            if not connected:
                self._trip(
                    normalized,
                    "disconnected",
                    "error",
                    f"{label} disconnected",
                    "The device is no longer connected.",
                    "Bluetooth device disconnected",
                )
            else:
                self._clear_alert(normalized, "disconnected")

    def clear_address(self, address: str) -> None:
        """Clear and close every alert owned by a device."""
        with self._lock:
            self._clear(_normalize_address(address))

    def _trip(
        self,
        address: str,
        key: str,
        priority: str,
        title: str,
        message: str,
        description: str,
    ) -> None:
        tripped = self._tripped.setdefault(address, set())
        if key in tripped:
            return
        alert = self._alert(address, key, priority, title, description)
        alert.trip(message)
        tripped.add(key)

    def _alert(
        self,
        address: str,
        key: str,
        priority: str,
        title: str,
        description: str,
    ) -> AlertLike:
        device_alerts = self._alerts.setdefault(address, {})
        if key not in device_alerts:
            device_alerts[key] = self._alert_factory(
                f"Bluetooth {address}: {title}", priority, description
            )
        return device_alerts[key]

    def _clear_alert(self, address: str, key: str) -> None:
        tripped = self._tripped.get(address)
        if tripped is None or key not in tripped:
            return
        tripped.discard(key)
        if not tripped:
            del self._tripped[address]
        device_alerts = self._alerts.get(address)
        if device_alerts is not None and key in device_alerts:
            device_alerts[key].clear()

    def _clear(self, address: str) -> None:
        self._tripped.pop(address, None)
        device_alerts = self._alerts.pop(address, None)
        if device_alerts is None:
            return
        for alert in device_alerts.values():
            alert.close()


class BluetoothSupervisor:
    """Own per-device supervisors, auto-connect, and periodic processing."""

    def __init__(
        self,
        manager: BluezManager,
        settings: BluetoothSettings | None = None,
        alerts_manager: DeviceAlertsManager | None = None,
        interval: float = TICK_INTERVAL,
        connect_cooldown: float = CONNECT_COOLDOWN,
        connect_timeout: float = CONNECT_TIMEOUT,
    ) -> None:
        self.manager = manager
        self.settings = settings or BluetoothSettings()
        self.alerts = alerts_manager or DeviceAlertsManager()
        self.interval = interval
        self.connect_cooldown = connect_cooldown
        self.connect_timeout = connect_timeout
        self._lock = threading.RLock()
        self._supervisors: dict[str, DeviceSupervisor] = {}
        self._attempting: set[str] = set()
        self._last_attempt: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = False
        self._listeners: set[Callable[[dict[str, Any]], None]] = set()
        self._sync_supervisors()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        self.manager.add_listener(self._on_manager_event)
        self._thread = threading.Thread(
            target=self._run,
            name="kaithem-bluetooth-supervisor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        self.manager.remove_listener(self._on_manager_event)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Bluetooth supervisor tick failed")
            self._wake_event.wait(self.interval)
            self._wake_event.clear()

    def _on_manager_event(self, event: dict[str, Any]) -> None:
        if event.get("type") == "snapshot":
            self._wake_event.set()

    def add_listener(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for supervisor events (config changes)."""
        with self._lock:
            self._listeners.add(listener)

    def remove_listener(
        self, listener: Callable[[dict[str, Any]], None]
    ) -> None:
        with self._lock:
            self._listeners.discard(listener)

    def _notify(self, event: dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Bluetooth supervisor listener failed")

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def get_device_config(self, address: str) -> DeviceConfig | None:
        """Return stored config for an address, or ``None`` if unset."""
        return self.settings.get(address)

    def update_device_config(
        self, address: str, values: dict[str, Any]
    ) -> DeviceConfig:
        config = self.settings.set(address, values)
        normalized = _normalize_address(address)
        with self._lock:
            supervisor = self._supervisors.get(normalized)
            if supervisor is None:
                self._supervisors[normalized] = DeviceSupervisor(
                    normalized, config
                )
            else:
                supervisor.update_config(config)
        if not config["alerts"]:
            self.alerts.clear_address(normalized)
        self._wake_event.set()
        self._notify_config(normalized, config)
        return config

    def remove_device(self, address: str) -> bool:
        normalized = _normalize_address(address)
        removed = self.settings.remove(normalized)
        with self._lock:
            self._supervisors.pop(normalized, None)
            self._attempting.discard(normalized)
            self._last_attempt.pop(normalized, None)
        self.alerts.clear_address(normalized)
        self._wake_event.set()
        self._notify_config(normalized, default_device_config())
        return removed

    def _notify_config(self, address: str, config: DeviceConfig) -> None:
        """Broadcast a config change followed by a full snapshot.

        The snapshot lets clients add or drop placeholders for configured
        devices that BlueZ does not report.
        """
        self._notify({"type": "config", "address": address, "config": config})
        self._notify(
            {
                "type": "snapshot",
                "snapshot": self.decorate_snapshot(self.manager.snapshot()),
            }
        )

    def decorate_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Attach config to every device and add unseen configured devices.

        Devices that BlueZ does not currently report still appear so their
        settings can be inspected or cleared, with ``seen`` set to ``False``.
        """
        result = copy.deepcopy(snapshot)
        configs = self.settings.configs()
        devices = result.get("devices")
        if not isinstance(devices, list):
            devices = []  # type: ignore
            result["devices"] = devices
        seen: set[str] = set()
        for device in devices:
            address = _normalize_address(str(device.get("address", "")))
            seen.add(address)
            device["config"] = copy.deepcopy(
                configs.get(address) or default_device_config()
            )
            device["seen"] = True
        for address in sorted(set(configs) - seen):
            devices.append(_unseen_device(address, configs[address]))
        return result

    # ------------------------------------------------------------------
    # Periodic processing
    # ------------------------------------------------------------------

    def tick(self) -> None:
        """Process one snapshot: transitions, alerts, and auto-connect."""
        snapshot = self.manager.snapshot()
        devices = {
            _normalize_address(str(device.get("address", ""))): device
            for device in snapshot.get("devices", [])
        }
        configs = self.settings.configs()
        self._sync_supervisors(configs)

        with self._lock:
            supervisors = list(self._supervisors.items())
        for address, supervisor in supervisors:
            device = devices.get(address)
            config = supervisor.config
            label = _device_label(address, device, config)
            self.alerts.process_device_metadata(
                address, label, device, config["alerts"]
            )
            if config["auto_connect"] and self._should_auto_connect(device):
                self._maybe_connect(address)

    def _sync_supervisors(
        self, configs: dict[str, DeviceConfig] | None = None
    ) -> None:
        configs = configs if configs is not None else self.settings.configs()
        with self._lock:
            for address, config in configs.items():
                existing = self._supervisors.get(address)
                if existing is None:
                    self._supervisors[address] = DeviceSupervisor(
                        address, config
                    )
                else:
                    existing.update_config(config)
            for address in list(self._supervisors):
                if address not in configs:
                    del self._supervisors[address]
                    self.alerts.clear_address(address)
                    self._attempting.discard(address)
                    self._last_attempt.pop(address, None)

    def _should_auto_connect(self, device: dict[str, Any] | None) -> bool:
        if device is None:
            return False
        return bool(
            device.get("paired")
            and not device.get("connected")
            and not device.get("blocked")
        )

    def _maybe_connect(self, address: str) -> None:
        now = time.monotonic()
        with self._lock:
            if address in self._attempting:
                return
            last = self._last_attempt.get(address, 0.0)
            if now - last < self.connect_cooldown:
                return
            self._attempting.add(address)
            self._last_attempt[address] = now
        threading.Thread(
            target=self._connect,
            args=(address,),
            name=f"kaithem-bluetooth-connect-{address}",
            daemon=True,
        ).start()

    def _connect(self, address: str) -> None:
        try:
            self.manager.connect(address, timeout=self.connect_timeout)
            logger.info("Auto-connected Bluetooth device %s", address)
        except BluezError as exc:
            logger.warning(
                "Auto-connect failed for %s: %s",
                address,
                exc.message or exc.name,
            )
        except Exception:
            logger.exception("Auto-connect failed for %s", address)
        finally:
            with self._lock:
                self._attempting.discard(address)
            self._wake_event.set()


def _unseen_device(address: str, config: DeviceConfig) -> dict[str, Any]:
    """Placeholder device for a configured address BlueZ cannot report."""
    return {
        "path": "",
        "adapter": None,
        "address": address,
        "name": None,
        "alias": None,
        "paired": False,
        "bonded": False,
        "trusted": False,
        "connected": False,
        "blocked": False,
        "rssi": None,
        "tx_power": None,
        "battery": None,
        "address_type": None,
        "icon": None,
        "class": None,
        "services_resolved": False,
        "uuids": [],
        "seen": False,
        "config": copy.deepcopy(config),
    }


def _device_label(
    address: str,
    device: dict[str, Any] | None,
    config: DeviceConfig,
) -> str:
    if config["name"]:
        return config["name"]
    if device is not None:
        for key in ("alias", "name"):
            value = device.get(key)
            if isinstance(value, str) and value:
                return value
    return address
