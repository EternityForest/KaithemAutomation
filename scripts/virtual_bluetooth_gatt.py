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

from dbus_fast import BusType, Message, MessageType, Variant
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
LOCAL_NAME = "KaithemBT"
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
        return [self._level]

    @method()
    def StartNotify(self) -> None:
        pass

    @method()
    def StopNotify(self) -> None:
        pass


class Advertisement(ServiceInterface):
    """Minimal LE advertisement for the battery peripheral.

    Only the Battery Service and the generic (unknown) appearance are
    advertised.  Audio UUIDs or an audio appearance would make the virtual
    device show up as a Bluetooth speaker in the host's audio stack.
    """

    def __init__(self):
        super().__init__("org.bluez.LEAdvertisement1")

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":  # noqa: F821
        return "peripheral"

    @dbus_property(access=PropertyAccess.READ)
    def Appearance(self) -> "q":  # noqa: F821
        # Generic "unknown" appearance.  Never advertise an audio appearance:
        # desktop audio stacks would surface the virtual device as a speaker.
        return 0

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> "s":  # noqa: F821
        return LOCAL_NAME

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> "as":  # noqa: F722
        return [BATTERY_SERVICE_UUID]

    @method()
    def Release(self) -> None:
        logger.info("Advertisement released")


class AutoAcceptAgent(ServiceInterface):
    """Pairing agent for the peripheral side of the virtual link.

    BlueZ registers a default agent when none is present, but registering one
    explicitly makes the test independent of that default and documents the
    capability we rely on.
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
    """Power the peripheral and make it discoverable and pairable.

    BlueZ may not have exported the freshly created adapter yet, so retry
    until the properties can be written.
    """
    deadline = asyncio.get_running_loop().time() + REGISTER_TIMEOUT
    properties = (
        ("Powered", Variant("b", True)),
        ("Discoverable", Variant("b", True)),
        ("Pairable", Variant("b", True)),
    )
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


async def register(
    bus: MessageBus, adapter_path: str, app_path: str, adv_path: str
) -> None:
    """Register the GATT application and advertisement.

    BlueZ may not have exported the freshly created adapter yet, so retry
    until it appears.
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
            break
        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError(f"RegisterApplication failed: {reply.body}")
        logger.info("Waiting for adapter %s", adapter_path)
        await asyncio.sleep(0.25)

    reply = await bus.call(
        Message(
            destination=BLUEZ_SERVICE,
            path=adapter_path,
            interface="org.bluez.LEAdvertisingManager1",
            member="RegisterAdvertisement",
            signature="oa{sv}",
            body=[adv_path, {}],
        )
    )
    if reply.message_type == MessageType.ERROR:
        raise RuntimeError(f"RegisterAdvertisement failed: {reply.body}")


async def register_agent(bus: MessageBus, agent_path: str) -> None:
    """Register an auto-accepting agent so the peripheral can be paired."""
    for member, signature, body in (
        ("RegisterAgent", "os", [agent_path, "NoInputNoOutput"]),
        ("RequestDefaultAgent", "o", [agent_path]),
    ):
        reply = await bus.call(
            Message(
                destination=BLUEZ_SERVICE,
                path="/org/bluez",
                interface="org.bluez.AgentManager1",
                member=member,
                signature=signature,
                body=body,
            )
        )
        if reply.message_type == MessageType.ERROR:
            logger.warning("%s failed: %s", member, reply.error_name)


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
    adv_path = f"{app_path}/advertisement0"
    agent_path = "/org/kaithem/test/agent"

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    bus.export(app_path, Application(service_path, characteristic_path))
    bus.export(service_path, BatteryService())
    bus.export(
        characteristic_path, BatteryLevel(service_path, arguments.battery)
    )
    bus.export(adv_path, Advertisement())
    bus.export(agent_path, AutoAcceptAgent())

    await configure_adapter(bus, arguments.adapter)
    await register(bus, arguments.adapter, app_path, adv_path)
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
