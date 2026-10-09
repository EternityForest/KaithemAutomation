import os
import pty
import socket
import struct
import sys
import time

import stamina

"""Does NOT fully replace physically testing
 DMX due to the lack of detecting the special
dmx break."""

if "--collect-only" not in sys.argv:  # pragma: no cover
    from kaithem.src.chandler import (
        core,
        universes,
    )

    from . import test_chandler
    from .helpers import make_client
    from .test_chandler import TempGroup


async def test_fixtures_to_dmx():
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

        tc = await make_client()

        await tc.put(
            f"/chandler/api/set-fixture-class/{test_chandler.board.name}/TestFixtureType",
            json=fixtypes["TestFixtureType"],
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
                "__admin__",
                ["scv", cid, "default", "@testFixture", "red", 39],
                "test",
            )
            test_chandler.board._onmsg(
                "__admin__",
                ["scv", cid, "default", "@testFixture", "green", 51],
                "test",
            )
            test_chandler.board._onmsg(
                "__admin__",
                ["scv", cid, "default", "@testFixture", "blue", 96],
                "test",
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
                "__admin__",
                ["scv", cid, "default", "@testFixture", "green", 89],
                "test",
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


async def test_artnet_universe():
    """Create an Art-Net universe and a fixture, then verify that
    ArtDMX packets with the right header and channel data show up on a
    basic local UDP listener standing in for a physical node.

    The universe is pointed at a loopback address:port instead of the
    default 255.255.255.255:6454 broadcast, so the test is deterministic
    in a sandbox. The packet format is identical either way."""

    # Basic listener standing in for a physical Art-Net node.
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("", 0))
    listener.setblocking(False)
    port = listener.getsockname()[1]

    try:
        u = {
            "artnet_test": {
                "channels": 128,
                "framerate": 44,
                "number": 7,
                "type": "artnet",
                "interface": f"127.0.0.1:{port}",
            }
        }
        fixtype = {
            "channels": [
                {"name": "red", "type": "red"},
                {"name": "green", "type": "green"},
                {"name": "blue", "type": "blue"},
            ]
        }
        assignment = {
            "addr": 1,
            "name": "artnetTestFixture",
            "type": "ArtNetTestFixtureType",
            "universe": "artnet_test",
        }

        test_chandler.board._onmsg("__admin__", ["setconfuniverses", u], "test")

        tc = await make_client()
        await tc.put(
            f"/chandler/api/set-fixture-class/{test_chandler.board.name}"
            "/ArtNetTestFixtureType",
            json=fixtype,
        )

        test_chandler.board._onmsg(
            "__admin__",
            ["setFixtureAssignment", "artnetTestFixture", assignment],
            "test",
        )

        def latest_payload():
            """Drain every queued ArtDMX packet and return the payload of
            the newest one.

            The sender streams at a fixed framerate, so we must drain the
            backlog to see the current values instead of stale ones."""
            payload = None
            start = time.time()
            while True:
                if time.time() - start > 5:  # Timeout after 5 seconds
                    raise TimeoutError(
                        "Timeout waiting for latest Art-Net payload"
                    )
                try:
                    pkt = listener.recv(4096)
                except BlockingIOError:
                    break
                assert pkt[:8] == b"Art-Net\x00"
                # OpCode ArtDMX (0x5000), little endian
                assert pkt[8:10] == b"\x00\x50"
                # Protocol version 14
                assert pkt[10:12] == b"\x00\x0e"
                # Physical + SubUniverse, little endian
                assert struct.unpack("<H", pkt[14:16])[0] == 7
                # Length field matches the universe channel count
                assert struct.unpack(">H", pkt[16:18])[0] == len(
                    universes.universes["artnet_test"]().values
                )
                # DMX starts at channel 1, so payload[0] is universe index 1
                payload = pkt[18:]
            return payload

        with TempGroup() as grp:
            cid = grp.cue.id

            test_chandler.board._onmsg(
                "__admin__",
                ["add_cuef", cid, "default", "artnetTestFixture"],
                "test",
            )
            core.wait_frame()

            test_chandler.board._onmsg(
                "__admin__",
                ["scv", cid, "default", "@artnetTestFixture", "red", 11],
                "test",
            )
            test_chandler.board._onmsg(
                "__admin__",
                ["scv", cid, "default", "@artnetTestFixture", "green", 22],
                "test",
            )
            test_chandler.board._onmsg(
                "__admin__",
                ["scv", cid, "default", "@artnetTestFixture", "blue", 33],
                "test",
            )

            core.wait_frame()

            assert universes.universes["artnet_test"]().values[1] == 11

            # The set values should show up in the Art-Net payload.
            for attempt in stamina.retry_context(on=AssertionError):
                with attempt:
                    payload = latest_payload()
                    assert payload is not None
                    assert payload[0:3] == bytes([11, 22, 33])

            # Changing a value should update the output
            test_chandler.board._onmsg(
                "__admin__",
                ["scv", cid, "default", "@artnetTestFixture", "green", 44],
                "test",
            )

            for attempt in stamina.retry_context(on=AssertionError):
                with attempt:
                    payload = latest_payload()
                    assert payload is not None
                    assert payload[0:3] == bytes([11, 44, 33])

            # Make sure it keeps sending
            for attempt in stamina.retry_context(on=AssertionError):
                with attempt:
                    assert latest_payload() is not None
                    time.sleep(0.1)
                    assert latest_payload() is not None

    finally:
        # Stop the sender / clean up the universe we added.
        try:
            test_chandler.board._onmsg(
                "__admin__", ["setconfuniverses", {}], "test"
            )
        except Exception:
            pass
        listener.close()
