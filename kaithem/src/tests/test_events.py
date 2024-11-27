import sys
import time
import weakref

if "--collect-only" not in sys.argv:
    from kaithem.src import messagebus, modules_state
    from kaithem.src.plugins import CorePluginEventResources


def test_events():
    modules_state.scopes["x"] = {}
    # Create an event that sets y to 0 if it is 1
    with CorePluginEventResources._event_list_lock:
        x = CorePluginEventResources.Event("y==1", "global y\ny=0", setup="y=0")
        x.module = x.resource = "pytest_testevt"
        CorePluginEventResources._events_by_module_resource[
            x.module, x.resource
        ] = x

        # Register event with polling.
        x.register()
    # Set y to 1
    x.pymodule.y = 1

    time.sleep(1)

    try:
        # y should immediately be set back to 0 at the next polling cycle
        if x.pymodule.y == 1:
            raise RuntimeError("Edge-Triggered Event did nothing")
    except Exception:
        print(x.pymodule.__dict__)
        raise
    finally:
        x.unregister()

    # TODO test that it goes away

    blah = [False]

    def f():
        return blah[0]

    def g():
        blah[0] = False

    CorePluginEventResources.when(f, g)
    time.sleep(0.5)
    blah[0] = True

    time.sleep(0.5)
    if blah[0]:
        time.sleep(2)
        if blah[0]:
            raise RuntimeError("One time event did not trigger")

    blah[0] = True
    time.sleep(1)
    if not blah[0]:
        raise RuntimeError("One time event did not delete itself properly")

    CorePluginEventResources.after(1, g)
    blah[0] = True
    time.sleep(0.5)
    if not blah[0]:
        raise RuntimeError("Time delay triggered too soon")

    time.sleep(1.5)
    if blah[0]:
        raise RuntimeError("Time delay event did not trigger")

    blah[0] = True
    time.sleep(1)
    if not blah[0]:
        raise RuntimeError("Time delay event did not delete itself properly")

    with CorePluginEventResources._event_list_lock:
        # Same exact thing exept we use the onchange
        x = CorePluginEventResources.Event("!onchange y", "global y\ny=5")
        # Give it a value to change from
        x.pymodule.y = 0

        x.module = x.resource = "pytest_TEST1"
        CorePluginEventResources._events_by_module_resource[
            x.module, x.resource
        ] = x

        # Register event with polling.
        x.register()

    # Let it notice the old value
    time.sleep(1)
    # Set y to 1
    x.pymodule.y = 1

    time.sleep(1)
    # y should immediately be set back to 0 at the next polling cycle
    x.unregister()

    if x.pymodule.y == 1:
        raise RuntimeError("Onchange Event did nothing")

    x.pymodule.y = 1
    if not x.pymodule.y == 1:
        raise RuntimeError("Onchange Event did not go away when unregistered")

    # There is a weird old feature where message events don't work if not in _events_by_module_resource
    # It was an old thing to caths a circular reference bug.
    with CorePluginEventResources._event_list_lock:
        # Now we test the message bus event
        x = CorePluginEventResources.Event(
            "!onmsg /system/selftest",
            "global y\ny='test'",
            setup="testObj=lambda x:0",
        )
        x.module = x.resource = "pytest_TEST2"
        # Make sure nobody is iterating the eventlist
        # Add new event
        x.register()
        # Update index
        CorePluginEventResources._events_by_module_resource[
            x.module, x.resource
        ] = x

    testObj = weakref.ref(x.pymodule.__dict__["testObj"])

    time.sleep(0.25)
    # Give it a value to change from
    messagebus.post_message("/system/selftest", "foo")
    # Let it notice the old value

    time.sleep(0.25)
    x.unregister()

    if not hasattr(x.pymodule, "y"):
        time.sleep(5)
        if not hasattr(x.pymodule, "y"):
            raise RuntimeError(
                "Message Event did nothing or took longer than 5s"
            )
        else:
            raise RuntimeError(
                "Message Event had slow performance, delivery took more than 0.25s"
            )

    assert x.pymodule.y == "test"

    try:
        x.pymodule.y = 1
    except Exception:
        # This might fail if the implementatino makes pymodule not exist anymore
        pass

    # Assert that after unregister, it no longer fires
    messagebus.post_message("/system/selftest", "foo")
    time.sleep(2)
    assert x.pymodule.y == 1

    x.cleanup()

    # Make sure the weakref isn't referencing
    if testObj():
        import gc

        gc.collect(0)
        gc.collect(1)
        gc.collect(2)
        gc.collect(0)
        gc.collect(1)
        gc.collect(2)
        if testObj():
            raise RuntimeError(
                "Object in event scope still exists after module deletion and GC"
            )

    messagebus.post_message("foo", "/system/selftest")
    # If there is no y or pymodule, this test won't work but we can probably assume it unregistered correctly.
    # Maybe we should add a real test that works either way?
    if hasattr(x, "pymodule") and hasattr(x.pymodule, "y"):
        if x.pymodule.y == "test":
            raise RuntimeError(
                "Message Event did not go away when unregistered"
            )
