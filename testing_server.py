#!/usr/bin/python3
"""
This file runs the environment that the Playwright tests expect.
It creates a clean var dir in /dev/shm/ every run
"""

import builtins
import os
import shutil
import tracemalloc

import kaithem

tracemalloc.start()

# test module setting spec moves the module here
if os.path.exists("/dev/shm/test_ext_module_location"):
    shutil.rmtree("/dev/shm/test_ext_module_location")

# Clean up the test environment.
if os.path.exists("/dev/shm/kaithem_test_env/"):
    shutil.rmtree("/dev/shm/kaithem_test_env/")


# Only load this here, not in the pytest unit tests,
# for those we specifically want to run in a clean environment

os.makedirs("/dev/shm/kaithem_test_env/modules/data", exist_ok=True)
shutil.copytree(
    os.path.join(
        os.path.dirname(__file__),
        "kaithem/data/testing/TestingServerModule",
    ),
    "/dev/shm/kaithem_test_env/modules/data/TestingServerModule",
)

with open(
    "/dev/shm/kaithem_test_env/modules/data/test_preloaded_ext_module.location",
    "w",
) as f:
    f.write("/dev/shm/kaithem_test_env/modules/data/TestingServerModule")

# Ensure tests don't do anything outside the sandbox
old_open = open

# Persistent, gitignored podman storage shared between runs so heavy
# container tests don't refetch images every time.  Lives in the repo dir
# (not the ephemeral var dir) so it survives across test runs.
PODMAN_STORAGE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".kaithem-podman-storage"
)


def open2(path, mode: str = "r", *args, **kwargs):
    p = str(path)
    if (
        not p.startswith("/dev/shm/")
        and p != "/dev/null"
        and not p.startswith(PODMAN_STORAGE_DIR)
    ):
        if "w" in mode or "a" in mode:
            if "__pycache__" not in p and "/.cache/" not in p:
                raise RuntimeError(  # pragma: no cover
                    "Unit testing is not allowed to write outside of /dev/shm: "
                    + p
                )

    return old_open(path, mode, *args, **kwargs)


builtins.open = open2

cfg = {
    "ssl_dir": "/dev/shm/kaithem_test_env/ssl",
    "site_data_dir": "/dev/shm/kaithem_test_env",
    # Set a fixed default location so no lookup is needed
    "location": "0.123,0.456",
    "log_format": "normal",
    "local_access_only": True,
    # Allow running the tests while a dev instance already holds the
    # default port.
    "http_port": int(os.environ.get("KAITHEM_TEST_HTTP_PORT", "8002")),
}

# This object is the same as the "kaithem" object in pages and events
api = kaithem.initialize_app(cfg)

# This causes problems if imported before the app is initialized
from kaithem.src import auth, directories  # noqa

# Use persistent storage for podman so heavy container tests don't have to
# refetch images on every run.
from kaithem.src import podman_util  # noqa: E402

podman_util.set_storage(PODMAN_STORAGE_DIR)

# Run a loopback fake of the OpenRouter API and point the AI settings at
# it, so the conversation feature can be tested end to end without ever
# reaching a paid provider.  The mock echoes whatever it is sent.
from kaithem.src.tests.ai_mock import start_ai_mock  # noqa: E402

ai_mock = start_ai_mock()
from kaithem.src import settings_overrides  # noqa: E402

for _ai_key, _ai_value in {
    "core/ai/openrouter_api_base": ai_mock.api_base,
    "core/ai/openrouter_api_key": "playwright-test-key",
    "core/ai/conversations_dir": "/dev/shm/kaithem_test_env/conversations",
}.items():
    settings_overrides.add_val(_ai_key, _ai_value, "<playwright test>", 100)

# Run a loopback fake Debug Adapter Protocol server so the text editor's
# debugger sidebar can be tested without a real debugger.  It listens on
# a fixed port (see DEFAULT_DAP_MOCK_PORT) because the Playwright
# container shares the host network but not /dev/shm, so the test cannot
# read a dynamically chosen port from a file.
from kaithem.src.tests.dap_mock import (  # noqa: E402
    DEFAULT_DAP_MOCK_PORT,
    start_dap_mock,
)

dap_mock = start_dap_mock(
    port=int(
        os.environ.get("KAITHEM_TEST_DAP_PORT", str(DEFAULT_DAP_MOCK_PORT))
    )
)

# Fake map tile to make sure we are reading from the cache
os.makedirs(
    "/dev/shm/kaithem_test_env/maptiles/openstreetmap/0/0/", exist_ok=True
)
shutil.copy(
    "kaithem/data/static/img/1x1.png",
    "/dev/shm/kaithem_test_env/maptiles/openstreetmap/0/0/0.png",
)

auth.add_user("admin", "test-admin-password")
auth.add_user_to_group("admin", "Administrators")

kaithem.start_server()
