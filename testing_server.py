#!/usr/bin/python3
"""
This file runs the environment that the Playwright tests expect.
It creates a clean var dir in /dev/shm/ every run
"""

import builtins
import os
import shutil

import kaithem

# Clean up the test environment.
if os.path.exists("/dev/shm/kaithem_test_env/"):
    shutil.rmtree("/dev/shm/kaithem_test_env/")

# Ensure tests don't do anything outside the sandbox
old_open = open

a = "/dev/shm/kaithem_test_env/assets/"
os.makedirs(a, exist_ok=True)
shutil.copy(
    os.path.join(
        os.path.dirname(__file__),
        "kaithem/data/static/sounds/320181__dland__hint.opus",
    ),
    "/dev/shm/kaithem_test_env/assets/alert.ogg",
)


def open2(path, mode="r", *args, **kwargs):
    if not (str(path).startswith("/dev/shm/")) and not path == "/dev/null":
        if "w" in mode or "a" in mode:
            if "__pycache__" not in str(path):
                raise RuntimeError(
                    "Unit testing is not allowed to write outside of /dev/shm: "
                    + str(path)
                )

    return old_open(path, mode, *args, **kwargs)


builtins.open = open2

cfg = {
    "ssl_dir": "/dev/shm/kaithem_test_env/ssl",
    "site_data_dir": "/dev/shm/kaithem_test_env",
    # Prevent it from getting IP geolocation every time
    "location": "0.123,0.456",
    "log_format": "normal",
    "local_access_only": True,
}

# This object is the same as the "kaithem" object in pages and events
api = kaithem.initialize_app(cfg)

# This causes problems if imported before the app is initialized
from kaithem.src import auth  # noqa

auth.add_user("admin", "test-admin-password")
auth.add_user_to_group("admin", "Administrators")

kaithem.start_server()
