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


def test_simple_resource_types():
    import kaithem.api.modules as modulesapi
    from kaithem.api.resource_types import (
        ResourceTypeRuntimeObject,
        resource_type_from_schema,
    )
    from kaithem.src import modules

    n = "test" + str(time.time()).replace(".", "_")
    modules.newModule(n)

    tst = []

    class DummyResourceTypeImplementation(ResourceTypeRuntimeObject):
        def __init__(self, module, resource, data):
            tst.append(data["val"])

        def close(self):
            tst.append("closed")

    schema = {
        "type": "object",
        "properties": {"val": {"type": "number"}},
        "required": ["val"],
    }

    resource_type_from_schema(
        resource_type="test-basic-autogen-type",
        title="Dummy",
        icon="mdi-account",
        schema=schema,
        runtime_object_cls=DummyResourceTypeImplementation,
        default={"val": 0},
    )

    with modulesapi.modules_lock:
        modulesapi.insert_resource(
            n,
            "test_resource",
            {
                "resource": {"type": "test-basic-autogen-type"},
                "data": {"val": 7878},
            },
        )

        modulesapi.delete_resource(n, "test_resource")

    assert tst == [7878, "closed"]


async def test_modules_api():
    import kaithem.api.modules as modulesapi
    from kaithem.src import modules, modules_state

    n = "test" + str(time.time()).replace(".", "_")

    modules.newModule(n)
    assert n in modules_state.ActiveModules

    with modulesapi.modules_lock:
        modulesapi.insert_resource(
            n, "test_resource", {"resource": {"type": "dummy"}, "val": 7878}
        )

        assert modules_state.ActiveModules[n]["test_resource"]["val"] == 7878
        assert modulesapi.get_resource_data(n, "test_resource")["val"] == 7878

    with modulesapi.modules_lock:
        modulesapi.set_resource_error(n, "test_resource", "foo")

    assert (n, "test_resource") in modules_state.resource_errors

    with modulesapi.modules_lock:
        modulesapi.update_resource(
            n, "test_resource", {"resource": {"type": "dummy"}, "val": 789}
        )

        assert modules_state.ActiveModules[n]["test_resource"]["val"] == 789

    # Updating should clear the error
    assert (n, "test_resource") not in modules_state.resource_errors

    # Can't update a non-existent resource
    with pytest.raises(KeyError):
        with modulesapi.modules_lock:
            modulesapi.update_resource(
                n,
                "nonexistent_resource",
                {"resource": {"type": "dummy"}, "val": 789},
            )

    # Can't update with wrong type
    with pytest.raises(ValueError):
        with modulesapi.modules_lock:
            modulesapi.update_resource(
                n,
                "test_resource",
                {"resource": {"type": "dummy2"}, "val": "789"},
            )

    # Already exists
    with pytest.raises(ValueError):
        with modulesapi.modules_lock:
            modulesapi.insert_resource(
                n, "test_resource", {"resource": {"type": "dummy"}, "val": 7878}
            )

    # Failed attempts should not modify
    assert "test_resource" in modules_state.ActiveModules[n]

    with modulesapi.modules_lock:
        modulesapi.delete_resource(n, "test_resource")

    assert "test_resource" not in modules_state.ActiveModules[n]

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
                modules_state.ActiveModules[n]["foo/bar"]["resource"]["type"]
                == "directory"
            )
