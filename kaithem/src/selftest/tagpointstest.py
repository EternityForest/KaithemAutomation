

def testTags():
    from src import tagpoints

    t= tagpoints.Tag("/system/selftest")
    t.value = 30

    tester = [0]

    if not t.value==30:
        raise RuntimeError("Unexpected Tag Value")

    def f(value,timestamp, annotation):
        tester[0]=value

    t.subscribe(f)

    t.value=80
    if not tester[0]==80:
        raise RuntimeError("Unexpected Tag Value")

    c = t.claim(50,"TestClaim",60)
    
    if not tester[0]==50:
        raise RuntimeError("Tag subscription issue")

    del f
    c.set(8)
    if not tester[0]==50:
        raise RuntimeError("Tag subscriber still active after being deleted")

    if not t.value==8:
        raise RuntimeError("Unexpected Tag Value")



    c2 = t.claim(5,"TestClaim2",55)

    if not t.value==8:
        raise RuntimeError("Tag value being affected by lower priority claim")
    
    c.release()
    if not t.value==5:
        raise RuntimeError("Lower priority tag not taking over when higher priority released")

    
