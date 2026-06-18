# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import os
import struct
import threading
import uuid
import weakref
from typing import Any

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
tab, so things should very often "just work".  However, any time a browser
client disconnects, it releases the persistent ID, any actions taken until
reconnecting may permanently add a few bytes of data to the document.

These persistent IDs use /etc/machine-id as a salt, so this must be set up
correctly, which it will be, unless you're copying disk images.

There is currently no way to clean this up except by starting all over.

Documents on the server have a session ID that is currently random,
and if a web client tries to reconnect to a server, or if
the session id changes, the web client refreshes the page.

Python nodes are not clients of any particular server, and do not do this.
Therefore, if you have a bunch of python nodes and you want to wipe the document
and start over, you must reboot them all at the same time, or the one that still
has the data will re-spread it to everything else.


See https://yjs.dev for more information.
"""

logger = structlog.get_logger(__name__)

# Global registry - uses weak references like tagpoints
# Indexed by document session ID
allSyncDbs: dict[str, weakref.ref[SyncDatabase]] = {}


lock = threading.RLock()


idlock = threading.RLock()


if os.path.exists("/etc/machine-id"):
    with open("/etc/machine-id") as f:
        machine_id = f.read().strip()
else:
    machine_id = os.urandom(32).hex()


def make_id(domain: str, num: int) -> int:
    hashable = (
        struct.pack("Q", num)
        + machine_id.encode("utf-8")
        + domain.encode("utf-8")
    )
    st = hashlib.sha256(hashable).digest()[:8]
    id = struct.unpack("Q", st)[0] % 2**52
    return id


class SyncDatabaseWidget(widgets.DataSource):
    def __init__(self, id: str, session_id: str):
        super().__init__(id=id)
        self.session_id = session_id
        self.crdt_id_counter = 0
        self.crdt_used: dict[str, int] = {}
        self.crdt_pool: list[int] = []

    ## Clients MUST release these when disconneted

    def on_new_subscriber(self, user, connection_id, **kw):
        with idlock:
            # Make a new one if none are available
            if not self.crdt_pool:
                self.crdt_id_counter += 1
                self.crdt_pool.append(make_id(user, self.crdt_id_counter))

            crdt_id = self.crdt_pool.pop(0)
            self.crdt_used[connection_id] = crdt_id
            self.send_to(
                {"crdt_id": crdt_id, "session_id": self.session_id},
                connection_id,
            )

    def on_subscriber_disconnected(self, user, connection_id, **kw):
        with idlock:
            if connection_id in self.crdt_used:
                self.crdt_pool.append(self.crdt_used.pop(connection_id))


class SyncDatabase:
    """
    A SyncDatabase holds a YJS document and provides collaborative editing
    capabilities. It can be accessed through a global registry using weak refs.

    Like tag points, these are created on demand if you try to get() one
    that does not exist. Only one per name can ever exist. Nobody can ever
    delete them from the global registry, you just delete your reference
    and let GC handle it.
    """

    def __init__(self, name: str):
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

        self._crdt = pycrdt.Doc(
            client_id=make_id(name, 0), allow_multithreading=True
        )
        """The underlying YJS document"""

        self._widget: widgets.DataSource | None = None
        """The widget used for subscribing to updates"""

        self._lock = threading.RLock()

        self.accept_updates = False
        """Whether to accept any updates from websockets.
           If true, anything you put will likely be put back by
           a client reconnecting after reboots.
        """

        # Create the DataSource widget for this database
        self._widget = SyncDatabaseWidget(
            id=f"syncdb:{name}", session_id=self.document_session_id
        )

        self.widget.set_permissions(
            read=["system_admin"], write=["system_admin"]
        )

        # Subscribe to the widget - every message is an update to apply
        self.widget.attach2(self._on_widget_message)

        with lock:
            if name in allSyncDbs:
                raise ValueError(f"SyncDatabase {name} already exists")
            allSyncDbs[name] = weakref.ref(self)

        self._crdt.observe(self._on_doc_update)

    @property
    def crdt(self) -> pycrdt.Doc:
        """The underlying YJS document. To use this class,
        Interact directly with the CRDT.
        """
        return self._crdt

    def _on_doc_update(self, evt: pycrdt.TransactionEvent):
        self.broadcast_update(evt.update)

    def _on_widget_message(self, acting_user: str, value: Any, conn_id: str):
        """Handle incoming messages from the widget subscription."""
        if value is None:
            return

        if not isinstance(value, bytes):
            return

        if not self.accept_updates:
            return

        # Value should be a YJS update that can be applied to the doc
        try:
            self.crdt.apply_update(value)
        except Exception:
            logger.exception("Failed to apply YJS update", database=self.name)

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

        # Send the raw bytes - subscribers will apply this update
        self.widget.send(update)

    def __repr__(self) -> str:
        return f"<SyncDatabase: {self.name}>"

    @classmethod
    def get(cls, name: str) -> SyncDatabase:
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
                    return existing

            # Create new one
            return cls(name)

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

        database.crdt.observe(self._on_doc_update)

        # Start the client
        self._start()

    def _start(self) -> None:
        """Start the websocket client."""
        self._running = True

        # Create the client and subscribe
        self._client = widget_api.WidgetApiClient(
            self._server, self._username, self._password
        )

        # Subscribe to the channel to receive updates
        self._client.subscribe(self._channel, self._on_message)

    def _on_message(self, value: Any) -> None:
        """Handle incoming YJS updates."""
        if value is None:
            return

        db = self._db_ref()
        if db is None:
            # Database was deleted, stop
            self.close()
            return

        # Value should be a YJS update that can be applied to the doc
        try:
            db.crdt.apply_update(value)
        except Exception:
            logger.exception("Failed to apply YJS update", database=db.name)

    def _on_doc_update(self, evt: pycrdt.TransactionEvent):
        self.send_update(evt.update)

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

        # Send via the widget API - this goes through the widget
        # which will broadcast to all subscribers including this client
        self._client.send(self._channel, update)

    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return (
            self._client is not None
            and self._running
            and self._client.connected
        )

    def close(self) -> None:
        """Close the WebSocket connection. Can be called from any thread."""
        self._running = False

        if self._client:
            try:
                self._client.close()
            except Exception:
                logger.exception("Failed to close client")
            self._client = None

        try:
            db = self._db_ref()
            if db:
                db.crdt.unobserve(self._on_doc_update)
        except Exception:
            logger.exception("Failed to unobserve document", database=db.name)

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
