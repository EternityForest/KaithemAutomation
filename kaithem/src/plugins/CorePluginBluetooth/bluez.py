# SPDX-License-Identifier: GPL-3.0-or-later


import asyncio
import copy
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from dbus_fast import BusType, DBusError, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.annotations import (
    DBusObjectPath,
    DBusStr,
    DBusUInt16,
    DBusUInt32,
)
from dbus_fast.service import (
    PropertyAccess,
    ServiceInterface,
    dbus_property,
    method,
)
from dbus_fast.unpack import unpack_variants

logger = logging.getLogger(__name__)

BLUEZ_SERVICE = "org.bluez"
BLUEZ_ROOT = "/org/bluez"
AGENT_PATH = "/org/kaithem/bluetooth/agent1"
ADVERTISEMENT_ROOT = "/org/kaithem/bluetooth/advertisement"
AGENT_TIMEOUT = 90.0
PAIR_TIMEOUT = AGENT_TIMEOUT + 30.0
CALL_TIMEOUT = 20.0

_DEVICE_INTERFACE = "org.bluez.Device1"
_ADAPTER_INTERFACE = "org.bluez.Adapter1"
_BATTERY_INTERFACE = "org.bluez.Battery1"
_LE_ADVERTISING_INTERFACE = "org.bluez.LEAdvertisingManager1"
_ADVERTISEMENT_INTERFACE = "org.bluez.LEAdvertisement1"
_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
_OBJECT_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"

# Adapter1 properties the console is allowed to write, with their D-Bus
# signature.  BlueZ exposes Name as read-only; Alias is the writable name.
_ADAPTER_WRITABLE_PROPERTIES: dict[str, str] = {
    "Powered": "b",
    "Discoverable": "b",
    "Pairable": "b",
    "Alias": "s",
    "DiscoverableTimeout": "u",
    "PairableTimeout": "u",
}
_ADVERTISING_PROPERTY = "Advertising"

AgentListener = Callable[[dict[str, Any]], None]


class BluezError(Exception):
    """A D-Bus call to BlueZ failed."""

    def __init__(self, name: str, message: str = "") -> None:
        super().__init__(message or name)
        self.name = name
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.name, "message": self.message}


class BluezUnavailableError(BluezError):
    """BlueZ could not be reached on the system bus."""

    def __init__(self, message: str = "Bluetooth is not available") -> None:
        super().__init__("BluezUnavailable", message)


class _PendingAgentRequest:
    """One outstanding org.bluez.Agent1 prompt awaiting a UI response."""

    def __init__(
        self,
        kind: str,
        device_path: str,
        passkey: int | None = None,
        pin: str | None = None,
        uuid_value: str | None = None,
        entered: int | None = None,
    ) -> None:
        self.id = uuid.uuid4().hex
        self.kind = kind
        self.device_path = device_path
        self.passkey = passkey
        self.pin = pin
        self.uuid = uuid_value
        self.entered = entered
        self.event = asyncio.Event()
        self.accepted = False
        self.value: str | None = None
        self.resolved = False


class BluezManager:
    """Thread-safe facade over BlueZ on the system D-Bus."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus: MessageBus | None = None
        self._stop_event: asyncio.Event | None = None
        self._ready = threading.Event()

        self._available = False
        self._error: str | None = None
        self._agent_registered = False
        self._agent_error: str | None = None

        self._revision = 0
        self._snapshot: dict[str, Any] = self._empty_snapshot()
        self._snapshot_signature = ""
        self._device_paths: dict[str, str] = {}

        self._listeners: set[AgentListener] = set()
        self._pending: dict[str, _PendingAgentRequest] = {}
        self._active_operations = 0
        self._refresh_task: asyncio.Task[None] | None = None
        self._advertisements: dict[str, _LeAdvertisement] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def ensure_started(self) -> None:
        """Start the dedicated D-Bus thread if it is not already running."""
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._thread_main,
                name="kaithem-bluez",
                daemon=True,
            )
            self._thread.start()
        # Do not block forever on a missing system bus.
        self._ready.wait(5.0)

    def stop(self) -> None:
        """Ask the D-Bus thread to shut down.  Safe to call more than once."""
        with self._start_lock:
            loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._stop_loop)
        except RuntimeError:
            pass

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop
        try:
            loop.run_until_complete(self._async_main())
        except Exception:
            logger.exception("BlueZ D-Bus thread crashed")
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            loop.close()
            with self._lock:
                self._loop = None
                self._bus = None
                self._advertisements.clear()

    async def _async_main(self) -> None:
        self._stop_event = asyncio.Event()
        first_attempt = True
        while not self._stop_event.is_set():
            try:
                await self._connect_and_setup()
            except Exception as exc:
                logger.warning("Could not connect to BlueZ: %s", exc)
                self._teardown_bus(str(exc) or exc.__class__.__name__)
                if first_attempt:
                    self._ready.set()
                    first_attempt = False
                await self._wait_or_stop(10.0)
                continue

            if first_attempt:
                self._ready.set()
                first_attempt = False

            # Stay connected until shutdown or BlueZ goes away.  bluetoothd
            # restarts (and system-bus connections drop) when adapters are
            # powered down, so keep reconnecting instead of going dead.
            stop_waiter = asyncio.create_task(self._stop_event.wait())
            disconnect_waiter = asyncio.create_task(self._wait_for_disconnect())
            done, pending = await asyncio.wait(
                {stop_waiter, disconnect_waiter},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if self._stop_event.is_set():
                break
            logger.warning("Lost connection to BlueZ; reconnecting")
            self._teardown_bus("BlueZ connection lost")

        if first_attempt:
            self._ready.set()
        self._teardown_bus(None)
        if not self._stop_event.is_set():
            await self._stop_event.wait()

    async def _wait_for_disconnect(self) -> None:
        bus = self._bus
        if bus is None:
            return
        try:
            await bus.wait_for_disconnect()
        except Exception:
            pass

    async def _wait_or_stop(self, timeout: float) -> None:
        try:
            assert self._stop_event
            await asyncio.wait_for(self._stop_event.wait(), timeout=timeout)
        except TimeoutError:
            pass

    def _teardown_bus(self, error: str | None) -> None:
        """Drop the bus connection and publish an unavailable snapshot."""
        refresh_task = self._refresh_task
        self._refresh_task = None
        if refresh_task is not None and not refresh_task.done():
            refresh_task.cancel()
        with self._lock:
            bus = self._bus
            self._bus = None
            self._available = False
            if error is not None:
                self._error = error
            self._agent_registered = False
            self._advertisements.clear()
            self._snapshot_signature = ""
            snapshot = self._empty_snapshot(
                self._error, self._agent_registered, self._agent_error
            )
            changed = snapshot != self._snapshot
            self._snapshot = snapshot
            event = None
            if changed:
                self._revision += 1
                self._snapshot["revision"] = self._revision
                event = {
                    "type": "snapshot",
                    "snapshot": copy.deepcopy(self._snapshot),
                    "revision": self._revision,
                }
        if bus is not None:
            try:
                bus.disconnect()
            except Exception:
                pass
        if event is not None:
            self._notify(event)

    async def _connect_and_setup(self) -> None:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        with self._lock:
            self._bus = bus
            self._error = None
            self._advertisements.clear()
        bus.add_message_handler(self._on_message)

        self._agent_registered = await self._register_agent()
        await self._refresh()

    def _stop_loop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

    # ------------------------------------------------------------------
    # Public synchronous API
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of the last known BlueZ state."""
        self.ensure_started()
        with self._lock:
            return copy.deepcopy(self._snapshot)

    def pending_agent_requests(self) -> list[dict[str, Any]]:
        with self._lock:
            # Resolved prompts linger briefly until the waiting agent call
            # wakes up; never replay those to a reconnecting client.
            requests = [r for r in self._pending.values() if not r.resolved]
        return [self._agent_request_dict(req) for req in requests]

    def refresh(self) -> dict[str, Any]:
        """Force a fresh GetManagedObjects call and return the snapshot."""
        self._run(self._refresh(), CALL_TIMEOUT)
        return self.snapshot()

    def set_discovering(
        self, discovering: bool, adapter: str | None = None
    ) -> dict[str, Any]:
        """Start or stop discovery on one adapter.

        ``adapter`` may be an adapter address, ``hciN`` short name, or D-Bus
        object path.  When omitted, the first powered adapter is used.
        """
        self._run(
            self._async_set_discovering(discovering, adapter), CALL_TIMEOUT
        )
        return self.snapshot()

    def set_adapter_properties(
        self, identifier: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        """Set writable Adapter1 properties and/or LE advertising.

        ``identifier`` is an adapter address or D-Bus object path.  Supported
        keys are ``Powered``, ``Discoverable``, ``Pairable``, ``Alias``,
        ``DiscoverableTimeout``, ``PairableTimeout``, and the pseudo-property
        ``Advertising``.
        """
        self._run(
            self._async_set_adapter_properties(identifier, values), CALL_TIMEOUT
        )
        return self.snapshot()

    def pair(self, address: str) -> dict[str, Any]:
        self._run(self._async_pair(address), PAIR_TIMEOUT)
        return self.snapshot()

    def connect(
        self, address: str, timeout: float | None = None
    ) -> dict[str, Any]:
        self._run(
            self._async_connect(address),
            PAIR_TIMEOUT if timeout is None else timeout,
        )
        return self.snapshot()

    def disconnect(self, address: str) -> dict[str, Any]:
        self._run(self._async_disconnect(address), CALL_TIMEOUT)
        return self.snapshot()

    def set_trusted(self, address: str, trusted: bool) -> dict[str, Any]:
        self._run(self._async_set_trusted(address, trusted), CALL_TIMEOUT)
        return self.snapshot()

    def forget(self, address: str) -> dict[str, Any]:
        self._run(self._async_forget(address), CALL_TIMEOUT)
        return self.snapshot()

    def respond_to_agent_request(
        self, request_id: str, accepted: bool, value: str | None = None
    ) -> bool:
        """Resolve a pending pairing prompt from the UI.

        Returns ``False`` if the request is unknown or already resolved.
        """
        with self._lock:
            request = self._pending.get(request_id)
            if request is None or request.resolved:
                return False
            request.resolved = True
            request.accepted = accepted
            request.value = value
            loop = self._loop
        if loop is None or loop.is_closed():
            return False
        try:
            loop.call_soon_threadsafe(request.event.set)
        except RuntimeError:
            return False
        return True

    def add_listener(self, listener: AgentListener) -> None:
        with self._lock:
            self._listeners.add(listener)

    def remove_listener(self, listener: AgentListener) -> None:
        with self._lock:
            self._listeners.discard(listener)

    # ------------------------------------------------------------------
    # D-Bus plumbing
    # ------------------------------------------------------------------

    def _run(self, coro: Any, timeout: float) -> Any:
        self.ensure_started()
        with self._lock:
            loop = self._loop
            bus = self._bus
            error = self._error
        if loop is None or bus is None:
            raise BluezUnavailableError(error or "BlueZ is not available")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout)
        except TimeoutError:
            future.cancel()
            raise BluezError("Timeout", "BlueZ operation timed out") from None
        except Exception:
            raise

    async def _call(
        self,
        interface: str,
        member: str,
        path: str = BLUEZ_ROOT,
        signature: str = "",
        body: list[Any] | None = None,
        destination: str = BLUEZ_SERVICE,
    ) -> Any:
        bus = self._bus
        if bus is None:
            raise BluezUnavailableError("BlueZ is not available")
        reply = await bus.call(
            Message(
                destination=destination,
                path=path,
                interface=interface,
                member=member,
                signature=signature,
                body=body or [],
            )
        )
        if reply.message_type == MessageType.ERROR:
            message = reply.body[0] if reply.body else ""
            raise BluezError(reply.error_name or "UnknownError", str(message))
        return reply.body[0] if reply.body else None

    async def _get_managed_objects(self) -> dict[str, Any]:
        result = await self._call(
            _OBJECT_MANAGER_INTERFACE, "GetManagedObjects", "/"
        )
        return unpack_variants(result or {})

    def _on_message(self, message: Message) -> bool:
        if message.message_type != MessageType.SIGNAL:
            return False
        path = message.path or ""
        if not path.startswith(BLUEZ_ROOT + "/") and path != BLUEZ_ROOT:
            return False
        if message.interface not in (
            _OBJECT_MANAGER_INTERFACE,
            _PROPERTIES_INTERFACE,
            _DEVICE_INTERFACE,
            _ADAPTER_INTERFACE,
            _BATTERY_INTERFACE,
            _LE_ADVERTISING_INTERFACE,
        ):
            return False
        if message.member not in (
            "InterfacesAdded",
            "InterfacesRemoved",
            "PropertiesChanged",
        ):
            return False
        self._schedule_refresh()
        return True

    def _schedule_refresh(self) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._queue_refresh)
        except RuntimeError:
            pass

    def _queue_refresh(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            return
        self._refresh_task = asyncio.create_task(self._delayed_refresh())

    async def _delayed_refresh(self) -> None:
        # Device properties often arrive in bursts; coalesce them.
        await asyncio.sleep(0.25)
        try:
            await self._refresh()
        except Exception:
            logger.exception("Failed to refresh BlueZ state")

    async def _refresh(self) -> None:
        try:
            objects = await self._get_managed_objects()
        except BluezError as exc:
            with self._lock:
                self._available = False
                self._error = exc.message or exc.name
                snapshot = self._empty_snapshot(
                    self._error, self._agent_registered, self._agent_error
                )
                changed = snapshot != self._snapshot
                self._snapshot = snapshot
                if changed:
                    self._revision += 1
                    self._snapshot["revision"] = self._revision
                    event = {
                        "type": "snapshot",
                        "snapshot": copy.deepcopy(self._snapshot),
                        "revision": self._revision,
                    }
                else:
                    event = None
            if event is not None:
                self._notify(event)
            return

        adapters, devices, device_paths = self._parse_objects(objects)
        primary = next(
            (a for a in adapters if a.get("powered")),
            adapters[0] if adapters else None,
        )
        payload = {
            "available": True,
            "error": None,
            "agent_registered": self._agent_registered,
            "agent_error": self._agent_error,
            "adapters": adapters,
            "adapter": primary,
            "devices": devices,
            "revision": self._revision,
            "updated": time.time(),
        }
        signature = json.dumps(payload, sort_keys=True, default=str)
        with self._lock:
            self._available = True
            self._error = None
            changed = signature != self._snapshot_signature
            self._snapshot_signature = signature
            self._device_paths = device_paths
            if changed:
                self._revision += 1
                payload["revision"] = self._revision
                payload["updated"] = time.time()
                self._snapshot = payload
                event = {
                    "type": "snapshot",
                    "snapshot": copy.deepcopy(payload),
                    "revision": self._revision,
                }
            else:
                self._snapshot = payload
                self._snapshot["revision"] = self._revision
                self._snapshot["updated"] = self._snapshot.get(
                    "updated", time.time()
                )
                event = None
        if event is not None:
            self._notify(event)

    def _parse_objects(
        self, objects: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
        adapters: list[dict[str, Any]] = []
        devices: list[dict[str, Any]] = []
        device_paths: dict[str, str] = {}

        for path, interfaces in objects.items():
            adapter = interfaces.get(_ADAPTER_INTERFACE)
            if isinstance(adapter, dict):
                le_manager = interfaces.get(_LE_ADVERTISING_INTERFACE)
                le_supported = isinstance(le_manager, dict)
                active_instances = (
                    le_manager.get("ActiveInstances")
                    if isinstance(le_manager, dict)
                    else None
                )
                supported_instances = (
                    le_manager.get("SupportedInstances")
                    if isinstance(le_manager, dict)
                    else None
                )
                with self._lock:
                    advertising = path in self._advertisements
                    if advertising and not active_instances:
                        # BlueZ dropped it (e.g. the adapter was powered off).
                        self._advertisements.pop(path, None)
                        advertising = False
                adapters.append(
                    {
                        "path": path,
                        "address": adapter.get("Address"),
                        "address_type": adapter.get("AddressType"),
                        "name": adapter.get("Name"),
                        "alias": adapter.get("Alias"),
                        "class": adapter.get("Class"),
                        "powered": bool(adapter.get("Powered", False)),
                        "discovering": bool(adapter.get("Discovering", False)),
                        "discoverable": bool(
                            adapter.get("Discoverable", False)
                        ),
                        "discoverable_timeout": adapter.get(
                            "DiscoverableTimeout"
                        ),
                        "pairable": bool(adapter.get("Pairable", False)),
                        "pairable_timeout": adapter.get("PairableTimeout"),
                        "roles": list(adapter.get("Roles") or []),
                        "uuids": list(adapter.get("UUIDs") or []),
                        "le_advertising": le_supported,
                        "advertising": advertising,
                        "active_instances": active_instances,
                        "supported_instances": supported_instances,
                    }
                )

            device = interfaces.get(_DEVICE_INTERFACE)
            if not isinstance(device, dict):
                continue
            battery = interfaces.get(_BATTERY_INTERFACE)
            address = device.get("Address")
            if not isinstance(address, str):
                continue
            entry = {
                "path": path,
                "adapter": device.get("Adapter"),
                "address": address,
                "name": device.get("Name"),
                "alias": device.get("Alias"),
                "paired": bool(device.get("Paired", False)),
                "bonded": bool(device.get("Bonded", False)),
                "trusted": bool(device.get("Trusted", False)),
                "connected": bool(device.get("Connected", False)),
                "blocked": bool(device.get("Blocked", False)),
                "rssi": device.get("RSSI"),
                "tx_power": device.get("TxPower"),
                "battery": battery.get("Percentage")
                if isinstance(battery, dict)
                else None,
                "address_type": device.get("AddressType"),
                "icon": device.get("Icon"),
                "class": device.get("Class"),
                "services_resolved": bool(
                    device.get("ServicesResolved", False)
                ),
                "uuids": list(device.get("UUIDs") or []),
            }
            devices.append(entry)
            device_paths[address.upper()] = path

        adapters.sort(key=lambda a: a["path"])
        devices.sort(
            key=lambda d: (
                not d["connected"],
                not d["paired"],
                (d["alias"] or d["name"] or d["address"]).lower(),
            )
        )
        return adapters, devices, device_paths

    def _empty_snapshot(
        self,
        error: str | None = None,
        agent_registered: bool = False,
        agent_error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "available": False,
            "error": error,
            "agent_registered": agent_registered,
            "agent_error": agent_error,
            "adapters": [],
            "adapter": None,
            "devices": [],
            "revision": self._revision,
            "updated": time.time(),
        }

    def _notify(self, event: dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("BlueZ listener failed")

    # ------------------------------------------------------------------
    # Device operations
    # ------------------------------------------------------------------

    def _device_path(self, address: str) -> str:
        with self._lock:
            path = self._device_paths.get(address.upper())
        if path is None:
            raise BluezError(
                "NotFound", f"No Bluetooth device with address {address}"
            )
        return path

    def _adapter_path(self) -> str:
        with self._lock:
            adapters = self._snapshot.get("adapters") or []
        if not adapters:
            raise BluezError("NotFound", "No Bluetooth adapter found")
        powered = [a for a in adapters if a.get("powered")]
        return (powered or adapters)[0]["path"]

    def _resolve_adapter_path(self, identifier: str) -> str:
        """Resolve an adapter address, short name,
        or object path to its path."""
        with self._lock:
            adapters = self._snapshot.get("adapters") or []
        if identifier.startswith("/"):
            for adapter in adapters:
                if adapter["path"] == identifier:
                    return identifier
        else:
            for adapter in adapters:
                address = adapter.get("address") or ""
                short_name = adapter["path"].rsplit("/", 1)[-1]
                if (
                    address.upper() == identifier.upper()
                    or short_name == identifier
                ):
                    return adapter["path"]
        raise BluezError(
            "NotFound", f"No Bluetooth adapter matching {identifier}"
        )

    async def _async_set_discovering(
        self, discovering: bool, adapter: str | None = None
    ) -> None:
        if adapter:
            adapter_path = self._resolve_adapter_path(adapter)
        else:
            adapter_path = self._adapter_path()
        member = "StartDiscovery" if discovering else "StopDiscovery"
        try:
            await self._call(_ADAPTER_INTERFACE, member, adapter_path)
        except BluezError as exc:
            # Already in the requested state is not an error for the UI.
            ignored = (
                {"org.bluez.Error.InProgress", "org.bluez.Error.AlreadyExists"}
                if discovering
                else {
                    "org.bluez.Error.NotReady",
                    "org.bluez.Error.Failed",
                    "org.bluez.Error.NotConnected",
                }
            )
            if exc.name not in ignored:
                raise
        await self._refresh()

    async def _async_pair(self, address: str) -> None:
        path = self._device_path(address)
        await self._run_agent_operation(
            self._call(_DEVICE_INTERFACE, "Pair", path)
        )
        await self._refresh()

    async def _async_connect(self, address: str) -> None:
        path = self._device_path(address)
        await self._run_agent_operation(
            self._call(_DEVICE_INTERFACE, "Connect", path)
        )
        await self._refresh()

    async def _async_disconnect(self, address: str) -> None:
        path = self._device_path(address)
        await self._call(_DEVICE_INTERFACE, "Disconnect", path)
        await self._refresh()

    async def _async_set_trusted(self, address: str, trusted: bool) -> None:
        path = self._device_path(address)
        await self._call(
            _PROPERTIES_INTERFACE,
            "Set",
            path,
            signature="ssv",
            body=[_DEVICE_INTERFACE, "Trusted", Variant("b", trusted)],
        )
        await self._refresh()

    async def _async_forget(self, address: str) -> None:
        path = self._device_path(address)
        with self._lock:
            device = next(
                (
                    d
                    for d in self._snapshot.get("devices", [])
                    if d["address"].upper() == address.upper()
                ),
                None,
            )
        adapter_path = (device or {}).get("adapter") or self._adapter_path()
        await self._call(
            _ADAPTER_INTERFACE,
            "RemoveDevice",
            adapter_path,
            signature="o",
            body=[path],
        )
        await self._refresh()

    async def _async_set_adapter_properties(
        self, identifier: str, values: dict[str, Any]
    ) -> None:
        adapter_path = self._resolve_adapter_path(identifier)
        advertising_requested: bool | None = None
        normalized: list[tuple[str, str, Any]] = []

        for key, raw in values.items():
            if key == _ADVERTISING_PROPERTY:
                if not isinstance(raw, bool):
                    raise BluezError(
                        "InvalidArguments",
                        f"Adapter property {key} must be a boolean",
                    )
                advertising_requested = raw
                continue
            signature = _ADAPTER_WRITABLE_PROPERTIES.get(key)
            if signature is None:
                raise BluezError(
                    "InvalidArguments",
                    f"Adapter property {key} is not writable",
                )
            if signature == "b":
                if not isinstance(raw, bool):
                    raise BluezError(
                        "InvalidArguments",
                        f"Adapter property {key} must be a boolean",
                    )
                value: Any = raw
            elif signature == "s":
                if not isinstance(raw, str):
                    raise BluezError(
                        "InvalidArguments",
                        f"Adapter property {key} must be a string",
                    )
                value = raw
            else:  # "u"
                if isinstance(raw, bool) or not isinstance(raw, int):
                    raise BluezError(
                        "InvalidArguments",
                        f"Adapter property {key} must be an integer",
                    )
                if raw < 0 or raw > 0xFFFFFFFF:
                    raise BluezError(
                        "InvalidArguments",
                        f"Adapter property {key} is out of range",
                    )
                value = raw
            normalized.append((key, signature, value))

        powering_off = any(
            key == "Powered" and value is False
            for key, _signature, value in normalized
        )
        if powering_off:
            if advertising_requested:
                raise BluezError(
                    "InvalidArguments",
                    "An adapter cannot advertise while being powered off",
                )
            # bluetoothd on this system crashes if an adapter is powered off
            # while one of our advertisements is still registered.
            await self._async_set_advertising(adapter_path, False)

        # Power on first so the remaining properties apply to a live adapter.
        normalized.sort(key=lambda item: item[0] != "Powered")
        for key, signature, value in normalized:
            await self._call(
                _PROPERTIES_INTERFACE,
                "Set",
                adapter_path,
                signature="ssv",
                body=[_ADAPTER_INTERFACE, key, Variant(signature, value)],
            )

        if advertising_requested is not None:
            await self._async_set_advertising(
                adapter_path, advertising_requested
            )
        await self._refresh()

    async def _async_set_advertising(
        self, adapter_path: str, enabled: bool
    ) -> None:
        with self._lock:
            currently = adapter_path in self._advertisements
        if currently == enabled:
            return

        bus = self._bus
        if bus is None:
            raise BluezUnavailableError("BlueZ is not available")
        path = self._advertisement_path(adapter_path)

        if enabled:
            advertisement = _LeAdvertisement(self, adapter_path)
            bus.export(path, advertisement)
            try:
                await self._call(
                    _LE_ADVERTISING_INTERFACE,
                    "RegisterAdvertisement",
                    adapter_path,
                    signature="oa{sv}",
                    body=[path, {}],
                )
            except BluezError:
                self._unexport_quietly(path)
                raise
            with self._lock:
                self._advertisements[adapter_path] = advertisement
            return

        with self._lock:
            self._advertisements.pop(adapter_path, None)
        try:
            await self._call(
                _LE_ADVERTISING_INTERFACE,
                "UnregisterAdvertisement",
                adapter_path,
                signature="o",
                body=[path],
            )
        except BluezError as exc:
            if exc.name not in (
                "org.bluez.Error.DoesNotExist",
                "org.bluez.Error.NotReady",
                "org.bluez.Error.Failed",
            ):
                raise
        finally:
            self._unexport_quietly(path)

    def _advertisement_path(self, adapter_path: str) -> str:
        suffix = adapter_path.rsplit("/", 1)[-1] or "adapter"
        return f"{ADVERTISEMENT_ROOT}/{suffix}"

    def _unexport_quietly(self, path: str) -> None:
        bus = self._bus
        if bus is None:
            return
        try:
            bus.unexport(path)
        except Exception:
            pass

    def _on_advertisement_released(self, adapter_path: str) -> None:
        with self._lock:
            self._advertisements.pop(adapter_path, None)
        self._schedule_refresh()

    async def _run_agent_operation(self, coro: Any) -> None:
        with self._lock:
            self._active_operations += 1
        try:
            await coro
        finally:
            with self._lock:
                self._active_operations -= 1

    # ------------------------------------------------------------------
    # org.bluez.Agent1
    # ------------------------------------------------------------------

    async def _register_agent(self) -> bool:
        agent = _BluezAgent(self)
        bus = self._bus
        if bus is None:
            return False
        try:
            bus.export(AGENT_PATH, agent)
            await self._call(
                "org.bluez.AgentManager1",
                "RegisterAgent",
                BLUEZ_ROOT,
                signature="os",
                body=[AGENT_PATH, "KeyboardDisplay"],
            )
            await self._call(
                "org.bluez.AgentManager1",
                "RequestDefaultAgent",
                BLUEZ_ROOT,
                signature="o",
                body=[AGENT_PATH],
            )
            self._agent_error = None
            return True  # noqa: TRY300
        except BluezError as exc:
            self._agent_error = exc.message or exc.name
            logger.warning(
                "Could not register BlueZ pairing agent: %s", self._agent_error
            )
            return False
        except Exception as exc:
            self._agent_error = str(exc)
            logger.exception("Could not register BlueZ pairing agent")
            return False

    def _agent_request_dict(
        self, request: _PendingAgentRequest
    ) -> dict[str, Any]:
        with self._lock:
            snapshot = self._snapshot
            device = next(
                (
                    d
                    for d in snapshot.get("devices", [])
                    if d["path"] == request.device_path
                ),
                None,
            )
        return {
            "id": request.id,
            "kind": request.kind,
            "device_path": request.device_path,
            "address": (device or {}).get("address"),
            "name": (device or {}).get("alias") or (device or {}).get("name"),
            "passkey": request.passkey,
            "pin": request.pin,
            "uuid": request.uuid,
            "entered": request.entered,
        }

    def _notify_agent_display(
        self,
        kind: str,
        device_path: str,
        passkey: int | None = None,
        pin: str | None = None,
        entered: int | None = None,
    ) -> None:
        request = _PendingAgentRequest(
            kind,
            device_path,
            passkey=passkey,
            pin=pin,
            entered=entered,
        )
        self._notify(
            {
                "type": "agent_display",
                "request": self._agent_request_dict(request),
            }
        )

    async def _agent_request(
        self,
        kind: str,
        device_path: str,
        passkey: int | None = None,
        uuid_value: str | None = None,
    ) -> str | int | None:
        with self._lock:
            active = self._active_operations > 0
            has_listener = bool(self._listeners)
        if not active:
            raise DBusError(
                "org.bluez.Error.Rejected",
                "Rejected: no pairing or connection operation is in progress",
            )
        if not has_listener:
            raise DBusError(
                "org.bluez.Error.Rejected",
                "Rejected: no Bluetooth console is connected",
            )

        request = _PendingAgentRequest(
            kind, device_path, passkey=passkey, uuid_value=uuid_value
        )
        with self._lock:
            self._pending[request.id] = request
        request_dict = self._agent_request_dict(request)
        self._notify({"type": "agent_request", "request": request_dict})

        try:
            await asyncio.wait_for(request.event.wait(), timeout=AGENT_TIMEOUT)
        except TimeoutError:
            with self._lock:
                request.resolved = True
                self._pending.pop(request.id, None)
            self._notify(
                {
                    "type": "agent_resolved",
                    "id": request.id,
                    "accepted": False,
                    "kind": kind,
                    "reason": "timeout",
                }
            )
            raise DBusError(
                "org.bluez.Error.Rejected", "Rejected: pairing prompt timed out"
            ) from None
        finally:
            with self._lock:
                self._pending.pop(request.id, None)

        self._notify(
            {
                "type": "agent_resolved",
                "id": request.id,
                "accepted": request.accepted,
                "kind": kind,
            }
        )
        if not request.accepted:
            raise DBusError("org.bluez.Error.Rejected", "Rejected by user")

        if kind == "pin":
            if not request.value:
                raise DBusError("org.bluez.Error.Rejected", "No PIN supplied")
            return request.value
        if kind == "passkey":
            try:
                return int(request.value or "")
            except ValueError:
                raise DBusError(
                    "org.bluez.Error.Rejected", "Invalid passkey supplied"
                ) from None
        return None

    def _cancel_agent_requests(self) -> None:
        with self._lock:
            requests = list(self._pending.values())
            self._pending.clear()
        for request in requests:
            if request.resolved:
                continue
            request.resolved = True
            request.accepted = False
            loop = self._loop
            if loop is not None and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(request.event.set)
                except RuntimeError:
                    pass
            self._notify(
                {
                    "type": "agent_resolved",
                    "id": request.id,
                    "accepted": False,
                    "kind": request.kind,
                    "reason": "cancelled",
                }
            )


class _BluezAgent(ServiceInterface):
    """The org.bluez.Agent1 object that BlueZ calls for pairing prompts."""

    def __init__(self, manager: BluezManager) -> None:
        super().__init__("org.bluez.Agent1")
        self.manager = manager

    @method()
    def Release(self) -> None:
        self.manager._cancel_agent_requests()

    @method()
    def Cancel(self) -> None:
        self.manager._cancel_agent_requests()

    @method()
    async def RequestPinCode(
        self,
        device: DBusObjectPath,  # type: ignore[valid-type]
    ) -> DBusStr:  # type: ignore[valid-type]
        result = await self.manager._agent_request("pin", device)
        if not isinstance(result, str):
            raise DBusError("org.bluez.Error.Rejected", "No PIN supplied")
        return result

    @method()
    async def RequestPasskey(
        self,
        device: DBusObjectPath,  # type: ignore[valid-type]
    ) -> DBusUInt32:  # type: ignore[valid-type]
        result = await self.manager._agent_request("passkey", device)
        if not isinstance(result, int):
            raise DBusError("org.bluez.Error.Rejected", "No passkey supplied")
        return result

    @method()
    async def DisplayPinCode(
        self,
        device: DBusObjectPath,  # type: ignore[valid-type]
        pincode: DBusStr,  # type: ignore[valid-type]
    ) -> None:
        self.manager._notify_agent_display("display_pin", device, pin=pincode)

    @method()
    async def DisplayPasskey(
        self,
        device: DBusObjectPath,  # type: ignore[valid-type]
        passkey: DBusUInt32,  # type: ignore[valid-type]
        entered: DBusUInt16,  # type: ignore[valid-type]
    ) -> None:
        self.manager._notify_agent_display(
            "display_passkey", device, passkey=passkey, entered=entered
        )

    @method()
    async def RequestConfirmation(
        self,
        device: DBusObjectPath,  # type: ignore[valid-type]
        passkey: DBusUInt32,  # type: ignore[valid-type]
    ) -> None:
        await self.manager._agent_request("confirm", device, passkey=passkey)

    @method()
    async def RequestAuthorization(
        self,
        device: DBusObjectPath,  # type: ignore[valid-type]
    ) -> None:
        await self.manager._agent_request("authorize", device)

    @method()
    async def AuthorizeService(
        self,
        device: DBusObjectPath,  # type: ignore[valid-type]
        uuid: DBusStr,  # type: ignore[valid-type]
    ) -> None:
        return None
        # await self.manager._agent_request(
        #     "authorize_service", device, uuid_value=uuid
        # )


class _LeAdvertisement(ServiceInterface):
    """Minimal org.bluez.LEAdvertisement1 object used for connectability.

    Registering this with ``LEAdvertisingManager1`` makes the adapter emit an
    advertising packet that includes the local name, which is what a peer needs
    to discover and initiate a connection.
    """

    def __init__(self, manager: BluezManager, adapter_path: str) -> None:
        super().__init__(_ADVERTISEMENT_INTERFACE)
        self.manager = manager
        self.adapter_path = adapter_path

    @dbus_property(access=PropertyAccess.READ)
    # pyrefly: ignore [unknown-name]
    def Type(self) -> "s":  # noqa: F821
        return "peripheral"

    @dbus_property(access=PropertyAccess.READ)
    # pyrefly: ignore [not-a-type]
    def Includes(self) -> "as":  # noqa: F722
        return ["local-name"]

    @method()
    def Release(self) -> None:
        self.manager._on_advertisement_released(self.adapter_path)
