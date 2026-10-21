# SPDX-License-Identifier: GPL-3.0-or-later

import time

import pycrdt
import pytest
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


def test_syncdb_impl_merge():
    """Ensure our implementation lets us merge the top level keys.
    Merging nested keys will NOT work.
    """
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_test")

    db1 = syncdb.SyncDatabase.get(name + "_merge1")
    db2 = syncdb.SyncDatabase.get(name + "_merge2")

    d1 = db1.crdt.get("test_map", type=pycrdt.Map)
    d2 = db2.crdt.get("test_map", type=pycrdt.Map)

    d1["key1"] = "val1"
    d2["key2"] = "val2"

    db1.crdt.apply_update(db2.crdt.get_update())
    db2.crdt.apply_update(db1.crdt.get_update())

    assert db1.crdt.get("test_map", type=pycrdt.Map)["key1"] == "val1"
    assert db1.crdt.get("test_map", type=pycrdt.Map)["key2"] == "val2"

    assert db2.crdt.get("test_map", type=pycrdt.Map)["key1"] == "val1"
    assert db2.crdt.get("test_map", type=pycrdt.Map)["key2"] == "val2"


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


def test_syncdb_awareness_e2e():
    """End-to-end test: two databases sync awareness updates."""
    from kaithem.src import auth, syncdb

    # Ensure admin user exists
    auth.add_user("admin", "test-admin-password")
    auth.add_user_to_group("admin", "Administrators")

    server_url = "http://localhost:8002"

    name = _get_test_name("/test/syncdb_awareness_test")

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
    db1.awareness.set_local_state(
        {
            "user": {"name": "Jane Doe", "color": "#007ACC"},
        }
    )

    id = 0

    for attempt in stamina.retry_context(on=KeyError):
        with attempt:
            for i in db2.awareness.states:
                if "user" in db2.awareness.states[i]:
                    id = i
            assert db2.awareness.states[id]["user"]["name"] == "Jane Doe"

    client2.close()


def test_syncdb_awareness_e2e_reverse():
    """End-to-end test: two databases sync awareness updates."""
    from kaithem.src import auth, syncdb

    # Ensure admin user exists
    auth.add_user("admin", "test-admin-password")
    auth.add_user_to_group("admin", "Administrators")

    server_url = "http://localhost:8002"

    name = _get_test_name("/test/syncdb_awareness_test")

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
    db2.awareness.set_local_state(
        {
            "user": {"name": "Jane Doe", "color": "#007ACC"},
        }
    )

    id = 0

    for attempt in stamina.retry_context(on=KeyError):
        with attempt:
            for i in db1.awareness.states:
                if "user" in db1.awareness.states[i]:
                    id = i
            assert db1.awareness.states[id]["user"]["name"] == "Jane Doe"

    client2.close()


def test_syncdb_version_defaults_to_zero():
    """A fresh database has version 0 and sends that in its handshake."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_version_default")

    db = syncdb.SyncDatabase.get(name)

    assert db.version == 0
    assert syncdb.encode_version(db.version) == b"\x00" * 8


def test_syncdb_version_encode_decode_roundtrip():
    """Versions are unsigned 64 bit and must survive big timestamps."""
    from kaithem.src import syncdb

    for version in [0, 1, 65_536, 2**32, 2**52, 2**63 + 12_345]:
        encoded = syncdb.encode_version(version)
        assert len(encoded) == syncdb.VERSION_PAYLOAD_SIZE
        assert syncdb.decode_version(encoded) == version

    with pytest.raises(ValueError):
        syncdb.encode_version(-1)

    with pytest.raises(ValueError):
        syncdb.decode_version(b"\x00")


def test_syncdb_version_is_sane():
    """Versions more than an hour in the future are rejected."""
    from kaithem.src import syncdb

    now = int(time.time() * 1000)

    assert syncdb.version_is_sane(0)
    assert syncdb.version_is_sane(now - 1000)
    assert syncdb.version_is_sane(now + 30 * 60 * 1000)

    # Clearly beyond the one hour allowance.
    assert not syncdb.version_is_sane(
        now + syncdb.MAX_VERSION_FUTURE_MS + 60_000
    )
    assert not syncdb.version_is_sane(now + syncdb.MAX_VERSION_FUTURE_MS * 2)


def test_syncdb_version_message_sent_first():
    """A new subscriber must see the version before anything else."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_version_first")

    db = syncdb.SyncDatabase.get(name)

    sent = []

    def record_send(value, target=None, **kw):
        sent.append(value)

    db.widget.send_to = record_send

    db.widget.on_new_subscriber("user", "conn1")

    assert len(sent) == 2
    first = sent[0]
    assert first[:4] == syncdb.MSG_VERSION
    assert syncdb.decode_version(first[4:]) == db.version
    # The session ID must follow the version.
    assert sent[1]["session"] == db.document_session_id


def test_syncdb_begin_migration():
    """begin_migration seeds, migrates, saves and notifies listeners."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_migrate")

    calls = []

    def on_migration(old_db, old_version, new_db, new_version):
        calls.append((old_db, old_version, new_db, new_version))
        # Move application level data that can be merged.
        new_db.get("shared", type=pycrdt.Map)["carried"] = "yes"

    db = syncdb.SyncDatabase.get(name, on_migration=on_migration)

    old_doc = db.crdt
    old_session = db.document_session_id

    listener_calls = []
    db.add_document_listener(lambda: listener_calls.append("called"))

    assert db.version == 0

    new_version = int(time.time() * 1000)

    db.begin_migration(new_version, {"seeded": {"a": 1}})

    assert db.version == new_version

    assert len(calls) == 1
    old_db, old_version, new_db, migrated_version = calls[0]
    assert old_db is old_doc
    assert old_version == 0
    assert new_db is db.crdt
    assert migrated_version == new_version

    # The snapshot seeded the new document.
    assert db.crdt.get("seeded", type=pycrdt.Map)["a"] == 1
    # The callback contributed application level data.
    assert db.crdt.get("shared", type=pycrdt.Map)["carried"] == "yes"
    # The session changed so clients know to refetch.
    assert db.document_session_id != old_session
    # Listeners were notified exactly once.
    assert listener_calls == ["called"]


def test_syncdb_begin_migration_rejects_bad_versions():
    """begin_migration refuses stale or implausible versions."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_migrate_bad")

    db = syncdb.SyncDatabase.get(name)

    now = int(time.time() * 1000)

    # Must be greater than the current version of 0.
    with pytest.raises(ValueError):
        db.begin_migration(0, {"seeded": {}})

    db.begin_migration(now, {"seeded": {}})

    # Equal to the current version is still not an upgrade.
    with pytest.raises(ValueError):
        db.begin_migration(now, {"seeded": {}})

    # Anything an hour or more ahead of the clock is an error.
    with pytest.raises(ValueError):
        db.begin_migration(
            now + syncdb.MAX_VERSION_FUTURE_MS + 60_000, {"seeded": {}}
        )

    # A failed migration must not have changed anything.
    assert db.version == now


def test_syncdb_begin_migration_requires_shared_types():
    """Top level snapshot values must be maps or lists."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_migrate_types")

    db = syncdb.SyncDatabase.get(name)

    new_version = int(time.time() * 1000)

    with pytest.raises(TypeError):
        db.begin_migration(new_version, {"scalar": 12})

    # The failed migration must not have advanced the version.
    assert db.version == 0


def test_syncdb_incoming_migration_without_callback():
    """An incoming migration is ignored if no callback is configured."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_migrate_nocb")

    db = syncdb.SyncDatabase.get(name)

    new_version = int(time.time() * 1000)

    db._incoming_migration(new_version)

    assert db.version == 0


def test_syncdb_migration_syncs_over_websocket():
    """A client on a newer version forces the server to migrate."""
    from kaithem.src import auth, syncdb

    auth.add_user("admin", "test-admin-password")
    auth.add_user_to_group("admin", "Administrators")

    server_url = "http://localhost:8002"

    name = _get_test_name("/test/syncdb_migrate_e2e")

    server_migrations = []

    def server_on_migration(old_db, old_version, new_db, new_version):
        server_migrations.append((old_version, new_version))

    db1 = syncdb.SyncDatabase.get(name, on_migration=server_on_migration)

    db2 = syncdb.SyncDatabase.get(name + "_mirror")

    new_version = int(time.time() * 1000)

    # Pretend the client has already migrated to a newer schema.
    db2.version = new_version

    client2 = syncdb.WebsocketClient(
        db2,
        server_url,
        "admin",
        "test-admin-password",
        server_side_db_name=db1.name,
    )

    for attempt in stamina.retry_context(on=AssertionError):
        with attempt:
            assert client2.is_connected()

    for attempt in stamina.retry_context(on=AssertionError):
        with attempt:
            assert db1.version == new_version

    assert server_migrations == [(0, new_version)]

    client2.close()
