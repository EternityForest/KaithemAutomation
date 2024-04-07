def testTags():
    from kaithem.src import tagpoints
    import time
    import gc

    t = tagpoints.Tag("/system/selftest")

    t.value = 30

    tester = [0]

    if not t.value == 30:
        raise RuntimeError("Unexpected Tag Value" + str(t.value))

    def f(value, timestamp, annotation):
        tester[0] = value

    t.subscribe(f)

    t.value = 80
    if not tester[0] == 80:
        raise RuntimeError("Unexpected Tag Value")

    c = t.claim(50, "TestClaim", 60)

    if not tester[0] == 50:
        raise RuntimeError("Tag subscription issue")

    del f
    gc.collect()
    c.set(8)
    if not tester[0] == 50:
        raise RuntimeError("Tag subscriber still active after being deleted")

    if not t.value == 8:
        raise RuntimeError("Unexpected Tag Value")

    c2 = t.claim(5, "TestClaim2", 55)

    if not t.value == 8:
        raise RuntimeError("Tag value being affected by lower priority claim")

    c.release()
    if not t.value == 5:
        raise RuntimeError(
            "Lower priority tag not taking over when higher priority released"
        )

    # Now test the StringTags
    t = tagpoints.StringTag("/system/selftest2")

    t.value = "str"

    tester = [0]

    if not t.value == "str":
        raise RuntimeError("Unexpected Tag Value")

    def f(value, timestamp, annotation):
        tester[0] = value

    t.subscribe(f)

    t.value = "str2"
    if not tester[0] == "str2":
        raise RuntimeError("Unexpected Tag Value")

    c = t.claim("50", "TestClaim", 60)

    if not tester[0] == "50":
        raise RuntimeError("Tag subscription issue")

    del f
    gc.collect()
    c.set("8")
    gc.collect()
    if not tester[0] == "50":
        raise RuntimeError("Tag subscriber still active after being deleted")

    if not t.value == "8":
        raise RuntimeError("Unexpected Tag Value")

    c2 = t.claim("5", "TestClaim2", 55)

    if not t.value == "8":
        raise RuntimeError("Tag value being affected by lower priority claim")

    c.release()
    if not t.value == "5":
        raise RuntimeError(
            "Lower priority tag not taking over when higher priority released"
        )

    x = []

    def f(v, t, a):
        c.append(v)

    t1 = tagpoints.Tag("/system/selftest")

    t2 = tagpoints.Tag("=tv('/system/selftest') + 7")
    t.subscribe(f)

    c3 = t1.claim(1, "testClaim3", 80)
    if not t2.value == 1 + 7:
        raise RuntimeError(
            "Subscriber to expression tag did not trigger when dependancy updated"
        )

    c3.set(2)
    if not t2.value == 2 + 7:
        raise RuntimeError(
            "Subscriber to expression tag did not trigger when dependancy updated"
        )

    # Test tag point values derived from other values
    t = tagpoints.Tag("TestTagPointSelftestA")
    t.value = 90

    t2 = tagpoints.Tag("=tv('/TestTagPointSelftestA')+10")

    if not t2.value == 100:
        raise RuntimeError("Expression tagpoint didn't work")

    t.value = 40

    if not t2.value == 50:
        raise RuntimeError("Expression tagpoint didn't update, value:" + str(t2.value))

    t2.set_alarm("TestTagAlarm", "value>40", priority="debug")

    time.sleep(0.5)
    if not t2.alarms["TestTagAlarm"].sm.state == "active":
        raise RuntimeError(
            "Alarm not activated, state:" + t2.alarms["TestTagAlarm"].sm.state
        )

    t.value = 0
    time.sleep(3)
    if not t2.alarms["TestTagAlarm"].sm.state == "cleared":
        raise RuntimeError(
            "Alarm not cleared, state:"
            + t2.alarms["TestTagAlarm"].sm.state
            + " value:"
            + str(t2.value)
        )

    t2.alarms["TestTagAlarm"].acknowledge()

    if not t2.alarms["TestTagAlarm"].sm.state == "normal":
        raise RuntimeError("Alarm not normal after acknowledge")

    gc.collect()
    gc.collect()

    t1 = tagpoints.Tag("/system/selftest/ExpireTest")
    t1.value = 0

    c1 = t1.claim(5, priority=70)
    c1.setExpiration(2)
    if not t1.value == 5:
        raise RuntimeError("Unexpected tag value")
    time.sleep(3)
    if not t1.value == 0:
        raise RuntimeError("Claim expiration did not work")

    c1.set(30)
    if not t1.value == 30:
        raise RuntimeError("Claim expiration did not un-expire correctly")

    t1 = tagpoints.StringTag("/system/selftest/Sync1Str")
    t2 = tagpoints.StringTag("/system/selftest/Sync2Str")

    # Make sure the old tag is gone
    gc.collect()
    gc.collect()

    t1 = tagpoints.Tag("/system/selftest/minmax")

    t1.value = 40
    t1.min = 50

    if not t1.value == 50:
        raise RuntimeError("Min was ignored")

    t1.value = -1000
    if not t1.value == 50:
        raise RuntimeError("Min was ignored")
