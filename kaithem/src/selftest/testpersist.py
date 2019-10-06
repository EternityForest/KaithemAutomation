import os
from .. import persist

def test():
    if os.path.isdir("/dev/shm"):
        x = "Test sting"
        persist.save(x,"/dev/shm/kaithem_persist_selftest.txt")
        if not x == persist.load("/dev/shm/kaithem_persist_selftest.txt"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.txt")
            
        persist.save(x,"/dev/shm/kaithem_persist_selftest.txt.gz")
        if not x == persist.load("/dev/shm/kaithem_persist_selftest.txt.gz"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.txt.gz")

        persist.save(x,"/dev/shm/kaithem_persist_selftest.txt.bz2")
        if not x == persist.load("/dev/shm/kaithem_persist_selftest.txt.bz2"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.txt.bz2")

        persist.save(b'test' , "/dev/shm/kaithem_persist_selftest.bin.bz2")
        if not b'test' == persist.load("/dev/shm/kaithem_persist_selftest.bin.bz2"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.bin.bz2")

            
        persist.save(b'test' , "/dev/shm/kaithem_persist_selftest.bin.gz")
        if not b'test' == persist.load("/dev/shm/kaithem_persist_selftest.bin.gz"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.bin.gz")

        x = [1,2,3,4,5,6,7,8,9]
        persist.save(x,"/dev/shm/kaithem_persist_selftest.json")
        if not x == persist.load("/dev/shm/kaithem_persist_selftest.json"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.json")

        persist.save(x,"/dev/shm/kaithem_persist_selftest.yaml")
        if not x == persist.load("/dev/shm/kaithem_persist_selftest.yaml"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.yaml")

        persist.save(x,"/dev/shm/kaithem_persist_selftest.yaml.bz2")
        if not x == persist.load("/dev/shm/kaithem_persist_selftest.yaml.bz2"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.yaml.bz2")

        persist.save(x,"/dev/shm/kaithem_persist_selftest.yaml.gz")
        if not x == persist.load("/dev/shm/kaithem_persist_selftest.yaml.gz"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.yaml.gz")

        persist.save(x,"/dev/shm/kaithem_persist_selftest.json.bz2")
        if not x == persist.load("/dev/shm/kaithem_persist_selftest.json.bz2"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.json.bz2")

        persist.save(x,"/dev/shm/kaithem_persist_selftest.json.gz")
        if not x == persist.load("/dev/shm/kaithem_persist_selftest.json.gz"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.json.gz")

        persist.save(b'test',"/dev/shm/kaithem_persist_selftest.bin")
        if not b'test' == persist.load("/dev/shm/kaithem_persist_selftest.bin"):
            raise RuntimeError("Kaithem persist readback does match")

        persist.save(b'test2',"/dev/shm/kaithem_persist_selftest.bin")
        if not b'test2' == persist.load("/dev/shm/kaithem_persist_selftest.bin"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.bin")

        x2 = [1,2,3,4,5,6,7,8,9,10]

        persist.save(x2,"/dev/shm/kaithem_persist_selftest.yaml.gz")
        if not x2 == persist.load("/dev/shm/kaithem_persist_selftest.yaml.gz"):
            raise RuntimeError("Kaithem persist readback does not match"+str(persist.load("/dev/shm/kaithem_persist_selftest.yaml.gz")))
        os.remove("/dev/shm/kaithem_persist_selftest.yaml.gz")

        persist.save(x2,"/dev/shm/kaithem_persist_selftest.yaml.bz2")
        if not x2 == persist.load("/dev/shm/kaithem_persist_selftest.yaml.bz2"):
            raise RuntimeError("Kaithem persist readback does not match")
        os.remove("/dev/shm/kaithem_persist_selftest.yaml.bz2")

        persist.save(x2,"/dev/shm/kaithem_persist_selftest.json.gz",backup=True)
        if not x2 == persist.load("/dev/shm/kaithem_persist_selftest.json.gz"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.json.gz")

        persist.save(b'test123',"/dev/shm/kaithem_persist_selftest.bin",backup=True)
        if not b'test123' == persist.load("/dev/shm/kaithem_persist_selftest.bin"):
            raise RuntimeError("Kaithem persist readback does match")
        os.remove("/dev/shm/kaithem_persist_selftest.bin")
