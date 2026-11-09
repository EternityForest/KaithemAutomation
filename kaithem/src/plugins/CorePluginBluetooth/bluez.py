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

# Broadcast signals are only routed to a connection that subscribed to them
# with AddMatch; without these rules BlueZ's changes never reach us.
# BlueZ's ObjectManager root is "/", above the org.bluez device tree, so the
# Interfaces* rules must not be restricted to the /org/bluez namespace.
# NameOwnerChanged is how we notice that bluetoothd restarted: the system bus
# connection survives a daemon restart, but the daemon forgets every agent and
# advertisement registration it was holding for us.
_SIGNAL_MATCH_RULES = (
    "type='signal',sender='org.bluez',"
    "interface='org.freedesktop.DBus.Properties',"
    "member='PropertiesChanged',path_namespace='/org/bluez'",
    "type='signal',sender='org.bluez',"
    "interface='org.freedesktop.DBus.ObjectManager',"
    "member='InterfacesAdded'",
    "type='signal',sender='org.bluez',"
    "interface='org.freedesktop.DBus.ObjectManager',"
    "member='InterfacesRemoved'",
    "type='signal',sender='org.freedesktop.DBus',"
    "interface='org.freedesktop.DBus',member='NameOwnerChanged',"
    "arg0='org.bluez'",
)

# Signals are the primary update path.  Polling is only a safety net for
# changes BlueZ does not announce, so it slows down when nothing is happening.
IDLE_REFRESH_INTERVAL = 30.0
DISCOVERING_REFRESH_INTERVAL = 3.0
# Device properties arrive in bursts while scanning; coalesce them.
REFRESH_COALESCE_DELAY = 0.25

_DEVICE_INTERFACE = "org.bluez.Device1"
_ADAPTER_INTERFACE = "org.bluez.Adapter1"
_BATTERY_INTERFACE = "org.bluez.Battery1"
_LE_ADVERTISING_INTERFACE = "org.bluez.LEAdvertisingManager1"
_ADVERTISEMENT_INTERFACE = "org.bluez.LEAdvertisement1"
_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
_OBJECT_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"
_DBUS_INTERFACE = "org.freedesktop.DBus"

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


def _snapshot_signature(payload: dict[str, Any]) -> str:
    """Fingerprint the parts of a snapshot that represent actual state.

    ``updated`` and ``revision`` change on every poll, so including them would
    make every refresh look like a state change.
    """
    comparable = {
        key: value
        for key, value in payload.items()
        if key not in ("updated", "revision")
    }
    return json.dumps(comparable, sort_keys=True, default=str)


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
        self._refresh_lock: asyncio.Lock | None = None
        self._refresh_pending = False
        self._advertisements: dict[str, _LeAdvertisement] = {}
        # Adapters where the user asked this plugin to advertise.  The
        # registration itself lives in bluetoothd's memory, so the request has
        # to outlive a daemon restart for us to be able to restore it.
        self._advertising_adapters: set[str] = set()
        # Set by the org.bluez NameOwnerChanged signal so the connection loop
        # can rebuild everything the old bluetoothd process was holding.
        self._bluez_changed: asyncio.Event | None = None
        # Adapters where this connection holds its own discovery session.
        # BlueZ tracks discovery per D-Bus sender, so stopping discovery only
        # cancels our request and leaves other applications' scans running.
        self._discovery_adapters: set[str] = set()

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
        self._refresh_lock = asyncio.Lock()
        self._refresh_pending = False
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

            # Stay connected until shutdown, BlueZ goes away, or bluetoothd is
            # replaced by a new process.  bluetoothd restarts (and system-bus
            # connections drop) when adapters are powered down, so keep
            # reconnecting instead of going dead.
            assert self._bluez_changed is not None
            stop_waiter = asyncio.create_task(self._stop_event.wait())
            disconnect_waiter = asyncio.create_task(self._wait_for_disconnect())
            restart_waiter = asyncio.create_task(self._bluez_changed.wait())
            poll_waiter = asyncio.create_task(self._poll_loop())
            done, pending = await asyncio.wait(
                {stop_waiter, disconnect_waiter, restart_waiter, poll_waiter},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if self._stop_event.is_set():
                break
            if restart_waiter in done:
                logger.warning(
                    "BlueZ restarted; re-registering the agent and "
                    "advertisements"
                )
            else:
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

    async def _poll_loop(self) -> None:
        """Refresh periodically so changes never depend on signals alone."""
        while True:
            try:
                await asyncio.sleep(self._poll_interval())
                await self._refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Periodic BlueZ refresh failed")

    def _poll_interval(self) -> float:
        with self._lock:
            discovering = any(
                adapter.get("discovering")
                for adapter in self._snapshot.get("adapters", [])
            )
        return (
            DISCOVERING_REFRESH_INTERVAL
            if discovering
            else IDLE_REFRESH_INTERVAL
        )

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
            self._bluez_changed = None
            self._available = False
            if error is not None:
                self._error = error
            self._agent_registered = False
            self._advertisements.clear()
            snapshot = self._empty_snapshot(
                self._error, self._agent_registered, self._agent_error
            )
            event = self._publish_locked(snapshot)
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
        self._bluez_changed = asyncio.Event()
        bus.add_message_handler(self._on_message)
        await self._subscribe_signals(bus)

        self._agent_registered = await self._register_agent()
        await self._refresh()
        await self._restore_advertisements()

    async def _subscribe_signals(self, bus: MessageBus) -> None:
        """Ask the bus daemon to route BlueZ change signals to this connection.

        ``add_message_handler`` only sees messages the daemon already sent us;
        broadcast signals need a matching ``AddMatch`` rule.  Without this the
        cached snapshot only changes when something calls ``refresh()``.
        """
        for rule in _SIGNAL_MATCH_RULES:
            reply = await bus.call(
                Message(
                    destination="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    interface="org.freedesktop.DBus",
                    member="AddMatch",
                    signature="s",
                    body=[rule],
                )
            )
            if reply.message_type == MessageType.ERROR:
                message = reply.body[0] if reply.body else ""
                raise BluezError(
                    reply.error_name or "AddMatchFailed",
                    f"Could not subscribe to BlueZ signals: {message}",
                )

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
        """Start or stop this plugin's discovery session on one adapter.

        BlueZ tracks discovery per D-Bus sender, so stopping only ends the
        session opened by this manager.  Another application may keep the
        adapter's ``Discovering`` property set; snapshots expose that
        distinction as ``discovering_owned``.

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
        if message.interface == _DBUS_INTERFACE:
            return self._handle_name_owner_changed(message)
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
        path = message.path or ""
        if message.interface == _OBJECT_MANAGER_INTERFACE:
            # BlueZ's object manager root is "/", above the /org/bluez tree.
            if path != "/":
                return False
        elif path != BLUEZ_ROOT and not path.startswith(BLUEZ_ROOT + "/"):
            return False
        self._schedule_refresh()
        return True

    def _handle_name_owner_changed(self, message: Message) -> bool:
        """Notice that bluetoothd was restarted or stopped.

        The system-bus connection outlives the daemon, so only this signal
        reveals that the agent and advertisement registrations held by the old
        process are gone.
        """
        if message.member != "NameOwnerChanged":
            return False
        body = message.body
        if len(body) < 3 or body[0] != BLUEZ_SERVICE:
            return False
        event = self._bluez_changed
        loop = self._loop
        if event is None or loop is None or loop.is_closed():
            return True
        loop.call_soon_threadsafe(event.set)
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
        self._refresh_pending = True
        if self._refresh_task is not None and not self._refresh_task.done():
            return
        self._refresh_task = asyncio.create_task(self._delayed_refresh())

    async def _delayed_refresh(self) -> None:
        try:
            while self._refresh_pending:
                self._refresh_pending = False
                # Device properties often arrive in bursts; coalesce them.
                await asyncio.sleep(REFRESH_COALESCE_DELAY)
                await self._refresh()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to refresh BlueZ state")

    async def _refresh(self) -> None:
        lock = self._refresh_lock
        if lock is None:
            raise RuntimeError("BlueZ refresh lock is not initialised")
        async with lock:
            await self._refresh_locked()

    async def _refresh_locked(self) -> None:
        try:
            objects = await self._get_managed_objects()
        except BluezError as exc:
            with self._lock:
                self._available = False
                self._error = exc.message or exc.name
                snapshot = self._empty_snapshot(
                    self._error, self._agent_registered, self._agent_error
                )
                event = self._publish_locked(snapshot)
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
            "updated": time.time(),
        }
        with self._lock:
            self._available = True
            self._error = None
            self._device_paths = device_paths
            event = self._publish_locked(payload)
        if event is not None:
            self._notify(event)

    def _publish_locked(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Store a snapshot and return a change event, if its state changed."""
        signature = _snapshot_signature(payload)
        changed = signature != self._snapshot_signature
        self._snapshot_signature = signature
        if changed:
            self._revision += 1
        payload["revision"] = self._revision
        self._snapshot = copy.deepcopy(payload)
        if not changed:
            return None
        return {
            "type": "snapshot",
            "snapshot": copy.deepcopy(self._snapshot),
            "revision": self._revision,
        }

    def _parse_objects(
        self, objects: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
        adapters: list[dict[str, Any]] = []
        devices: list[dict[str, Any]] = []
        device_paths: dict[str, str] = {}
        released_advertisements: list[str] = []

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
                        logger.info(
                            "Advertisement on %s vanished (ActiveInstances=%s)",
                            path,
                            active_instances,
                        )
                        self._advertisements.pop(path, None)
                        released_advertisements.append(
                            self._advertisement_path(path)
                        )
                        advertising = False
                    powered = bool(adapter.get("Powered", False))
                    discovering = bool(adapter.get("Discovering", False))
                    if not (powered and discovering):
                        # BlueZ ends discovery when the adapter powers off
                        # or is removed, so forget the stale session.
                        self._discovery_adapters.discard(path)
                    discovering_owned = path in self._discovery_adapters
                adapters.append(
                    {
                        "path": path,
                        "address": adapter.get("Address"),
                        "address_type": adapter.get("AddressType"),
                        "name": adapter.get("Name"),
                        "alias": adapter.get("Alias"),
                        "class": adapter.get("Class"),
                        "powered": powered,
                        "discovering": discovering,
                        "discovering_owned": discovering_owned,
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

        for released_path in released_advertisements:
            # dbus-fast refuses to export a path twice, so a stale object
            # must go before advertising can be enabled again.
            self._unexport_quietly(released_path)

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
        """Start or stop this connection's own discovery session.

        BlueZ keeps one discovery session per D-Bus sender, and the adapter's
        ``Discovering`` property is true while *any* application scans.  This
        method therefore tracks the sessions it owns instead of trusting
        ``StopDiscovery`` to clear the adapter-wide flag.
        """
        if adapter:
            adapter_path = self._resolve_adapter_path(adapter)
        else:
            adapter_path = self._adapter_path()
        with self._lock:
            owned = adapter_path in self._discovery_adapters

        if discovering == owned:
            await self._refresh()
            return

        if discovering:
            try:
                await self._call(
                    _ADAPTER_INTERFACE, "StartDiscovery", adapter_path
                )
            except BluezError as exc:
                # InProgress means this connection already owns a session,
                # which is exactly the state we want.
                if exc.name != "org.bluez.Error.InProgress":
                    raise
            with self._lock:
                self._discovery_adapters.add(adapter_path)
            await self._refresh()
            with self._lock:
                entry = next(
                    (
                        item
                        for item in self._snapshot.get("adapters") or []
                        if item.get("path") == adapter_path
                    ),
                    None,
                )
            if entry is None or not entry.get("discovering"):
                with self._lock:
                    self._discovery_adapters.discard(adapter_path)
                raise BluezError(
                    "Failed",
                    f"BlueZ did not start discovery on {adapter_path}",
                )
            return

        try:
            await self._call(_ADAPTER_INTERFACE, "StopDiscovery", adapter_path)
        except BluezError as exc:
            # Only a missing session is benign; BlueZ may have dropped ours
            # when the adapter powered off.  Other failures are real.
            no_session = (
                exc.name == "org.bluez.Error.Failed"
                and exc.message == "No discovery started"
            )
            if not (no_session or exc.name == "org.bluez.Error.NotReady"):
                raise
        with self._lock:
            self._discovery_adapters.discard(adapter_path)
        await self._refresh()

    async def _async_pair(self, address: str) -> None:
        await self._run_device_operation("Pair", address)

    async def _async_connect(self, address: str) -> None:
        await self._run_device_operation("Connect", address)

    async def _async_disconnect(self, address: str) -> None:
        await self._run_device_operation("Disconnect", address)

    async def _run_device_operation(self, member: str, address: str) -> None:
        """Call a Device1 method and log how it ended.

        BlueZ blocks a Pair call until every pairing agent it asked has
        answered, so a prompt routed to another process looks like a hang.
        Recording the duration and outcome here is what makes that visible in
        the server log instead of only in the browser.
        """
        path = self._device_path(address)
        started = time.monotonic()
        logger.info("%s starting for %s (%s)", member, address, path)
        try:
            if member == "Disconnect":
                await self._call(_DEVICE_INTERFACE, member, path)
            else:
                await self._run_agent_operation(
                    self._call(_DEVICE_INTERFACE, member, path)
                )
        except BluezError as exc:
            logger.warning(
                "%s failed for %s after %.1fs: %s (%s)",
                member,
                address,
                time.monotonic() - started,
                exc.name,
                exc.message,
            )
            raise
        except Exception:
            logger.exception(
                "%s failed for %s after %.1fs",
                member,
                address,
                time.monotonic() - started,
            )
            raise
        logger.info(
            "%s finished for %s in %.1fs",
            member,
            address,
            time.monotonic() - started,
        )
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
        logger.info("Removing %s (%s) from %s", address, path, adapter_path)
        await self._call(
            _ADAPTER_INTERFACE,
            "RemoveDevice",
            adapter_path,
            signature="o",
            body=[path],
        )
        await self._refresh()
        # Removing a device can stop a peer adapter's advertisement while
        # BlueZ still counts the registration, which leaves the peer
        # undiscoverable.  Re-assert every advertisement we own.
        await self._async_reassert_advertisements()

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
        if not enabled:
            with self._lock:
                self._advertising_adapters.discard(adapter_path)
            await self._async_unregister_advertisement(adapter_path)
            return

        with self._lock:
            self._advertising_adapters.add(adapter_path)
        # The adapter may already advertise: BlueZ can keep counting a
        # registration while the radio stopped transmitting it.  Cycling the
        # advertisement is the only way to re-assert it, and it is cheap.
        await self._async_unregister_advertisement(adapter_path)

        bus = self._bus
        if bus is None:
            raise BluezUnavailableError("BlueZ is not available")
        path = self._advertisement_path(adapter_path)

        advertisement = _LeAdvertisement(self, adapter_path)
        try:
            bus.export(path, advertisement)
        except ValueError:
            # A stale object is still exported because a previous
            # registration ended without cleanup.  Replace it.
            self._unexport_quietly(path)
            bus.export(path, advertisement)
        try:
            await self._call(
                _LE_ADVERTISING_INTERFACE,
                "RegisterAdvertisement",
                adapter_path,
                signature="oa{sv}",
                body=[path, {}],
            )
        except BluezError as exc:
            if exc.name != "org.bluez.Error.AlreadyExists":
                self._unexport_quietly(path)
                raise
        with self._lock:
            self._advertisements[adapter_path] = advertisement

    async def _async_unregister_advertisement(self, adapter_path: str) -> None:
        with self._lock:
            registered = adapter_path in self._advertisements
        if not registered:
            return
        bus = self._bus
        if bus is None:
            raise BluezUnavailableError("BlueZ is not available")
        path = self._advertisement_path(adapter_path)
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

    async def _async_reassert_advertisements(self) -> None:
        """Re-register every advertisement this connection registered.

        BlueZ normally reports a dropped advertisement through ``Release()``,
        but a controller can stop transmitting while BlueZ still counts the
        registration.  Removing a device can leave a peer adapter in that
        state, so callers cycle the advertisements to restore them.
        """
        with self._lock:
            adapter_paths = list(self._advertisements)
        for adapter_path in adapter_paths:
            try:
                await self._async_set_advertising(adapter_path, True)
            except BluezError as exc:
                logger.warning(
                    "Could not re-register the advertisement on %s: %s",
                    adapter_path,
                    exc,
                )

    async def _restore_advertisements(self) -> None:
        """Re-apply advertising requests that outlived a bluetoothd restart.

        The registration is stored inside the daemon, so a restarted daemon
        silently drops it while the console still shows the adapter as
        advertising.
        """
        with self._lock:
            requested = set(self._advertising_adapters)
            live = {a["path"] for a in self._snapshot.get("adapters", [])}
        for adapter_path in sorted(requested & live):
            try:
                await self._async_set_advertising(adapter_path, True)
            except BluezError as exc:
                logger.warning(
                    "Could not restore the advertisement on %s: %s",
                    adapter_path,
                    exc,
                )

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
        logger.info("BlueZ released advertisement on %s", adapter_path)
        with self._lock:
            self._advertisements.pop(adapter_path, None)
        # BlueZ calls Release from a method handler on this object, so defer
        # the unexport until the reply has been sent.  A re-registration may
        # have exported a fresh object at the same path by then.
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._unexport_released, adapter_path)
        self._schedule_refresh()

    def _unexport_released(self, adapter_path: str) -> None:
        with self._lock:
            if adapter_path in self._advertisements:
                return
        self._unexport_quietly(self._advertisement_path(adapter_path))

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
            logger.info("Registered BlueZ pairing agent at %s", AGENT_PATH)
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
            logger.info(
                "Rejecting %s for %s: no pairing or connection in progress",
                kind,
                device_path,
            )
            raise DBusError(
                "org.bluez.Error.Rejected",
                "Rejected: no pairing or connection operation is in progress",
            )
        if not has_listener:
            logger.info(
                "Rejecting %s for %s: no Bluetooth console is connected",
                kind,
                device_path,
            )
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
