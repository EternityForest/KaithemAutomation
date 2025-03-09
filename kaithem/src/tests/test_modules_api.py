import os
import time

import pytest
import stamina


def test_resolve_file_resource():
    from kaithem.api.modules import (
        filename_for_file_resource,
        modules_lock,
        resolve_file_resource,
    )
    from kaithem.src import modules

    n = "test" + str(time.time()).replace(".", "_")
    modules.newModule(n)

    fn = filename_for_file_resource(n, "readme.txt")
    assert n in fn
    assert "readme.txt" in fn
    assert "__filedata__" in fn

    os.makedirs(os.path.dirname(fn), exist_ok=True)

    with open(fn, "w") as f:
        f.write("hello")

    with modules_lock:
        assert resolve_file_resource("nonexistent_45564567463.txt") is None
        x = resolve_file_resource("readme.txt")
        assert x
        assert x == fn

        assert os.path.exists(x)


async def test_modules_api():
    import kaithem.api.modules as modulesapi
    from kaithem.src import modules, modules_state

    n = "test" + str(time.time()).replace(".", "_")

    modules.newModule(n)
    assert n in modules_state.ActiveModules

    with modulesapi.modules_lock:
        modulesapi.insert_resource(
            n, "test_resource", {"resource_type": "dummy", "val": 7878}
        )

        assert modules_state.ActiveModules[n]["test_resource"]["val"] == 7878
        assert modulesapi.get_resource_data(n, "test_resource")["val"] == 7878

    with modulesapi.modules_lock:
        modulesapi.update_resource(
            n, "test_resource", {"resource_type": "dummy", "val": 789}
        )

        assert modules_state.ActiveModules[n]["test_resource"]["val"] == 789

    # Can't update a non-existent resource
    with pytest.raises(KeyError):
        with modulesapi.modules_lock:
            modulesapi.update_resource(
                n,
                "nonexistent_resource",
                {"resource_type": "dummy", "val": 789},
            )

    # Can't update with wrong type
    with pytest.raises(ValueError):
        with modulesapi.modules_lock:
            modulesapi.update_resource(
                n, "test_resource", {"resource_type": "dummy2", "val": "789"}
            )

    # Already exists
    with pytest.raises(ValueError):
        with modulesapi.modules_lock:
            modulesapi.insert_resource(
                n, "test_resource", {"resource_type": "dummy", "val": 7878}
            )

    # Test file resource stuff
    fn = modulesapi.filename_for_file_resource(n, "test_file_resource.txt")
    assert (
        fn
        == f"/dev/shm/kaithem_tests/modules/data/{n}/__filedata__/test_file_resource.txt"
    )

    # Paths aren't guaranteed to exist just because filename_for_file_resource returns them
    os.makedirs(os.path.dirname(fn), exist_ok=True)

    with open(fn, "w") as f:
        f.write("test")

    from .helpers import make_client

    client = await make_client()

    r = await client.get(
        modulesapi.admin_url_for_file_resource(n, "test_file_resource.txt"),
        follow_redirects=True,
    )
    d = await r.data
    assert d == b"test"


async def test_scan_file_resources():
    import kaithem.api.modules as modulesapi
    from kaithem.src import modules, modules_state

    n = "test" + str(time.time()).replace(".", "_")
    with modulesapi.modules_lock:
        modules.newModule(n)

    fn = modulesapi.filename_for_file_resource(n, "foo/bar/baz.txt")
    os.makedirs(os.path.dirname(fn), exist_ok=True)

    with modulesapi.modules_lock:
        modulesapi.scan_file_resources(n)

    time.sleep(0.1)
    for attempt in stamina.retry_context(on=KeyError):
        with attempt:
            assert (
                modules_state.ActiveModules[n]["foo/bar"]["resource_type"]
                == "directory"
            )
