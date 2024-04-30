import io
import os
import time
import weakref

import cherrypy

from kaithem.api import tags
from kaithem.src import modules, modules_state, webapproot
from kaithem.src.plugins import CorePluginEventResources

dir = "/dev/shm/kaithem_tests/"


class testobj:
    pass


def test_make_module_web():
    # Make module using the same API that the web frontend would
    n = "test" + str(time.time()).replace(".", "_")

    try:
        webapproot.root.modules.newmoduletarget(name=n)
        raise RuntimeError("Newmoduletarget should redirect")
    except cherrypy.HTTPRedirect:
        pass

    assert n in modules_state.ActiveModules

    assert n in webapproot.webapproot().modules.index()

    assert webapproot.webapproot().modules.module(n)

    try:
        webapproot.root.modules.module(n, "addresourcetarget", "event", name="testevt")
        raise RuntimeError("Newmoduletarget should redirect")
    except cherrypy.HTTPRedirect:
        pass

    assert webapproot.webapproot().modules.module(n, "resource", "testevt")

    # Check file on disk and internal data structure
    assert os.path.exists(os.path.join(dir, "modules/data/" + n))

    assert os.path.exists(os.path.join(dir, "modules/data/", n, "testevt.py"))
    assert "testevt" in modules_state.ActiveModules[n]

    try:
        webapproot.root.modules.module(
            n,
            "updateresource",
            "testevt",
            newname="testevt",
            setup="x = 8\n",
            trigger="x>6",
            action="global x\n\nx= 5",
            priority="interactive",
            ratelimit=1,
            enable=True,
        )
        raise RuntimeError("Newmoduletarget should redirect")
    except cherrypy.HTTPRedirect:
        pass

    assert "x = 8" in webapproot.webapproot().modules.module(n, "resource", "testevt")

    assert (n, "testevt") in CorePluginEventResources._events_by_module_resource

    x = CorePluginEventResources._events_by_module_resource[(n, "testevt")]

    x.pymodule.__dict__["test_obj"] = testobj()
    ref = weakref.ref(x.pymodule.__dict__["test_obj"])

    # Ensure the event actually worked
    time.sleep(1)
    assert x.pymodule.__dict__["x"] == 5

    try:
        webapproot.root.modules.module(n, "deleteresourcetarget", name="testevt")
    except cherrypy.HTTPRedirect:
        pass

    assert (n, "testevt") not in CorePluginEventResources._events_by_module_resource

    # The scope of the dynamically generated module should be gone now
    assert ref() is None

    try:
        webapproot.root.modules.module(
            n,
            "addresourcetarget",
            "tagpoint",
            name="testtag",
            tag="test_tag_foo",
            min="",
            max="",
            hi="",
            lo="",
            interval="",
            default=99,
            tag_type="numeric",
        )
        raise RuntimeError("Newmoduletarget should redirect")
    except cherrypy.HTTPRedirect:
        pass

    assert tags.existing_tag("test_tag_foo").value == 99

    # Round trip upload and download with the YAML mechanism

    zf = webapproot.root.modules.yamldownload(n)
    assert zf
    zf2 = io.BytesIO(zf)

    try:
        webapproot.root.modules.deletemoduletarget(name=n)
        raise RuntimeError("Newmoduletarget should redirect")
    except cherrypy.HTTPRedirect:
        pass

    assert "/test_tag_foo" not in tags.all_tags_raw()

    modules.load_modules_from_zip(zf2)

    assert n in modules_state.ActiveModules
    assert "/test_tag_foo" in tags.all_tags_raw()
