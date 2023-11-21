# NOTICE
# This file is full of awful hacks to deal with things that should be more modular
# And testable and not need so much context.


import os, shutil
import kaithem.src.config

if os.path.exists("/dev/shm/kaithem_tests"):
    shutil.rmtree("/dev/shm/kaithem_tests")

os.makedirs("/dev/shm/kaithem_tests")
# This makes a /dev/shm disk to run these tests in the context of a real kaithem instance.
# They are mostly integration, not unit tests.
kaithem.src.config.initialize_defaults_for_testing()