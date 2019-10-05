import time

def test():
    from src import messagebus
    succeed = [0]
    def f(m,v):
        succeed[0]= 1
    messagebus.subscribe("/system/selftest", f)
    messagebus.postMessage("/system/selftest","Test")

    time.sleep(0.2)
    if not succeed[0]:
        time.sleep(2)
        if succeed[0]:
            raise RuntimeError("Message not delivered within 0.2 second. This may happen occasionally if CPU load is high but otherwise should not occur.")
        else:
            raise RuntimeError("Message not delivered within 2 seconds")
    
    del f
    succeed[0] = 0

    messagebus.postMessage("/system/selftest","Test")
    time.sleep(3)
    if succeed[0]:
        raise RuntimeError("Garbage collection fails to unsubscribe")
