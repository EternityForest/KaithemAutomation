#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Expose a battery GATT service on a virtual BlueZ adapter.

This is a test helper for the Bluetooth console E2E test.  It registers a
standard Battery Service on an adapter created by ``btvirt`` so the host
side of a virtual pairing can discover and read a battery level.
"""

import argparse
import asyncio
import logging
import signal

from dbus_fast import BusType, Message, MessageType, Variant, unpack_variants
from dbus_fast.aio import MessageBus
from dbus_fast.service import (
    PropertyAccess,
    ServiceInterface,
    dbus_property,
    method,
)

logger = logging.getLogger("virtual_bluetooth_gatt")

BLUEZ_SERVICE = "org.bluez"
ADAPTER_INTERFACE = "org.bluez.Adapter1"
AGENT_INTERFACE = "org.bluez.Agent1"
BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
REGISTER_TIMEOUT = 20.0


class Application(ServiceInterface):
    def __init__(self, service_path: str, characteristic_path: str):
        super().__init__("org.freedesktop.DBus.ObjectManager")
        self._service_path = service_path
        self._characteristic_path = characteristic_path

    @method()
    def GetManagedObjects(self) -> "a{oa{sa{sv}}}":  # noqa: F722
        return {
            self._service_path: {
                "org.bluez.GattService1": {
                    "UUID": Variant("s", BATTERY_SERVICE_UUID),
                    "Primary": Variant("b", True),
                }
            },
            self._characteristic_path: {
                "org.bluez.GattCharacteristic1": {
                    "UUID": Variant("s", BATTERY_LEVEL_UUID),
                    "Service": Variant("o", self._service_path),
                    "Flags": Variant("as", ["read", "notify"]),
                }
            },
        }


class BatteryService(ServiceInterface):
    def __init__(self):
        super().__init__("org.bluez.GattService1")

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":  # noqa: F821
        return BATTERY_SERVICE_UUID

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> "b":  # noqa: F821
        return True


class BatteryLevel(ServiceInterface):
    def __init__(self, service_path: str, level: int):
        super().__init__("org.bluez.GattCharacteristic1")
        self._service_path = service_path
        self._level = level

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":  # noqa: F821
        return BATTERY_LEVEL_UUID

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":  # noqa: F821
        return self._service_path

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":  # noqa: F722
        return ["read", "notify"]

    @method()
    def ReadValue(self, options: "a{sv}") -> "ay":  # noqa: F722, F821
        logger.info("Battery level read: %s%%", self._level)
        # BlueZ marshals this as an ``ay`` (byte array); dbus-fast rejects
        # lists and needs an immutable ``bytes`` object.
        return bytes([self._level])

    @method()
    def StartNotify(self) -> None:
        pass

    @method()
    def StopNotify(self) -> None:
        pass


class AutoAcceptAgent(ServiceInterface):
    """Pairing agent for the peripheral side of the virtual link.

    The agent answers the prompts BlueZ routes to this D-Bus sender while the
    virtual peripheral is being paired.  It deliberately does not request the
    default-agent role: whichever process registers last would own every
    pairing prompt on the system, silently auto-accepting the prompts the
    console is supposed to show to the user.
    """

    def __init__(self):
        super().__init__(AGENT_INTERFACE)

    @method()
    def Release(self) -> None:
        logger.info("Pairing agent released")

    @method()
    def RequestConfirmation(
        self,
        device: "o",  # noqa: F821
        passkey: "u",  # noqa: F821
    ) -> None:
        logger.info("Auto-confirming pairing with %s", device)

    @method()
    def RequestAuthorization(self, device: "o") -> None:  # noqa: F821
        logger.info("Auto-authorizing %s", device)

    @method()
    def AuthorizeService(self, device: "o", uuid: "s") -> None:  # noqa: F821
        logger.info("Auto-authorizing service %s for %s", uuid, device)

    @method()
    def RequestPasskey(self, device: "o") -> "u":  # noqa: F821
        return 0

    @method()
    def RequestPinCode(self, device: "o") -> "s":  # noqa: F821
        return "0000"

    @method()
    def DisplayPasskey(
        self,
        device: "o",  # noqa: F821
        passkey: "u",  # noqa: F821
        entered: "q",  # noqa: F821
    ) -> None:
        logger.info("Display passkey for %s", device)

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s") -> None:  # noqa: F821
        logger.info("Display pin code for %s", device)


async def set_property(
    bus: MessageBus,
    path: str,
    interface: str,
    name: str,
    value: Variant,
) -> None:
    reply = await bus.call(
        Message(
            destination=BLUEZ_SERVICE,
            path=path,
            interface="org.freedesktop.DBus.Properties",
            member="Set",
            signature="ssv",
            body=[interface, name, value],
        )
    )
    if reply.message_type == MessageType.ERROR:
        raise RuntimeError(f"could not set {name}: {reply.error_name}")


async def configure_adapter(bus: MessageBus, adapter_path: str) -> None:
    """Power the peripheral so its GATT application can be registered.

    Discoverability, pairability, and advertising are deliberately left to the
    console under test: the E2E clicks "Make connectable" on this controller,
    which is the behaviour being verified.  BlueZ may not have exported the
    freshly created adapter yet, so retry until the property can be written.
    """
    deadline = asyncio.get_running_loop().time() + REGISTER_TIMEOUT
    properties = (("Powered", Variant("b", True)),)
    for name, value in properties:
        while True:
            try:
                await set_property(
                    bus, adapter_path, ADAPTER_INTERFACE, name, value
                )
                break
            except RuntimeError as exc:
                if asyncio.get_running_loop().time() >= deadline:
                    raise
                logger.info("Waiting to set %s: %s", name, exc)
                await asyncio.sleep(0.25)


async def register(bus: MessageBus, adapter_path: str, app_path: str) -> None:
    """Register the GATT application.

    BlueZ may not have exported the freshly created adapter yet, so retry
    until it appears.  BlueZ keeps the application registered across adapter
    power cycles, so nothing has to be done when the adapter comes back.
    """
    deadline = asyncio.get_running_loop().time() + REGISTER_TIMEOUT
    while True:
        reply = await bus.call(
            Message(
                destination=BLUEZ_SERVICE,
                path=adapter_path,
                interface="org.bluez.GattManager1",
                member="RegisterApplication",
                signature="oa{sv}",
                body=[app_path, {}],
            )
        )
        if reply.message_type != MessageType.ERROR:
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError(
                f"RegisterApplication failed: {reply.error_name}"
            )
        logger.info("Waiting for adapter %s", adapter_path)
        await asyncio.sleep(0.25)


async def register_agent(bus: MessageBus, agent_path: str) -> None:
    """Register an auto-accepting agent for this connection only.

    ``RequestDefaultAgent`` is intentionally absent: the console registers
    itself as the default agent so it can show pairing prompts to the user,
    and a second default agent would silently answer them instead.
    """
    reply = await bus.call(
        Message(
            destination=BLUEZ_SERVICE,
            path="/org/bluez",
            interface="org.bluez.AgentManager1",
            member="RegisterAgent",
            signature="os",
            body=[agent_path, "NoInputNoOutput"],
        )
    )
    if reply.message_type == MessageType.ERROR:
        logger.warning("RegisterAgent failed: %s", reply.error_name)


async def clear_peer_bonds(bus: MessageBus, adapter_path: str) -> None:
    """Forget peers this adapter still has a bond with.

    BlueZ keeps the pairing keys on both ends of a link.  When the host side
    forgets the device but the peripheral side keeps its bond, every later
    pairing attempt fails with ``Authentication Failed``: the peripheral tries
    to encrypt with keys the host has already discarded.  The virtual
    peripheral exists only for this test, so its peer list is always ours to
    clear.
    """
    reply = await bus.call(
        Message(
            destination=BLUEZ_SERVICE,
            path="/",
            interface="org.freedesktop.DBus.ObjectManager",
            member="GetManagedObjects",
        )
    )
    if reply.message_type == MessageType.ERROR:
        raise RuntimeError(f"GetManagedObjects failed: {reply.error_name}")
    objects = unpack_variants(reply.body[0])
    prefix = f"{adapter_path}/"
    for path, interfaces in objects.items():
        if not path.startswith(prefix):
            continue
        if "org.bluez.Device1" not in interfaces:
            continue
        logger.info("Forgetting leftover peer %s", path)
        removal = await bus.call(
            Message(
                destination=BLUEZ_SERVICE,
                path=adapter_path,
                interface=ADAPTER_INTERFACE,
                member="RemoveDevice",
                signature="o",
                body=[path],
            )
        )
        if removal.message_type == MessageType.ERROR:
            raise RuntimeError(
                f"RemoveDevice failed for {path}: {removal.error_name}"
            )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True, help="Adapter object path")
    parser.add_argument("--battery", type=int, default=42)
    arguments = parser.parse_args()

    if not 0 <= arguments.battery <= 100:
        raise SystemExit("--battery must be between 0 and 100")

    app_path = "/org/kaithem/test/battery"
    service_path = f"{app_path}/service0"
    characteristic_path = f"{service_path}/char0"
    agent_path = "/org/kaithem/test/agent"

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    bus.export(app_path, Application(service_path, characteristic_path))
    bus.export(service_path, BatteryService())
    bus.export(
        characteristic_path, BatteryLevel(service_path, arguments.battery)
    )
    bus.export(agent_path, AutoAcceptAgent())

    await configure_adapter(bus, arguments.adapter)
    await clear_peer_bonds(bus, arguments.adapter)
    await register(bus, arguments.adapter, app_path)
    await register_agent(bus, agent_path)
    print(f"ready {arguments.adapter} battery={arguments.battery}", flush=True)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    await stop.wait()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
