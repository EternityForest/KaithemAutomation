# NOTICE
# This file is full of awful hacks to deal with things that should be more modular
# And testable and not need so much context.

# It starts the whole app, pointed at a ram sandbox, to run things.


import os
import shutil
import kaithem.src.config
import kaithem

if os.path.exists("/dev/shm/kaithem_tests"):
    shutil.rmtree("/dev/shm/kaithem_tests")

os.makedirs("/dev/shm/kaithem_tests")

cfg = {
    'ssl-dir': "/dev/shm/kaithem_tests/ssl",
    'site-data-dir': "/dev/shm/kaithem_tests",
    # Prevent it from getting IP geolocation every time
    'location': "0,0"
}

kaithem.initialize_app(cfg)
