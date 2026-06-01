# SPDX-License-Identifier: GPL-3.0-or-later

import time

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
    assert db1.yjs_doc is not None


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
    doc = db.yjs_doc

    # Test basic YJS operations with pycrdt
    yarray = doc.get("test_array", type=doc.Array)
    yarray.append([1, 2, 3])

    assert len(yarray) == 3
    assert list(yarray) == [1, 2, 3]

    # Test YMap
    ymap = doc.get("test_map", type=doc.Map)
    ymap["key"] = "value"

    assert ymap["key"] == "value"


def test_syncdb_repr():
    """Test string representation."""
    from kaithem.src import syncdb

    name = _get_test_name("/test/syncdb_repr_test")

    db = syncdb.SyncDatabase.get(name)

    assert "SyncDatabase" in repr(db)
    assert name in repr(db)
