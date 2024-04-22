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
