# NOTICE
# This file is full of awful hacks to deal with things that should be more modular
# And testable and not need so much context.

# It starts the whole app, pointed at a ram sandbox, to run things.


import os
import shutil

import kaithem
import kaithem.src.config

if os.path.exists("/dev/shm/kaithem_tests"):
    shutil.rmtree("/dev/shm/kaithem_tests")

os.makedirs("/dev/shm/kaithem_tests")

cfg = {
    "ssl-dir": "/dev/shm/kaithem_tests/ssl",
    "site-data-dir": "/dev/shm/kaithem_tests",
    # Prevent it from getting IP geolocation every time
    "location": "0,0",
    "log-format": "normal",
}

kaithem.initialize_app(cfg)
# TODO Sound can't be imported before config init, eventually
# A refactor should fix that
import kaithem.src.sound  # noqa

kaithem.src.sound.select_backend("test")
