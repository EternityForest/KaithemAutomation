import gc
import os
import sys
import time

import yaml

if "--collect-only" not in sys.argv:
    from kaithem.src import quart_app

    dir = "/dev/shm/kaithem_tests/"

    tc = quart_app.app.test_client()


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

    devices_interface.create_device_from_kwargs(
        module=n, resource="devtest", type="DemoDevice", name="pytest_demo"
    )

    assert "pytest_demo" in devices.remote_devices
    assert "pytest_demo" in devices.remote_devices_atomic

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
            "device.fixed_number_multiplier": "10000909000",
            "type": "DemoDevice",
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

    assert tagpoints.allTagsAtomic["/devices/pytest_demo.random"]().value > 1

    devices_interface.delete_device("pytest_demo")

    gc.collect()
    gc.collect()
    time.sleep(0.2)

    assert "/devices/pytest_demo.random" not in tagpoints.allTags
    assert (
        "/devices/pytest_demo/subdevice.random" not in tagpoints.allTagsAtomic
    )

    assert "pytest_demo" not in devices.remote_devices
    assert "pytest_demo" not in devices.remote_devices_atomic

    assert len(devices.remote_devices) == 0
    assert len(devices.remote_devices_atomic) == 0

    assert not os.path.exists(
        os.path.join(dir, "modules/data/", n, "devtest.yaml")
    )
