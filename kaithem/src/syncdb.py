# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import threading
import weakref
from typing import Any

import pycrdt
import quart
import structlog

from . import quart_app, widgets

logger = structlog.get_logger(__name__)

# Global registry - uses weak references like tagpoints
allSyncDbs: dict[str, weakref.ref[SyncDatabase]] = {}
exposedSyncDbs: weakref.WeakValueDictionary[str, SyncDatabase] = (
    weakref.WeakValueDictionary()
)
lock = threading.RLock()


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

        # Normalize name - use similar rules to tagpoints
        self.name = name
        """The name of the sync database"""

        self.yjs_doc = pycrdt.Doc()
        """The underlying YJS document"""

        self._widget: widgets.DataSource | None = None
        """The widget used for subscribing to updates"""

        self._lock = threading.RLock()

        # Create the DataSource widget for this database
        self._widget = widgets.DataSource(id=f"syncdb:{name}")

        # Subscribe to the widget - every message is an update to apply
        self._widget.attach2(self._on_widget_message)

        with lock:
            if name in allSyncDbs:
                raise ValueError(f"SyncDatabase {name} already exists")
            allSyncDbs[name] = weakref.ref(self)

        logger.info("SyncDatabase created", name=name)

    def _on_widget_message(self, acting_user: str, value: Any, conn_id: str):
        """Handle incoming messages from the widget subscription."""
        if value is None:
            return

        # Value should be a YJS update that can be applied to the doc
        try:
            self.yjs_doc.apply_update(value)
        except Exception:
            logger.exception("Failed to apply YJS update", database=self.name)

    @property
    def widget(self) -> widgets.DataSource | None:
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
        if not self._widget:
            return

        if isinstance(read, str):
            read = [i.strip() for i in read.split(",") if i.strip()]
        if isinstance(write, str):
            write = [i.strip() for i in write.split(",") if i.strip()]

        self._widget.set_permissions(read, write)

    def broadcast_update(self, update: bytes) -> None:
        """
        Broadcast a YJS update to all subscribers.

        Args:
            update: The YJS update bytes to broadcast
        """
        if not self._widget:
            return

        # Send the raw bytes - subscribers will apply this update
        self._widget.send(update)

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


# State vector sync endpoint
# Client sends their state vector, server returns updates needed
@quart_app.app.route("/api/syncdb/<path:document_name>/sync", methods=["POST"])
async def syncdb_sync(document_name: str):
    """Sync endpoint - takes client state vector, returns updates needed."""
    try:
        # Get or create the sync database
        doc = SyncDatabase.get(document_name).yjs_doc

        # Read the client's state vector from the request
        client_state_vector = await quart.request.get_data()
        assert isinstance(client_state_vector, bytes)

        # If client sends empty bytes, they want the full document
        if not client_state_vector:
            # Return full state as update
            update = doc.get_update()
        else:
            # Return updates since client's state vector
            update = doc.get_update(client_state_vector)

        # Return the update as binary response
        return quart.Response(update, mimetype="application/octet-stream")
    except Exception:
        logger.exception("Failed to sync document", document=document_name)
        return quart.Response("Sync failed", status=500)
