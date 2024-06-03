import sys

if "--collect-only" not in sys.argv:
    from kaithem.src import quart_app

    dir = "/dev/shm/kaithem_tests/"

    tc = quart_app.app.test_client()


def test_make_demo_device():
    pass
    # n = "test" + str(time.time()).replace(".", "_")

    # c = run(tc.post("/modules/newmoduletarget", data={"name": n}))
    # assert c.status_code == 302

    # assert n in modules_state.ActiveModules

    # # Call methids the web normally would
    # d = devices_interface.WebDevices()

    # assert d.index()

    # try:
    #     d.createDevice("pytest_demo", module=n, resource="devtest", type="DemoDevice")
    # except cherrypy.HTTPRedirect:
    #     pass

    # assert "devtest" in webapproot.webapproot().modules.module(n)

    # assert d.index()
    # assert d.device("pytest_demo", "manage")

    # assert "pytest_demo" in devices.remote_devices
    # assert "pytest_demo" in devices.remote_devices_atomic

    # assert tagpoints.allTagsAtomic["/devices/pytest_demo.random"]().value
    # assert tagpoints.allTagsAtomic["/devices/pytest_demo.random"]().value < 1

    # assert tagpoints.allTagsAtomic["/devices/pytest_demo/subdevice.random"]().value

    # try:
    #     # Make the number really big, check that config takes effect
    #     d.updateDevice(
    #         "pytest_demo",
    #         type="DemoDevice",
    #         **{
    #             "temp.kaithem.store_in_module": n,
    #             "temp.kaithem.store_in_resource": "devtest",
    #             "device.fixed_number_multiplier": "10000909000",
    #         },
    #     )
    # except cherrypy.HTTPRedirect:
    #     pass

    # assert "10000909000" in d.device("pytest_demo", "manage")

    # assert os.path.exists(os.path.join(dir, "modules/data/", n, "devtest.yaml"))

    # with open(os.path.join(dir, "modules/data/", n, "devtest.yaml")) as f:
    #     lr = f.read()

    # assert str(yaml.load(lr, yaml.SafeLoader)["device"]["device.fixed_number_multiplier"]) == "10000909000"

    # assert tagpoints.allTagsAtomic["/devices/pytest_demo.random"]().value > 1

    # try:
    #     # Make the number really big, check that config takes effect
    #     d.deletetarget(name="pytest_demo")
    # except cherrypy.HTTPRedirect:
    #     pass

    # gc.collect()
    # gc.collect()
    # time.sleep(0.2)

    # assert "/devices/pytest_demo.random" not in tagpoints.allTags
    # assert "/devices/pytest_demo/subdevice.random" not in tagpoints.allTagsAtomic

    # assert "devtest" not in webapproot.webapproot().modules.module(n)

    # assert len(devices.remote_devices) == 0
    # assert len(devices.remote_devices_atomic) == 0

    # assert not os.path.exists(os.path.join(dir, "modules/data/", n, "devtest.yaml"))
