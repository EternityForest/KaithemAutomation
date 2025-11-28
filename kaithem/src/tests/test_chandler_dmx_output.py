import os
import pty
import sys
import time

import stamina

"""Does NOT fully replace physically testing DMX due to the lack of detecting the special
dmx break."""

if "--collect-only" not in sys.argv:  # pragma: no cover
    from kaithem.src.chandler import (
        core,
        universes,
    )

    from . import test_chandler
    from .test_chandler import TempGroup


def test_fixtures_to_dmx():
    """Create a universe, a fixture type, and a fixture,
    add the fixture to a group, che/ck the universe vals
    """

    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)
    try:
        print(f"Virtual serial port created at: {slave_name}")

        u = {
            "dmx": {
                "channels": 512,
                "framerate": 44,
                "number": 1,
                "type": "enttecopen",
                "interface": slave_name,
            }
        }
        fixtypes = {
            "TestFixtureType": {
                "channels": [
                    {"name": "red", "type": "red"},
                    {"name": "green", "type": "green"},
                    {"name": "blue", "type": "blue"},
                    {"name": "dim", "type": "intensity"},
                    {"name": "dim_fine", "type": "fine", "coarse": "dim"},
                    {"name": "mode", "type": "fixed", "value": 4},
                ]
            }
        }

        fixture_assignments = {
            "testFixture": {
                "addr": 1,
                "name": "testFixture",
                "type": "TestFixtureType",
                "universe": "dmx",
            }
        }

        test_chandler.board._onmsg("__admin__", ["setconfuniverses", u], "test")

        # Should be a buncha zeros
        x = b""
        for attempt in stamina.retry_context(on=AssertionError):
            with attempt:
                x += os.read(master_fd, 1024)
                assert bytes([0, 0, 0, 0, 0, 0]) in x

        test_chandler.board._onmsg(
            "__admin__",
            ["setfixtureclass", "TestFixtureType", fixtypes["TestFixtureType"]],
            "test",
        )

        test_chandler.board._onmsg(
            "__admin__",
            [
                "setFixtureAssignment",
                "testFixture",
                fixture_assignments["testFixture"],
            ],
            "test",
        )

        with TempGroup() as grp:
            cid = grp.cue.id
            ## 0s are the pattern spacing
            core.wait_frame()

            test_chandler.board._onmsg(
                "__admin__", ["add_cuef", cid, "default", "testFixture"], "test"
            )
            core.wait_frame()

            test_chandler.board._onmsg(
                "__admin__", ["scv", cid, "@testFixture", "red", 39], "test"
            )
            test_chandler.board._onmsg(
                "__admin__", ["scv", cid, "@testFixture", "green", 51], "test"
            )
            test_chandler.board._onmsg(
                "__admin__", ["scv", cid, "@testFixture", "blue", 96], "test"
            )

            core.wait_frame()

            assert universes.universes["dmx"]().values[0] == 0
            assert universes.universes["dmx"]().values[1] == 39

            x = b""

            for attempt in stamina.retry_context(on=AssertionError):
                with attempt:
                    x += os.read(master_fd, 1024)
                    assert bytes([0, 39, 51, 96, 0]) in x

            # Changing a val should update the output
            test_chandler.board._onmsg(
                "__admin__", ["scv", cid, "@testFixture", "green", 89], "test"
            )

            x = b""
            for attempt in stamina.retry_context(on=AssertionError):
                with attempt:
                    x += os.read(master_fd, 1024)
                    assert bytes([0, 39, 89, 96, 0, 0, 4]) in x

            # Make sure it keeps sending, and that the frames line up
            for attempt in stamina.retry_context(on=AssertionError):
                with attempt:
                    x = b""
                    time.sleep(0.1)
                    x += os.read(master_fd, 1024)
                    assert x.startswith(bytes([0, 39, 89, 96, 0]))

    finally:
        os.close(master_fd)
        os.close(slave_fd)
