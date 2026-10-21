# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import threading
import time
import uuid
import weakref
from collections.abc import Callable
from typing import Any, Protocol

import pycrdt
import quart
import structlog

from kaithem.src import pages

from . import quart_app, widget_api, widgets

"""
SyncDatabase provides a YJS document for collaborative editing.

YJS has a few oddities to work around.

Long term documents that have many writer
sessions coming and going will eventually get bloated with client IDs.

One writer, many reader documents do not have this problem as much.

Kaithem uses a workaround where the server assigns persistent to each browser
tab, so things should very often "just work".

There is currently no way to clean this up except by starting all over.

If you have a bunch of python nodes and you want to wipe the document
and start over, you must reboot them all at the same time, or the one that still
has the data will re-spread it to everything else.


YJS top level keys are not deletable, but they are referenced by name instead of
ID.  You can merge two top level lists with the same name even on two documents
created totally separately, but nested items do not merge like that.


See https://yjs.dev for more information.
"""

# Message type codes for WebSocket communication (4-byte big-endian)
MSG_UPDATE = b"\x00\x00\x00\x01"  # Regular YJS document updates
MSG_AWARENESS = b"\x00\x00\x00\x02"  # YJS Awareness updates
MSG_VERSION = b"\x00\x00\x00\x03"  # Database version handshake

# Versions are millisecond timestamps stored as unsigned 64-bit integers.
VERSION_PAYLOAD_SIZE = 8

# Anything more than an hour ahead of local time is treated as an error.
MAX_VERSION_FUTURE_MS = 60 * 60 * 1000

logger = structlog.get_logger(__name__)

OnMigration = Callable[[pycrdt.Doc, int, pycrdt.Doc, int], None]
"""Callback invoked when a database is migrated.

The callback receives the old document, the old version, a fresh
document it should populate with any application level data worth
keeping, and the new version.
"""


def encode_version(version: int) -> bytes:
    """Encode a version number as 8 big-endian bytes.

    Versions are millisecond timestamps that may exceed 32 bits, so they
    are always encoded as unsigned 64-bit integers.
    """
    if version < 0:
        raise ValueError("Version cannot be negative")
    return version.to_bytes(VERSION_PAYLOAD_SIZE, "big")


def decode_version(payload: bytes) -> int:
    """Decode an 8-byte big-endian version number."""
    if len(payload) != VERSION_PAYLOAD_SIZE:
        raise ValueError(
            f"Version payload must be {VERSION_PAYLOAD_SIZE} bytes, "
            f"got {len(payload)}"
        )
    return int.from_bytes(payload, "big")


def version_is_sane(version: int) -> bool:
    """Check that a version is not implausibly far in the future.

    Versions are millisecond timestamps. Anything one hour or more ahead
    of the local clock is treated as an error.
    """
    now_ms = int(time.time() * 1000)
    return version < now_ms + MAX_VERSION_FUTURE_MS


def _to_crdt(value: Any) -> Any:
    """Convert a JSON-like value into mergeable pycrdt shared types.

    Maps become pycrdt.Map and lists become pycrdt.Array so that they can
    merge across documents. Other values are returned unchanged.
    """
    if isinstance(value, dict):
        return pycrdt.Map({key: _to_crdt(item) for key, item in value.items()})
    if isinstance(value, list):
        return pycrdt.Array([_to_crdt(item) for item in value])
    return value


def _seed_document(document: pycrdt.Doc, snapshot: dict[str, Any]) -> None:
    """Populate a document from a JSON-like map of top level keys.

    Top level YJS values must be shared types (maps or lists), so scalar
    values are rejected rather than silently stored in an unmergeable way.
    """
    if not isinstance(snapshot, dict):
        raise TypeError("Migration snapshot must be a map object")

    for key, value in snapshot.items():
        converted = _to_crdt(value)
        if not isinstance(converted, (pycrdt.Map, pycrdt.Array)):
            raise TypeError(
                f"Top level migration value for {key!r} must be a map or list"
            )
        document[key] = converted


class Unobservable(Protocol):
    """Anything with a pycrdt style unobserve method.

    Both pycrdt.Doc and pycrdt.Awareness implement this, and both have
    thread affine subscriptions. A document takes the Subscription object
    returned by observe, while awareness takes the string id it returned.
    """

    def unobserve(self, subscription: Any) -> None: ...


def _unobserve(
    observable: Unobservable,
    subscription: pycrdt.Subscription | str | None,
    owner_thread: int | None,
) -> None:
    """Unregister an observer when it is safe to do so.

    pycrdt subscriptions are thread affine: dropping one from a thread
    other than the one that created it panics. When we are not on the
    owning thread we simply return and let garbage collection handle it,
    rather than risking the panic.
    """
    if subscription is None:
        return
    if owner_thread is not None and threading.get_ident() != owner_thread:
        return

    try:
        observable.unobserve(subscription)
    except ValueError:
        pass
    except Exception:
        logger.exception("Failed to unobserve")


# Global registry - uses weak references like tagpoints
# Indexed by document session ID
allSyncDbs: dict[str, weakref.ref[SyncDatabase]] = {}


lock = threading.RLock()


class SyncDatabaseWidget(widgets.DataSource):
    def __init__(self, id: str, db: SyncDatabase):
        super().__init__(id=id)
        self._db = db
        # The version message must be the very first thing every
        # subscriber sees, so we send it ourselves instead of letting the
        # widget send its value on connect.
        self.noOnConnectData = True
        # The generic echo would rebroadcast client traffic to everyone,
        # bypassing the version gate that decides whose updates are
        # trusted. Updates are broadcast explicitly instead.
        self.echo = False

    def on_new_subscriber(self, user, connection_id, **kw):
        """Send the version first, then the document session ID."""
        db = self._db
        db.send_version(connection_id)
        self.send_to(
            {
                "session": db.document_session_id,
            },
            connection_id,
        )

    def on_subscriber_disconnected(self, user, connection_id, **kw):
        """Forget the version a disconnected subscriber reported."""
        self._db._connection_versions.pop(connection_id, None)


class SyncDatabase:
    """
    A SyncDatabase holds a YJS document and provides collaborative editing
    capabilities. It can be accessed through a global registry using weak refs.

    Like tag points, these are created on demand if you try to get() one
    that does not exist. Only one per name can ever exist. Nobody can ever
    delete them from the global registry, you just delete your reference
    and let GC handle it.
    """

    def __init__(self, name: str, on_migration: OnMigration | None = None):
        global allSyncDbs

        if not name:
            raise ValueError("SyncDatabase name cannot be empty")

        if not name.startswith("/"):
            name = "/" + name

        self.document_session_id = uuid.uuid4().hex
        """The document session ID.
        Used to track when clients need to completely replace the document"""

        # Normalize name - use similar rules to tagpoints
        self.name = name
        """The name of the sync database"""

        self._crdt = pycrdt.Doc(allow_multithreading=True)
        """The underlying YJS document"""

        self.awareness = pycrdt.Awareness(self._crdt)
        """The YJS awareness document"""

        self.version: int = 0
        """The application level schema version of this database.

        This is a millisecond timestamp, or 0 if no migration occurred.
        """

        self._on_migration = on_migration
        """Optional callback invoked when this database is migrated."""

        self._connection_versions: dict[str, int] = {}
        """Maps subscriber connection IDs to the version they reported."""

        self._document_listeners: set[Callable[[], None]] = set()
        """Callbacks invoked when the underlying document is replaced."""

        self._widget: widgets.DataSource | None = None
        """The widget used for subscribing to updates"""

        self._lock = threading.RLock()

        self.accept_updates = False
        """Whether to accept any updates from websockets.
           If true, anything you put will likely be put back by
           a client reconnecting after reboots.
        """

        # Create the DataSource widget for this database
        self._widget = SyncDatabaseWidget(id=f"syncdb:{name}", db=self)

        self.widget.set_permissions(
            read=["system_admin"], write=["system_admin"]
        )

        # Subscribe to the widget - every message is an update to apply
        self.widget.attach2(self._on_widget_message)

        with lock:
            if name in allSyncDbs:
                raise ValueError(f"SyncDatabase {name} already exists")
            allSyncDbs[name] = weakref.ref(self)

        self._doc_subscription = self._crdt.observe(self._on_doc_update)
        self._awareness_subscription = self.awareness.observe(
            self._on_awareness_update
        )

    @property
    def crdt(self) -> pycrdt.Doc:
        """The underlying YJS document. To use this class,
        Interact directly with the CRDT.
        """
        return self._crdt

    def _on_doc_update(self, evt: pycrdt.TransactionEvent):
        self.broadcast_update(evt.update)

    def _on_awareness_update(
        self, type: str, changes: tuple[dict[str, Any], Any]
    ) -> None:
        if type != "update" or changes[1] != "local":
            return

        updated_clients = [v for value in changes[0].values() for v in value]
        state = self.awareness.encode_awareness_update(updated_clients)
        self.broadcast_awareness(state)

    def _on_widget_message(self, acting_user: str, value: Any, conn_id: str):
        """Handle incoming messages from the widget subscription."""
        if value is None:
            return

        if not isinstance(value, bytes):
            return

        # Check message type code (first 4 bytes)
        if len(value) < 4:
            return

        msg_type = value[:4]
        payload = value[4:]

        # The version message is always handled, even when we are not
        # accepting updates, because it establishes the protocol state.
        if msg_type == MSG_VERSION:
            self._on_version_message(conn_id, payload)
            return

        if not self.accept_updates:
            return

        # Ignore traffic from a remote that is not on our version.
        if self._connection_versions.get(conn_id) != self.version:
            return

        if msg_type == MSG_UPDATE:
            if self.accept_updates:
                # Applying to our own document broadcasts it on to
                # everyone else as well.
                try:
                    self.crdt.apply_update(payload)
                except Exception:
                    logger.exception(
                        "Failed to apply YJS update", database=self.name
                    )
            else:
                # We do not own the authoritative copy, but we can still
                # relay the update to the other peers.
                self.widget.send(
                    MSG_UPDATE + payload, exclude_connection_id=conn_id
                )
        elif msg_type == MSG_AWARENESS:
            self.awareness.apply_awareness_update(payload, self)
            self.widget.send(
                MSG_AWARENESS + payload, exclude_connection_id=conn_id
            )

    def _on_version_message(self, conn_id: str, payload: bytes) -> None:
        """Record the version a remote reported and migrate if needed."""
        try:
            remote_version = decode_version(payload)
        except ValueError:
            logger.warning(
                "Ignoring malformed version message", database=self.name
            )
            return

        if not version_is_sane(remote_version):
            logger.error(
                "Ignoring version too far in the future",
                database=self.name,
                remote_version=remote_version,
            )
            return

        self._connection_versions[conn_id] = remote_version

        if remote_version > self.version:
            logger.info(
                "Remote reported a newer version, migrating",
                database=self.name,
                remote_version=remote_version,
                version=self.version,
            )
            self._incoming_migration(remote_version)
        elif remote_version < self.version:
            logger.warning(
                "Remote reported an older version, ignoring its updates",
                database=self.name,
                remote_version=remote_version,
                version=self.version,
            )

    @property
    def widget(self) -> widgets.DataSource:
        """Return the underlying widget for this database."""
        return self._widget

    def set_permissions(
        self, read: list[str] | str, write: list[str] | str
    ) -> None:
        """
        Set permissions on the underlying widget.

        Args:
            read: Read permissions (can be list or comma-separated string)
            write: Write permissions (can be list or comma-separated string)
        """
        if not self.widget:
            return

        if isinstance(read, str):
            read = [i.strip() for i in read.split(",") if i.strip()]
        if isinstance(write, str):
            write = [i.strip() for i in write.split(",") if i.strip()]

        self.widget.set_permissions(read, write)

        self.widget.send(
            {
                "session": self.document_session_id,
            }
        )

    def broadcast_update(self, update: bytes) -> None:
        """
        Broadcast a YJS update to all subscribers.

        Args:
            update: The YJS update bytes to broadcast
        """
        if not self.widget:
            return

        # Prefix with type code (MSG_UPDATE)
        self.widget.send(MSG_UPDATE + update)

    def broadcast_awareness(self, awareness_update: bytes) -> None:
        """
        Broadcast an awareness update to all subscribers.

        Args:
            awareness_update: The YJS awareness update bytes to broadcast
        """
        if not self.widget:
            return

        # Prefix with type code (MSG_AWARENESS)
        self.widget.send(MSG_AWARENESS + awareness_update)

    def send_version(self, connection_id: str | None = None) -> None:
        """Send the database version to subscribers.

        The version message must always be the first message a subscriber
        receives, and is re-sent after a successful migration.

        Args:
            connection_id: Send to one connection, or all if None.
        """
        if not self.widget:
            return

        message = MSG_VERSION + encode_version(self.version)
        if connection_id is None:
            self.widget.send(message)
        else:
            self.widget.send_to(message, connection_id)

    def add_document_listener(self, callback: Callable[[], None]) -> None:
        """Register a callback invoked when the document is replaced."""
        self._document_listeners.add(callback)

    def remove_document_listener(self, callback: Callable[[], None]) -> None:
        """Unregister a callback added with add_document_listener."""
        self._document_listeners.discard(callback)

    def begin_migration(self, version: int, snapshot: dict[str, Any]) -> None:
        """Migrate the database to a new version.

        Builds a new document from the given JSON-like snapshot of top
        level keys, then hands the old and new documents to the optional
        migration callback so any application level data that can be
        merged is carried over. The new document and version are saved and
        the migration is broadcast to subscribers.

        Args:
            version: The new version number (a millisecond timestamp).
            snapshot: A JSON-like map of top level keys for the new doc.
        """
        if not version_is_sane(version):
            raise ValueError(
                f"Migration version is too far in the future: {version}"
            )
        if version <= self.version:
            raise ValueError(
                f"Migration version {version} must be greater than the "
                f"current version {self.version}"
            )

        self._migrate(version, snapshot)

    def _incoming_migration(self, new_version: int) -> None:
        """Migrate in response to a remote reporting a newer version."""
        if self._on_migration is None:
            logger.error(
                "Received a migration but no on_migration callback is set, "
                "ignoring",
                database=self.name,
                new_version=new_version,
            )
            return

        # No snapshot is available locally, so the callback must rebuild
        # the application state and the remote will fill in the rest.
        self._migrate(new_version, None)

    def _migrate(
        self, new_version: int, snapshot: dict[str, Any] | None
    ) -> None:
        """Run a migration and swap in the resulting document."""
        old_db = self._crdt
        old_version = self.version

        new_db = pycrdt.Doc(allow_multithreading=True)
        if snapshot is not None:
            _seed_document(new_db, snapshot)

        if self._on_migration is not None:
            self._on_migration(old_db, old_version, new_db, new_version)

        self._apply_new_document(new_db, new_version)

    def _apply_new_document(self, new_db: pycrdt.Doc, new_version: int) -> None:
        """Replace the underlying document and broadcast the change."""
        with self._lock:
            # The old document and its subscriptions are simply
            # dereferenced, not explicitly unobserved. A subscription
            # panics if it is dropped on a thread other than the one that
            # created it, and this may run elsewhere, but a subscription
            # that is still attached to its document is safe to release
            # anywhere. The document is discarded along with it.
            self._crdt = new_db
            self.version = new_version
            self.document_session_id = uuid.uuid4().hex
            self.awareness = pycrdt.Awareness(self._crdt)

            self._doc_subscription = self._crdt.observe(self._on_doc_update)
            self._awareness_subscription = self.awareness.observe(
                self._on_awareness_update
            )

            # Existing connections are now out of date until they report
            # the new version.
            self._connection_versions.clear()

        for listener in list(self._document_listeners):
            try:
                listener()
            except Exception:
                logger.exception(
                    "Error in document listener", database=self.name
                )

        # The version must go out first, then the new session and state.
        self.send_version()
        if self.widget:
            self.widget.send({"session": self.document_session_id})
        self.broadcast_update(self._crdt.get_update())

    def __repr__(self) -> str:
        return f"<SyncDatabase: {self.name}>"

    @classmethod
    def get(
        cls, name: str, on_migration: OnMigration | None = None
    ) -> SyncDatabase:
        """
        Get a SyncDatabase by name. Creates one if it doesn't exist.

        This is similar to how TagPoints work - creates on demand,
        returns existing if found.
        """
        global allSyncDbs
        if not name.startswith("/"):
            name = "/" + name

        with lock:
            if name in allSyncDbs:
                existing = allSyncDbs[name]()
                if existing is not None:
                    if on_migration is not None:
                        existing._on_migration = on_migration
                    return existing

            # Create new one
            return cls(name, on_migration)

    def __del__(self):
        global allSyncDbs

        with lock:
            if hasattr(self, "name") and self.name in allSyncDbs:
                try:
                    del allSyncDbs[self.name]
                except Exception:
                    pass


class WebsocketClient:
    """
    WebSocket client for syncing a SyncDatabase with a remote server.

    Maintains a weak reference to the database - if the database is deleted,
    this client will stop.
    """

    def __init__(
        self,
        database: SyncDatabase,
        server: str,
        username: str,
        password: str,
        server_side_db_name: str | None = None,
    ):
        """
        Initialize the WebSocket client.

        Args:
            database: The SyncDatabase to sync (kept via weak reference)
            server: The server URL (e.g., "http://localhost:8010")
            username: Username for authentication
            password: Password for authentication
        """
        self._db_ref: weakref.ref[SyncDatabase] = weakref.ref(database)
        self._server = server
        self._username = username
        self._password = password

        # The channel name matches the widget ID format
        self._channel = f"syncdb:{server_side_db_name or database.name}"

        self._client: widget_api.WidgetApiClient | None = None
        self._running = False

        # The version the remote reported, or None until we learn it.
        self._remote_version: int | None = None

        # The thread that created the pycrdt subscriptions, so that we
        # only unobserve from that thread.
        self._owner_thread = threading.get_ident()
        self._closed = False

        self._doc_subscription = database.crdt.observe(self._on_doc_update)
        self._awareness_subscription = database.awareness.observe(
            self._on_awareness_update
        )
        database.add_document_listener(self._on_document_replaced)

        # Start the client
        self._start()

    def _start(self) -> None:
        """Start the websocket client."""
        self._running = True

        # Create the client and subscribe
        self._client = widget_api.WidgetApiClient(
            self._server,
            self._username,
            self._password,
            on_connect=self._on_connected,
        )

        # Subscribe to the channel to receive updates
        self._client.subscribe(self._channel, self._on_message)

    def _on_connected(self) -> None:
        """Advertise our version as the very first message."""
        db = self._db_ref()
        if db is None:
            self.close()
            return

        # We do not know the remote's version until it tells us.
        self._remote_version = None

        # The version message must always come first, then our state so
        # that the remote can merge whatever we already have.
        self._send_version()
        self._send_state()

    def _send_version(self) -> None:
        """Send our current version to the remote."""
        if not self._client:
            return

        db = self._db_ref()
        if db is None:
            self.close()
            return

        self._client.send(
            self._channel, MSG_VERSION + encode_version(db.version)
        )

    def _send_state(self) -> None:
        """Send the full document state to the remote."""
        if not self._client:
            return

        db = self._db_ref()
        if db is None:
            self.close()
            return

        self._client.send(self._channel, MSG_UPDATE + db.crdt.get_update())

    def _on_message(self, value: Any) -> None:
        """Handle incoming messages from the remote."""
        if value is None:
            return

        db = self._db_ref()
        if db is None:
            # Database was deleted, stop
            self.close()
            return

        if not isinstance(value, bytes) or len(value) < 4:
            return

        msg_type = value[:4]
        payload = value[4:]

        # The version message is always handled first.
        if msg_type == MSG_VERSION:
            self._on_version_message(payload)
            return

        # Ignore traffic from a remote that is not on our version.
        if self._remote_version != db.version:
            return

        if msg_type == MSG_UPDATE:
            try:
                db.crdt.apply_update(payload)
            except Exception:
                logger.exception("Failed to apply YJS update", database=db.name)
        elif msg_type == MSG_AWARENESS:
            db.awareness.apply_awareness_update(payload, self)

    def _on_version_message(self, payload: bytes) -> None:
        """Record the remote version and migrate if it is newer."""
        db = self._db_ref()
        if db is None:
            self.close()
            return

        try:
            remote_version = decode_version(payload)
        except ValueError:
            logger.warning(
                "Ignoring malformed version message", database=db.name
            )
            return

        if not version_is_sane(remote_version):
            logger.error(
                "Ignoring version too far in the future",
                database=db.name,
                remote_version=remote_version,
            )
            return

        self._remote_version = remote_version

        if remote_version > db.version:
            logger.info(
                "Remote reported a newer version, migrating",
                database=db.name,
                remote_version=remote_version,
                version=db.version,
            )
            # This swaps in a new document and calls
            # _on_document_replaced, which re-sends the version.
            db._incoming_migration(remote_version)
        else:
            # Either we are ahead, or we just need the remote to know
            # what version we are on so it trusts our updates.
            self._send_version()

    def _on_document_replaced(self) -> None:
        """Re-observe and advertise a document that was just migrated."""
        db = self._db_ref()
        if db is None:
            return

        self._doc_subscription = db.crdt.observe(self._on_doc_update)
        self._awareness_subscription = db.awareness.observe(
            self._on_awareness_update
        )
        # The new subscriptions were created on this thread.
        self._owner_thread = threading.get_ident()

        # The new version must go out before any other traffic.
        self._send_version()
        self._send_state()

    def _on_doc_update(self, evt: pycrdt.TransactionEvent):
        self.send_update(evt.update)

    def _on_awareness_update(
        self, type: str, changes: tuple[dict[str, Any], Any]
    ) -> None:
        if type != "update" or changes[1] != "local":
            return

        db = self._db_ref()
        if db is None:
            self.close()
            return

        updated_clients = [v for value in changes[0].values() for v in value]
        state = db.awareness.encode_awareness_update(updated_clients)
        self.send_awareness(state)

    def send_update(self, update: bytes) -> None:
        """
        Send a YJS update to the server.

        Args:
            update: The YJS update bytes to send
        """
        if not self._client:
            return

        db = self._db_ref()
        if db is None:
            self.close()
            return

        # Send via the widget API with type code prefix
        self._client.send(self._channel, MSG_UPDATE + update)

    def send_awareness(self, awareness_update: bytes) -> None:
        """
        Send an awareness update to the server.

        Args:
            awareness_update: The YJS awareness update bytes to send
        """
        if not self._client:
            return

        # Send via the widget API with type code prefix
        self._client.send(self._channel, MSG_AWARENESS + awareness_update)

    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return (
            self._client is not None
            and self._running
            and self._client.connected
        )

    def close(self) -> None:
        """Close the WebSocket connection. Can be called from any thread."""
        if self._closed:
            return
        self._closed = True
        self._running = False

        if self._client:
            try:
                self._client.close()
            except Exception:
                logger.exception("Failed to close client")
            self._client = None

        db = self._db_ref()
        if db:
            try:
                _unobserve(
                    db.crdt,
                    self._doc_subscription,
                    self._owner_thread,
                )
                _unobserve(
                    db.awareness,
                    self._awareness_subscription,
                    self._owner_thread,
                )
                db.remove_document_listener(self._on_document_replaced)
            except Exception:
                logger.exception(
                    "Failed to unobserve document", database=db.name
                )
            # Release our references on this thread. Once a subscription
            # has been dropped it panics if it is deallocated on another
            # thread, so it must not be left for some other thread's
            # garbage collection to find.
            self._doc_subscription = None
            self._awareness_subscription = None

    def __del__(self):
        """Cleanup when the client is garbage collected."""
        self.close()


# State vector sync endpoint
# Client sends their state vector, server returns updates needed
@quart_app.app.route("/api/syncdb/<path:document_name>/sync", methods=["POST"])
async def syncdb_sync(document_name: str):
    """Sync endpoint - takes client state vector, returns updates needed."""
    try:
        # Get or create the sync database
        doc = SyncDatabase.get(document_name)

        for perm in doc.widget._read_perms:
            pages.require(perm)

        # Read the client's state vector from the request
        client_state_vector = await quart.request.get_data()
        assert isinstance(client_state_vector, bytes)

        # If client sends empty bytes, they want the full document
        if not client_state_vector:
            # Return full state as update
            update = doc.crdt.get_update()
        else:
            # Return updates since client's state vector
            update = doc.crdt.get_update(client_state_vector)

        # Return the update as binary response
        return quart.Response(update, mimetype="application/octet-stream")
    except Exception:
        logger.exception("Failed to sync document", document=document_name)
        return quart.Response("Sync failed", status=500)


# State vector sync endpoint
# Client sends their state vector, server returns updates needed
@quart_app.app.route(
    "/api/syncdb/<path:document_name>/state_vector", methods=["GET"]
)
async def syncdb_vector(document_name: str):
    try:
        # Get or create the sync database
        doc = SyncDatabase.get(document_name)

        for perm in doc.widget._read_perms:
            pages.require(perm)

        vector = doc.crdt.get_state()

        return quart.Response(vector, mimetype="application/octet-stream")
    except Exception:
        logger.exception("Failed to get state vector", document=document_name)
        return quart.Response("Sync failed", status=500)


# Admin page for listing all SyncDatabase documents
@quart_app.app.route("/syncdb", methods=["GET", "POST"])
@quart_app.wrap_sync_route_handler
def syncdb_admin_index(*path, **data):
    """Admin page listing all SyncDatabase documents."""
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    page_number = int(data.get("pageNumber", 0))
    search_filter = data.get("searchFilter", "").strip()

    # Collect all documents from the registry
    docs_list = []
    with lock:
        for name, ref in allSyncDbs.items():
            doc = ref()
            if doc is not None:
                docs_list.append((name, doc))

    # Filter by search term
    if search_filter:
        docs_list = [
            (name, doc)
            for name, doc in docs_list
            if search_filter.lower() in name.lower()
        ]

    # Sort by name
    docs_list_sorted = sorted(docs_list, key=lambda x: x[0])

    # Paginate results (250 per page)
    paginated_docs = docs_list_sorted[
        page_number * 250 : (page_number + 1) * 250
    ]

    # Build doc data for template
    docs_data = []
    for name, doc in paginated_docs:
        try:
            doc_size = len(doc.crdt.get_update())
            sv_size = len(doc.crdt.get_state())
        except Exception:
            doc_size = 0
            sv_size = 0

        read_perms = list(doc.widget._read_perms)
        write_perms = list(doc.widget._write_perms)

        docs_data.append(
            {
                "name": name,
                "version": doc.version,
                "doc_size": doc_size,
                "sv_size": sv_size,
                "read_perms": read_perms,
                "write_perms": write_perms,
            }
        )

    total_pages = max(1, int(len(docs_list_sorted) / 250) + 1)
    page_numbers = list(range(total_pages))

    return pages.render_jinja_template(
        "settings/syncdb_admin.j2.html",
        page_number=page_number,
        search_filter=search_filter,
        docs_data=docs_data,
        page_numbers=page_numbers,
        total_pages=total_pages,
    )
