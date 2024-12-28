import os
import time


async def test_modules_api():
    import kaithem.api.modules as modulesapi
    from kaithem.src import modules, modules_state

    n = "test" + str(time.time()).replace(".", "_")

    modules.newModule(n)
    assert n in modules_state.ActiveModules

    modulesapi.insert_resource(
        n, "test_resource", {"resource_type": "dummy", "val": 7878}
    )

    assert modules_state.ActiveModules[n]["test_resource"]["val"] == 7878
    assert modulesapi.get_resource_data(n, "test_resource")["val"] == 7878

    modulesapi.update_resource(
        n, "test_resource", {"resource_type": "dummy", "val": 789}
    )

    assert modules_state.ActiveModules[n]["test_resource"]["val"] == 789

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
