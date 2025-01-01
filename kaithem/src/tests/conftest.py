# NOTICE
# This file is full of awful hacks to deal with things that should be more modular
# And testable and not need so much context.

# It starts the whole app, pointed at a ram sandbox, to run things.

import os
import sys
import threading

import pytest

print("Conftest.py", sys.argv)


@pytest.fixture(scope="session", autouse=True)
def cleanup(request):
    def remove_test_dir():
        # TODO what is keeping it running?
        # List all non daemon threads and what they are doing

        print("Test finished, listing remaining threads")
        frames = sys._current_frames()
        for thread in threading.enumerate():
            if not thread.daemon:
                print(thread, thread.is_alive(), thread.name)
                if thread.ident:
                    try:
                        print(thread.name, frames[thread.ident])
                    except KeyError:
                        pass

        from kaithem.api import lifespan

        lifespan.shutdown_now()

    request.addfinalizer(remove_test_dir)


if "--collect-only" not in sys.argv:  # pragma: no cover
    import builtins
    import os
    import shutil

    import kaithem
    import kaithem.src.config

    if os.path.exists("/dev/shm/kaithem_tests"):
        shutil.rmtree("/dev/shm/kaithem_tests")

    os.makedirs("/dev/shm/kaithem_tests/plugins/Test")

    old_open = open

    def open2(path, mode="r", *args, **kwargs):
        if not (str(path).startswith("/dev/shm/")) and not path == "/dev/null":
            if "w" in mode or "a" in mode:
                if "__pycache__" not in str(path):
                    if ".cache/" not in str(path) and not path.startswith(
                        "/run/"
                    ):
                        raise RuntimeError(
                            "Unit testing is not allowed to write outside of /dev/shm: "
                            + str(path)
                        )

        return old_open(path, mode, *args, **kwargs)

    builtins.open = open2

    cfg = {
        "ssl_dir": "/dev/shm/kaithem_tests/ssl",
        "site_data_dir": "/dev/shm/kaithem_tests",
        # Prevent it from getting IP geolocation every time
        "location": "0.123,0.345",
        "log_format": "normal",
        "local_access_only": True,
    }

    pp = """
import os

import kaithem.api.chandler as chandlerapi


def foo_command(x: str):
    "This docstring shows up in the logic editor"
    # Trigger an event in every group
    chandlerapi.trigger_event(x)

    # Jump to any cue that has the shortcut
    chandlerapi.shortcut(x)
    return True

chandlerapi.add_command("foo_command", foo_command)
    """

    pt = """
{% extends "pagetemplate.j2.html" %}

{% block title %}Title Here{% endblock %}

{% block body %}
<main>
    <section class="window paper">
        <h2>Path</h2>

        {% for i in path %}
        <p>{{i}}</p>
        {% endfor %}

        <h2>URL Params</h2>
        <p>{{kw}}</p>

    </section>
</main>
{% endblock %}
"""

    with open("/dev/shm/kaithem_tests/plugins/Test/__init__.py", "w") as f:
        f.write(pp)

    with open("/dev/shm/kaithem_tests/plugins/Test/template.html", "w") as f:
        f.write(pt)

    kaithem.initialize_app(cfg)
    # This causes problems if imported before the app is initialized
    from kaithem.src import auth  # noqa

    auth.add_user("admin", "test-admin-password")
    auth.add_user_to_group("admin", "Administrators")

    # TODO Sound can't be imported before config init, eventually
    # A refactor should fix that
    import kaithem.src.sound  # noqa

    kaithem.src.sound.select_backend("test")
