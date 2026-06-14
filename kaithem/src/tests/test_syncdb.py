# SPDX-License-Identifier: GPL-3.0-or-later

import time

import pycrdt
import stamina

from kaithem.src import auth, syncdb

# Use a global timestamp for test uniqueness
_test_timestamp = None


def _get_test_name(base: str) -> str:
    """Generate a unique test name using timestamp."""
    global _test_timestamp
    if _test_timestamp is None:
        _test_timestamp = str(time.time()).replace(".", "_")
    return f"{base}_{_test_timestamp}"


def test_syncdb_create_and_get():
    """Test that we can create and retrieve a SyncDatabase."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_test")

    # Create a new SyncDatabase
    db1 = syncdb.SyncDatabase.get(name)

    # Should be the same instance when we get it again
    db2 = syncdb.SyncDatabase.get(name)

    assert db1 is db2
    assert db1.name == name
    assert db1.crdt is not None


def test_syncdb_permissions():
    """Test that permissions can be set on the SyncDatabase."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_perms_test")

    db = syncdb.SyncDatabase.get(name)

    # Set permissions using string
    db.set_permissions("__guest__", "__guest__")

    # Set permissions using list
    db.set_permissions(["__guest__"], ["__guest__"])

    # Widget should exist
    assert db.widget is not None

    assert db.widget._read_perms == ["__guest__"]
    assert db.widget._write_perms == ["__guest__"]


def test_syncdb_yjs_integration():
    """Test basic YJS document operations via pycrdt."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_yjs_test")

    db = syncdb.SyncDatabase.get(name)
    doc = db.crdt

    # Test basic YJS operations with pycrdt
    yarray = doc.get("test_array", type=pycrdt.Array)
    yarray.extend([1, 2, 3])

    assert len(yarray) == 3
    assert list(yarray) == [1, 2, 3]

    # Test YMap
    ymap = doc.get("test_map", type=pycrdt.Map)
    ymap["key"] = "value"

    assert ymap["key"] == "value"


def test_syncdb_yjs_impl_queue_bloat():
    """Make sure the implementation works like we think it does."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_yjs_test")

    db = syncdb.SyncDatabase.get(name)
    doc = db.crdt

    test = doc.get("test", type=pycrdt.Array)
    for i in range(100):
        test.append({"val": i})

    sz = len(db.crdt.get_update())

    db2 = syncdb.SyncDatabase.get(name + str(i))
    doc2 = db2.crdt
    doc2.apply_update(doc.get_update())
    test2 = doc2.get("test", type=pycrdt.Array)

    for i in range(500):
        test2.append({"val": i})
        del test2[0]

        db.crdt.apply_update(db2.crdt.get_update())

    test = doc.get("test", type=pycrdt.Array)

    assert test[0]["val"] > 101
    assert len(test) == 100

    sz2 = len(db.crdt.get_update())

    assert sz2 < sz * 1.2


def test_syncdb_yjs_impl_bloat_two_writer():
    """Make sure a two writer overwriting a key doesn't cause infinite bloat."""

    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_yjs_test")

    db = syncdb.SyncDatabase.get(name)

    doc = db.crdt
    shouldbe = 2

    test = doc.get("test", type=pycrdt.Map)
    test["key"] = {"val": shouldbe}

    sz = len(db.crdt.get_update())

    db2 = syncdb.SyncDatabase.get(name + "_writer")
    doc2 = db2.crdt
    doc2.apply_update(doc.get_update())

    db3 = syncdb.SyncDatabase.get(name + "_writer")
    doc3 = db3.crdt
    doc3.apply_update(doc.get_update())

    for i in range(100):
        # Nonsense that gets overwritten to test interleaved dual writers
        test2 = doc3.get("test", type=pycrdt.Map)
        test2["key"] = {"val": shouldbe * 2}
        db.crdt.apply_update(db3.crdt.get_update())

        test = doc2.get("test", type=pycrdt.Map)

        shouldbe += 1
        # doc2["test"] = pycrdt.Map()
        test["key"] = {"val": shouldbe}

        db.crdt.apply_update(db2.crdt.get_update())

    test = doc.get("test", type=pycrdt.Map)

    assert test["key"]["val"] == shouldbe

    sz2 = len(db.crdt.get_update())
    # Less than 1 byte per interleaved write
    assert sz2 < sz + 100

    assert len(db.crdt.get_state()) < 50

    # But also make sure the state vector expands when
    # it seems like it should, create some non overlapping
    # data that seems like it should expand things.

    sz = len(db.crdt.get_state())

    db2 = syncdb.SyncDatabase.get(name + "jhgfdfghjkl")
    doc2 = db2.crdt
    test2 = doc2.get("test2", type=pycrdt.Map)
    test2["key"] = shouldbe

    db.crdt.apply_update(db2.crdt.get_update())

    assert doc.get("test2", type=pycrdt.Map)["key"] == shouldbe

    assert len(db.crdt.get_state()) > sz


# def test_syncdb_yjs_impl_bloat_multi_writer_cleanup_attemp():
#     from kaithem.src import syncdb

#     name = _get_test_name("/test/syncdb_yjs_test")

#     db = syncdb.SyncDatabase.get(name)

#     doc = db.crdt
#     shouldbe = 2

#     test = doc.get("test", type=pycrdt.Map)
#     test["key"] = {"val": shouldbe}

#     client_ids_seen = {}

#     for i in range(150):
#         db2 = syncdb.SyncDatabase.get(name + str(i))
#         doc2 = db2.crdt

#         doc2.apply_update(doc.get_update())

#         client_ids_seen[doc2.client_id] = True

#         test = doc2.get("test", type=pycrdt.Map)

#         assert isinstance(test["key"]["val"], float)

#         shouldbe += 1
#         # doc2["test"] = pycrdt.Map()
#         test["key"] = {"val": shouldbe}

#         db.crdt.apply_update(db2.crdt.get_update())

#     test = doc.get("test", type=pycrdt.Map)

#     assert test["key"]["val"] == shouldbe

#     # Try to wipe everything out with a hard overwrite
#     # It doesn't work.
#     db.crdt["test"] = pycrdt.Map({"key": pycrdt.Map({"val": shouldbe})})

#     assert int(doc.get("test", type=pycrdt.Map)["key"]["val"]) == shouldbe
#     assert len(db.crdt.get_update()) < 1000


# def test_syncdb_yjs_impl_bloat_multi_writer():
#     # Note: This does in fact do a lot of bloat.
#     # We can't fix that because that's just how the library do be
#     # like
#     from kaithem.src import syncdb

#     name = _get_test_name("/test/syncdb_yjs_test")

#     db = syncdb.SyncDatabase.get(name)

#     doc = db.crdt
#     shouldbe = 2

#     test = doc.get("test", type=pycrdt.Map)
#     test["key"] = {"val": shouldbe}

#     sz = len(db.crdt.get_update())

#     client_ids_seen = {}

#     for i in range(100):
#         db2 = syncdb.SyncDatabase.get(name + str(i))
#         doc2 = db2.crdt

#         doc2.apply_update(doc.get_update())

#         client_ids_seen[doc2.client_id] = True

#         test = doc2.get("test", type=pycrdt.Map)

#         assert isinstance(test["key"]["val"], float)

#         shouldbe += 1
#         # doc2["test"] = pycrdt.Map()
#         test["key"] = {"val": shouldbe}

#         db.crdt.apply_update(db2.crdt.get_update())

#     test = doc.get("test", type=pycrdt.Map)

#     assert test["key"]["val"] == shouldbe

#     sz2 = len(db.crdt.get_update())
#     assert sz2 < 5000

#     # Be sure that pycrdt is doing it's secret undocumented
#     # background client ID thing.  It does not do that,
#     # So the state size does in fact grow.
#     assert len(db.crdt.get_state()) < 1000
#     assert len(client_ids_seen) > 99

#     # Getting the update and refreshing the doc should
#     # shrink the state vector ideally, but it does not.
#     db3 = syncdb.SyncDatabase.get(name + "jhgfdfghjklu654w")
#     doc3 = db3.crdt
#     doc3.apply_update(doc.get_update())

#     assert int(doc.get("test", type=pycrdt.Map)["key"]["val"]) == shouldbe
#     assert len(db.crdt.get_state()) < 100


def test_syncdb_repr():
    """Test string representation."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_repr_test")

    db = syncdb.SyncDatabase.get(name)

    assert "SyncDatabase" in repr(db)
    assert name in repr(db)


def test_syncdb_websocket_client():
    """Test that WebsocketClient can connect and sync with a server."""

    # Ensure admin user exists (should already from conftest.py)
    auth.add_user("admin", "test-admin-password")
    auth.add_user_to_group("admin", "Administrators")

    name = _get_test_name("/test/syncdb_ws_test")

    # Create a database
    db = syncdb.SyncDatabase.get(name)

    server_url = "http://localhost:8002"

    # Create a websocket client (this will try to connect)
    # We just test that it can be created and closed
    client = syncdb.WebsocketClient(
        db, server_url, "admin", "test-admin-password"
    )

    for attempt in stamina.retry_context(on=AssertionError):
        with attempt:
            assert client.is_connected()

    # Close the client
    client.close()

    # Should not be running after close
    assert not client.is_connected()


def test_syncdb_sync_e2e():
    """End-to-end test: two databases sync via WebsocketClient."""
    from kaithem.src import auth, syncdb

    # Ensure admin user exists
    auth.add_user("admin", "test-admin-password")
    auth.add_user_to_group("admin", "Administrators")

    server_url = "http://localhost:8002"

    name = _get_test_name("/test/syncdb_e2e_test")

    # Create two databases
    db1 = syncdb.SyncDatabase.get(name)
    db2 = syncdb.SyncDatabase.get(name + "_mirror")

    client2 = syncdb.WebsocketClient(
        db2,
        server_url,
        "admin",
        "test-admin-password",
        server_side_db_name=db1.name,
    )

    # Wait for connections
    for attempt in stamina.retry_context(on=AssertionError):
        with attempt:
            assert client2.is_connected()

    # Make a change to db1
    yarray = db1.crdt.get("test_array", type=pycrdt.Array)
    yarray.extend([1, 2, 3])

    for attempt in stamina.retry_context(on=AssertionError):
        with attempt:
            assert len(db2.crdt.get("test_array", type=pycrdt.Array)) == 3

    client2.close()

    assert db1.name == name
    assert db2.name == name + "_mirror"
