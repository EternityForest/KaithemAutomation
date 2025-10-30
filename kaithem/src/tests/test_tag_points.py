import pytest


def test_unit_conversion():
    from kaithem.src import tagpoints

    t = tagpoints.Tag("/system/unit_test_tag")
    t.unit = "cm"

    t.default_claim.set_as(50, "in")
    assert abs(t.value - 50 * 2.54) < 0.00001

    t.default_claim.set_as(50, "cm")
    assert t.value == 50

    assert abs(t.convert_to("in") - 50 / 2.54) < 0.00001

    t.set_as(4, "in")
    assert abs(t.value - 4 * 2.54) < 0.00001


def test_normalize_tag_names():
    from kaithem.src import tagpoints

    assert tagpoints.Tag("=1") is tagpoints.Tag("/=1")
    assert tagpoints.Tag("foo1234") is tagpoints.Tag("/foo1234")
    assert tagpoints.Tag("/foo-1234") is tagpoints.Tag("/foo_1234")


def test_tag_override_resource():
    import time

    import kaithem.api.modules as modulesapi
    from kaithem.src import alerts, modules, tagpoints

    n = "test" + str(time.time()).replace(".", "_")
    modules.newModule(n)

    tp = tagpoints.Tag("/system/unit_test_tag_override_resource")

    with modulesapi.modules_lock:
        modulesapi.insert_resource(
            n,
            "test_resource",
            {
                "resource": {"type": "tag_override"},
                "tag": "/system/unit_test_tag_override_resource",
                "tag_type": "numeric",
                "priority": 60,
                "alert": True,
                "value": 7878,
            },
        )

        assert tp.value == 7878
        assert tp.active_claim and tp.active_claim.priority == 60

        time.sleep(0.2)

        found = False
        for alert in alerts.active.values():
            if "unit_test_tag_override_resource" in alert().name:
                found = True
                break
        assert found

        modulesapi.delete_resource(n, "test_resource")
        time.sleep(0.2)
        found = False
        for alert in alerts.active.values():
            if "unit_test_tag_override_resource" in alert().name:
                found = True
                break
        assert not found
        assert tp.value == 0


def test_trigger():
    from kaithem.src import tagpoints

    t = tagpoints.Tag("/system/unit_test_tag_trigger")
    x = t.value
    t.trigger()
    assert t.value == x + 1


def test_tags_fail():
    from kaithem.src import tagpoints

    # Numeric tag make sure it doesn't take strings
    t = tagpoints.Tag("/system/unit_test_tag_fail")

    with pytest.raises(TypeError):
        t.claim(10, "TestClaim", "wrong")

    with pytest.raises(ValueError):
        t.claim(89, "PriorityTooHigh101", priority=101)

    with pytest.raises(ValueError):
        t.add_alias("/multiple/forward/slashes/in/alias")

    assert isinstance(t.value, float)

    with pytest.raises(RuntimeError):
        # Normally we never get this far and the getter function
        # Would return the existing one, but lets test the low
        # level feature of ensuring no duplicate tgs with the same name
        tagpoints.NumericTagPointClass("/system/unit_test_tag_fail")

    # Empty tag
    with pytest.raises(ValueError):
        tagpoints.Tag("")

    # All numbers
    with pytest.raises(ValueError):
        tagpoints.Tag("907686")

    # Has a non allowed special char
    with pytest.raises(ValueError):
        tagpoints.Tag("fail #")

    # Have to set unit to blank before you can change it, to prevent
    # mistakes
    t.unit = "in"
    with pytest.raises(ValueError):
        t.unit = "cm"

    t.unit = ""
    t.unit = "cm"
    assert t.unit == "cm"


def test_tag_getter_error():
    import time

    from kaithem.src import logviewer, tagpoints

    t = tagpoints.Tag("/system/unit_test_tag_getter")

    err_once = [True]
    t.interval = 0.4

    def f():
        if err_once[0]:
            err_once[0] = False
            raise Exception("Test Error")
        return 6

    t.value = f
    # Error is logged but treated as no data
    assert t.value == 0
    # TODO the interval test was flaky
    # assert t.value == 0

    time.sleep(0.6)
    assert t.value == 6

    # Ensure that it ws logged.
    logviewer.expect_log(
        "Error getting tag value for /system/unit_test_tag_getter"
    )


def test_aliases():
    import gc

    from kaithem.src import tagpoints

    t = tagpoints.Tag("/foo1234")

    t = tagpoints.Tag("/system/unit_test_tag_alias")
    t.value = 30

    assert t.value == 30

    with pytest.raises(RuntimeError):
        t.add_alias("foo1234")
    with pytest.raises(ValueError):
        t.add_alias("")
    with pytest.raises(ValueError):
        t.add_alias(" ")
    with pytest.raises(ValueError):
        t.add_alias("foo #")

    t.add_alias("tag_alias_1")
    t.add_alias("tag_alias_2")

    assert tagpoints.Tag("tag_alias_1").value == 30
    assert tagpoints.Tag("tag_alias_2").value == 30

    t.remove_alias("tag_alias_2")
    assert tagpoints.Tag("tag_alias_2").value == 0

    tagpoints.Tag("tag_alias_1").value = 40

    assert t.value == 40

    del t
    gc.collect()
    gc.collect()

    assert tagpoints.Tag("/system/unit_test_tag_alias").value == 0
    assert tagpoints.Tag("tag_alias_1").value == 0


def test_tags_basic():
    import time

    from kaithem.src import tagpoints

    t = tagpoints.Tag("/system/unit_test_tag_5457647")
    # TODO should probably actualluly do some assertions here,
    # but at least we can check that it doesn't block up.
    t.testForDeadlock()

    ts = time.time()

    gotTagValue = []
    got_tag_error = []

    def onError(tag, function, val):
        got_tag_error.append((tag, function, val))

    tagpoints.subscriber_error_handlers.append(onError)

    def f(value, timestamp, annotation):
        gotTagValue.append((value, timestamp, annotation))

    t.subscribe(f)

    t.set_claim_val("default", 50, ts, "TestAnnotation")

    # Makr sure subscribers work
    assert len(gotTagValue) == 1
    assert len(got_tag_error) == 0
    assert gotTagValue[0] == (50, ts, "TestAnnotation")

    assert t.value == 50
    assert t.timestamp == ts
    assert t.annotation == "TestAnnotation"

    assert t.vta == (50, ts, "TestAnnotation")

    # Make sure setting None uses the time
    t.set_claim_val("default", 50, None, "TestAnnotation")
    assert abs(t.timestamp - time.time()) < 0.1


def test_tags_claim_release():
    import time

    from kaithem.src import tagpoints

    t = tagpoints.Tag("/system/unit_test_tag_545j7647")
    claim1 = t.claim(51, "c1", 51, time.time(), "TestAnnotation")
    claim2 = t.claim(52, "c2", 52, time.time(), "TestAnnotation2")

    assert t.value == 52
    t.set_claim_val("c2", 40, time.time(), "TestAnnotation")
    assert t.value == 40

    claim2.release()
    assert t.value == 51
    claim1.release()
    assert t.value == 0


def test_tags_claim_release_after_set_while_not_active():
    import time

    from kaithem.src import tagpoints

    t = tagpoints.Tag("/system/unit_test_tag_545j7647")
    claim1 = t.claim(51, "c1", 51, time.time(), "TestAnnotation")
    claim2 = t.claim(52, "c2", 52, time.time(), "TestAnnotation2")

    assert t.value == 52
    t.set_claim_val("c2", 40, time.time(), "TestAnnotation")
    assert t.value == 40
    assert t.annotation == "TestAnnotation"

    t.set_claim_val("c1", 123, time.time(), annotation="TestAnnotation3")
    assert t.value == 40

    claim2.release()
    assert t.value == 123
    assert t.annotation == "TestAnnotation3"
    claim1.release()
    assert t.value == 0


def test_tags_claim_change_active_claim_priority():
    import time

    from kaithem.src import tagpoints

    t = tagpoints.Tag("/system/unit_test_tag_545j7647")
    claim1 = t.claim(51, "c1", 51, time.time(), "TestAnnotation")
    claim2 = t.claim(52, "c2", 52, time.time(), "TestAnnotation2")

    assert t.value == 52
    t.set_claim_val("c2", 40, time.time(), "TestAnnotation")
    assert t.value == 40

    claim2.set_priority(49)
    assert t.value == 51
    claim1.release()
    assert t.value == 0


def test_tags_error():
    import time

    from kaithem.src import tagpoints

    t = tagpoints.Tag("/system/unit_test_tag_545j7647")
    ts = time.time()

    got_tag_error = []

    def onError(tag, function, val):
        got_tag_error.append((tag, function, val))

    tagpoints.subscriber_error_handlers.append(onError)

    def f(value, timestamp, annotation):
        raise Exception("Test Error")

    t.subscribe(f)
    t.set_claim_val("default", 50, ts, "TestAnnotation")

    # Makr sure subscribers work
    assert len(got_tag_error) == 1
    assert got_tag_error[0] == (t, f, 50)

    assert t.value == 50
    assert t.timestamp == ts
    assert t.annotation == "TestAnnotation"
    assert t.vta == (50, ts, "TestAnnotation")


def test_no_alarm_on_default():
    import time

    from kaithem.src import tagpoints

    t = tagpoints.Tag("/system/unit_test_tag_545j7647b")
    assert t.value == 0
    t.set_alarm("test", "value < 10")
    time.sleep(1)
    assert t._alerts["test"].sm.state == "normal"
    t.value = 9
    time.sleep(1)
    assert t._alerts["test"].sm.state != "normal"


def test_tags():
    import gc
    import time

    from kaithem.src import tagpoints

    t = tagpoints.Tag("/system/unit_test_tag")

    t.value = 30

    tester = [0]

    assert t.value == 30

    def f(value, timestamp, annotation):
        tester[0] = value

    t.subscribe(f)

    t.value = 80
    assert tester[0] == 80

    c = t.claim(50, "TestClaim", 60)

    assert tester[0] == 50

    del f
    gc.collect()
    c.set(8)
    assert tester[0] == 50

    assert t.value == 8

    c2 = t.claim(5, "TestClaim2", 55)

    assert t.value == 8

    c.release()
    assert t.value == 5

    # Now test the StringTags
    t = tagpoints.StringTag("/system/unit_test_tag2")

    t.value = "str"

    tester = [0]

    assert t.value == "str"

    def f(value, timestamp, annotation):
        tester[0] = value

    t.subscribe(f)

    t.value = "str2"
    assert tester[0] == "str2"

    c = t.claim("50", "TestClaim", 60)

    assert tester[0] == "50"

    del f
    gc.collect()
    c.set("8")
    gc.collect()
    assert tester[0] == "50"

    assert t.value == "8"

    c2 = t.claim("5", "TestClaim2", 55)  # noqa

    assert t.value == "8"

    c.release()
    assert t.value == "5"

    t1 = tagpoints.Tag("/system/unit_test_tag")

    t2 = tagpoints.Tag("=tv('/system/unit_test_tag') + 7")

    c3 = t1.claim(1, "testClaim3", 80)
    assert t2.value == 1 + 7

    c3.set(2)
    assert t2.value == 2 + 7

    # Test tag point values derived from other values
    t = tagpoints.Tag("testTagPointSelftestA")
    t.value = 90

    t2 = tagpoints.Tag("=tv('/testTagPointSelftestA')+10")

    assert t2.value == 100

    t.value = 40

    assert t2.value == 50

    t2.set_alarm("TestTagAlarm", "value>40", priority="debug")

    time.sleep(0.5)
    assert t2._alerts["TestTagAlarm"].sm.state == "active"

    t.value = 0
    time.sleep(1)
    assert t2._alerts["TestTagAlarm"].sm.state == "cleared"

    t2._alerts["TestTagAlarm"].acknowledge()

    assert t2._alerts["TestTagAlarm"].sm.state == "normal"

    gc.collect()
    gc.collect()

    t1 = tagpoints.StringTag("/system/unit_test_tag/sync1Str")
    t2 = tagpoints.StringTag("/system/unit_test_tag/sync2Str")

    # Make sure the old tag is gone
    gc.collect()
    gc.collect()

    t1 = tagpoints.Tag("/system/unit_test_tag/minmax")

    t1.value = 40
    t1.min = 50

    assert t1.value == 50

    t1.value = -1000
    assert t1.value == 50
