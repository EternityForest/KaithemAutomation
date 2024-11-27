import copy
import difflib
import gc
import io
import json
import os
import sys
import time
import weakref

if "--collect-only" not in sys.argv:
    from kaithem.api import tags
    from kaithem.src import modules, modules_state
    from kaithem.src.plugins import CorePluginEventResources

dir = "/dev/shm/kaithem_tests/"


class testobj:
    pass


def test_make_module():
    n = "test" + str(time.time()).replace(".", "_")

    modules.newModule(n)
    assert n in modules_state.ActiveModules

    # Todo we should probably have a cleaner interface for doing this programmatically

    with modules_state.modulesLock:
        type = "event"
        rt = modules_state.additionalTypes[type]
        # If create returns None, assume it doesn't want to insert a module or handles it by itself
        r = rt.on_create_request(n, "testevt", {})
        rt._validate(r)
        if r:
            modules_state.rawInsertResource(n, "testevt", r)
            rt.on_load(n, "testevt", r)

    assert "testevt" in modules_state.ActiveModules[n]

    # Check file on disk and internal data structure
    assert os.path.exists(os.path.join(dir, "modules/data/" + n))

    assert os.path.exists(os.path.join(dir, "modules/data/", n, "testevt.py"))
    assert "testevt" in modules_state.ActiveModules[n]

    d = dict(
        setup="x = 8\n",
        trigger="x>6",
        action="global x\n\nx= 5",
        priority="interactive",
        ratelimit=1,
        enable=True,
    )

    x = copy.deepcopy(modules_state.ActiveModules[n]["testevt"])
    x.update(d)
    modules_state.rawInsertResource(n, "testevt", x)
    modules.handleResourceChange(n, "testevt")

    assert "x = 8" in str(modules_state.ActiveModules[n]["testevt"])

    assert (n, "testevt") in CorePluginEventResources._events_by_module_resource

    x = CorePluginEventResources._events_by_module_resource[(n, "testevt")]

    x.pymodule.__dict__["test_obj"] = testobj()
    ref = weakref.ref(x.pymodule.__dict__["test_obj"])

    # Ensure the event actually worked
    time.sleep(1)
    assert x.pymodule.__dict__["x"] == 5

    modules.rmResource(n, "testevt")

    assert (
        n,
        "testevt",
    ) not in CorePluginEventResources._events_by_module_resource

    # The scope of the dynamically generated module should be gone now
    assert ref() is None

    type = "tagpoint"

    d = dict(
        tag="test_tag_foo",
        min="",
        max="",
        hi="",
        lo="",
        interval="",
        default=99,
        tag_type="numeric",
    )
    rt = modules_state.additionalTypes[type]
    r = rt.on_create_request(n, "testtag", d)

    modules_state.rawInsertResource(n, "testtag", r)
    modules.handleResourceChange(n, "testtag")

    assert tags.existing_tag("test_tag_foo").value == 99

    # Round trip upload and download with the YAML mechanism

    old_hash = modules_state.getModuleHash(n)

    old_json = json.dumps(
        modules_state.ActiveModules[n], sort_keys=True, indent=4
    )

    zf = modules_state.getModuleAsYamlZip(n)
    assert zf
    zf2 = io.BytesIO()

    for i in zf:
        zf2.write(i)

    modules.rmModule(n)

    if "/test_tag_foo" in tags.all_tags_raw():
        gc.collect()

    assert "/test_tag_foo" not in tags.all_tags_raw()

    modules.load_modules_from_zip(zf2)

    new_json = json.dumps(
        modules_state.ActiveModules[n], sort_keys=True, indent=4
    )

    diff = difflib.unified_diff(old_json.splitlines(), new_json.splitlines())

    assert "\n".join(diff) == ""

    assert n in modules_state.ActiveModules
    assert "/test_tag_foo" in tags.all_tags_raw()
    assert old_hash == modules_state.hashModule(n)
    assert old_hash == modules_state.getModuleHash(n)

    modules.rmModule(n)
