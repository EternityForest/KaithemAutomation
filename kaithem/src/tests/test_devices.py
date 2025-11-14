import gc
import os
import sys
import time

import yaml

if "--collect-only" not in sys.argv:  # pragma: no cover
    from kaithem.src import quart_app

    dir = "/dev/shm/kaithem_tests/"

    tc = quart_app.app.test_client()


# def test_error_in_device():
#     from scullery import messagebus

#     from kaithem.src import (
#         devices,
#         devices_interface,
#         modules,
#         modules_state,
#     )

#     n = "test" + str(time.time()).replace(".", "_")

#     modules.newModule(n)

#     assert n in modules_state.ActiveModules

#     devices_interface.create_device_from_kwargs(
#         module=n, resource="devtest", type="DemoDevice", name="pytest_demo2"
#     )

#     got_errs = [0]

#     def message_handler(toppic, data: str):
#         data = data.lower()
#         if "pytest_demo2" in data:
#             if "error" in data:
#                 got_errs[0] += 1

#     messagebus.subscribe("/system/notifications/errors", message_handler)

#     assert "pytest_demo2" in devices.devices_host.get_devices()

#     d = devices.devices_host.devices["pytest_demo2"]
#     d.set_data_point("test_error", 1)
#     time.sleep(0.5)
#     assert got_errs[0] == 1

#     # Only the first one goes to the notifications
#     d.set_data_point("test_error", 2)
#     time.sleep(0.5)
#     assert got_errs[0] == 1

#     modules.rmResource(n, "devtest")


def test_subdevice_loading():
    from kaithem.src import (
        devices,
        modules,
        modules_state,
    )

    n = "test" + str(time.time()).replace(".", "_")
    modules.newModule(n)
    assert n in modules_state.ActiveModules

    devcon_child = {
        "resource": {
            "type": "device",
        },
        "device": {
            "type": "DemoDevice",
            "name": "pytest_demo_parent/subdevice",
            "is_subdevice": True,
            "device.echo_number": 81,
        },
    }

    modules.createResource(n, "devtest", devcon_child)

    # Does't load till parent makes it
    assert "pytest_demo_parent/subdevice" not in devices.devices_host.devices
    assert "pytest_demo_parent/subdevice" in devices.device_data_cache

    devcon = {
        "resource": {
            "type": "device",
        },
        "device": {
            "type": "DemoDevice",
            "name": "pytest_demo_parent",
        },
    }

    modules.createResource(n, "devtest2", devcon)

    # System should look up the config when the device is made
    # TODO test init where they both get made at once
    dev = devices.devices_host.devices["pytest_demo_parent/subdevice"]
    assert dev.wait_device_ready().config["device.echo_number"] == 81


def test_make_demo_device():
    from kaithem.src import (
        devices,
        devices_interface,
        modules,
        modules_state,
        tagpoints,
    )

    n = "test" + str(time.time()).replace(".", "_")

    modules.newModule(n)

    assert n in modules_state.ActiveModules

    devices_interface.create_blank_device(
        module=n, resource="devtest", type="DemoDevice", name="pytest_demo"
    )

    assert "pytest_demo" in devices.devices_host.devices
    assert "pytest_demo" in devices.devices_host.get_devices()

    assert tagpoints.allTagsAtomic["/devices/pytest_demo.random"]().value
    assert tagpoints.allTagsAtomic["/devices/pytest_demo.random"]().value < 1

    assert tagpoints.allTagsAtomic[
        "/devices/pytest_demo/subdevice.random"
    ]().value

    devices.updateDevice(
        "pytest_demo",
        {
            "temp.kaithem.store_in_module": n,
            "temp.kaithem.store_in_resource": "devtest",
            "json": """{
                "device.fixed_number_multiplier": "10000909000",
                "type": "DemoDevice"
            }""",
        },
    )

    assert os.path.exists(os.path.join(dir, "modules/data/", n, "devtest.yaml"))

    with open(os.path.join(dir, "modules/data/", n, "devtest.yaml")) as f:
        lr = f.read()

    assert "10000909000" in lr

    assert (
        str(
            yaml.load(lr, yaml.SafeLoader)["device"][
                "device.fixed_number_multiplier"
            ]
        )
        == "10000909000"
    )

    assert tagpoints.allTagsAtomic["/devices/pytest_demo.random"]().value > 100

    devices.updateDevice(
        "pytest_demo/subdevice",
        {
            "temp.kaithem.store_in_module": n,
            "temp.kaithem.store_in_resource": "devtest_subdevice",
            "json": """{
                "device.echo_number": "6",
                "type": "DemoDevice"
            }""",
        },
    )

    assert (
        devices.devices_host.devices["pytest_demo/subdevice"].config[
            "device.echo_number"
        ]
        == "6"
    )

    devices_interface.delete_device("pytest_demo")

    gc.collect()
    gc.collect()
    time.sleep(0.2)

    assert "/devices/pytest_demo.random" not in tagpoints.allTags
    assert (
        "/devices/pytest_demo/subdevice.random" not in tagpoints.allTagsAtomic
    )

    assert "pytest_demo" not in devices.devices_host.devices
    assert "pytest_demo" not in devices.devices_host.get_devices()
    assert "pytest_demo/subdevice" not in devices.devices_host.devices

    assert "pytest_demo/subdevice" in devices.device_data_cache

    # Remake it
    devices_interface.create_blank_device(
        module=n, resource="devtest", type="DemoDevice", name="pytest_demo"
    )

    # Ensure it picks up config from the module
    assert (
        devices.devices_host.devices["pytest_demo/subdevice"].config[
            "device.echo_number"
        ]
        == "6"
    )

    devices_interface.delete_device("pytest_demo")

    assert "pytest_demo" not in devices.devices_host.devices
    assert "pytest_demo" not in devices.devices_host.get_devices()

    modules.rmResource(n, "devtest_subdevice")

    assert "pytest_demo/subdevice" not in devices.device_location_cache
    assert "pytest_demo/subdevice" not in devices.subdevice_data_cache

    assert not os.path.exists(
        os.path.join(dir, "modules/data/", n, "devtest.yaml")
    )
