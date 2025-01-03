import pytest


def test_tags_fail():
    from kaithem.src import tagpoints

    # Numeric tag make sure it doesn't take strings
    t = tagpoints.Tag("/system/unit_test_tag")

    with pytest.raises(TypeError):
        t.claim(10, "TestClaim", "wrong")

    assert isinstance(t.value, float)

    with pytest.raises(RuntimeError):
        # Normally we never get this far and the getter function
        # Would return the existing one, but lets test the low
        # level feature of ensuring no duplicate tgs with the same name
        tagpoints.NumericTagPointClass("/system/unit_test_tag")

    # Empty tag
    with pytest.raises(ValueError):
        tagpoints.Tag("")

    # All numbers
    with pytest.raises(ValueError):
        tagpoints.Tag("907686")

    # Has a non allowed special char
    with pytest.raises(ValueError):
        tagpoints.Tag("fail #")


def test_aliases():
    import gc

    from kaithem.src import tagpoints

    t = tagpoints.Tag("/system/unit_test_tag_alias")
    t.value = 30

    assert t.value == 30

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

    x = []

    def f(v, t, a):
        x.append(v)

    t1 = tagpoints.Tag("/system/unit_test_tag")

    t2 = tagpoints.Tag("=tv('/system/unit_test_tag') + 7")
    t.subscribe(f)

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
    assert t2.alarms["TestTagAlarm"].sm.state == "active"

    t.value = 0
    time.sleep(1)
    assert t2.alarms["TestTagAlarm"].sm.state == "cleared"

    t2.alarms["TestTagAlarm"].acknowledge()

    assert t2.alarms["TestTagAlarm"].sm.state == "normal"

    gc.collect()
    gc.collect()

    t1 = tagpoints.Tag("/system/unit_test_tag/expireTest")
    t1.value = 0

    c1 = t1.claim(5, priority=70)
    c1.set_expiration(0.5)
    assert t1.value == 5
    time.sleep(1)
    assert t1.value == 0

    c1.set(30)
    assert t1.value == 30

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
