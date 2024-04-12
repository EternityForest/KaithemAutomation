import os
import time

import cherrypy

from kaithem.src import modules_state, newevt, webapproot

dir = "/dev/shm/kaithem_tests/"


class testobj:
    pass


def test_make_module_web():
    # Make module using the same API that the web frontend would
    n = "test" + str(time.time())

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

    assert (n, "testevt") in newevt.EventReferences

    x = newevt.EventReferences[(n, "testevt")]

    # Ensure the event actually worked
    time.sleep(1)
    assert x.pymodule.__dict__["x"] == 5
