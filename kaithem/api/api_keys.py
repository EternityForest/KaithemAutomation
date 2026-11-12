# SPDX-License-Identifier: GPL-3.0-or-later
"""Public API for ephemeral, in-memory API keys.

An ephemeral API key is a random secret that authenticates a caller as a
user for as long as the key's :class:`EphemeralApiKey` object stays alive.
Unlike a login token it is never written to disk, so it disappears when the
process restarts or the object is dropped.

They are meant for container apps and other internal services that must
talk to Kaithem without holding a real user's token::

    from kaithem.api import api_keys

    credentials = api_keys.add_ephemeral_api_key("myapp")
    # Callers present credentials.key in the x-kaithem-api-key header.
    ...
    credentials.remove()

Recognizing that header is the job of the ``CorePluginApiKeys`` auth hook;
this module only owns the key registry and the stable public functions.
"""

from __future__ import annotations

import base64
import os
import weakref
from collections.abc import Mapping

import structlog

from kaithem.api import lifespan

logger = structlog.get_logger(__name__)

#: Request header used to present an ephemeral API key.  Stored lowercase
#: because HTTP/2 and many server stacks lowercase header names.
API_KEY_HEADER = "x-kaithem-api-key"

# Weak values so a key stops working as soon as its ``EphemeralApiKey``
# object is garbage collected, which is also what lets ``__del__`` warn
# about keys that were dropped without ``remove()``.
#
# The annotation is a forward reference resolved lazily, so referencing the
# class defined below is fine.
_keys: weakref.WeakValueDictionary[str, EphemeralApiKey] = (
    weakref.WeakValueDictionary()
)


class EphemeralApiKey:
    """A random, in-memory API key that authenticates as a user.

    The key stays valid until :meth:`remove` is called or the object is
    garbage collected.  Keep a reference to the object for as long as the
    key should work.
    """

    def __init__(self, username: str):
        if not username:
            raise ValueError("username must be a non-empty string")
        self.username: str = username
        self.key: str = base64.b64encode(os.urandom(24)).decode()
        self._removed = False
        _keys[self.key] = self

    def __del__(self) -> None:
        try:
            removed = self._removed
            username = self.username
        except Exception:  # pragma: no cover - partially constructed object
            return
        if removed:
            return
        if lifespan.is_shutting_down:
            return
        logger.warning(
            "Ephemeral API key for %r was garbage collected without being "
            "removed; call remove() to release it",
            username,
        )

    def remove(self) -> None:
        """Invalidate the key.  Safe to call more than once."""
        if self._removed:
            return
        self._removed = True
        _keys.pop(self.key, None)


def add_ephemeral_api_key(username: str) -> EphemeralApiKey:
    """Create a new random ephemeral API key authenticating as ``username``.

    Callers must keep a reference to the returned object for as long as the
    key should remain valid, and call :meth:`EphemeralApiKey.remove` when
    they are done with it.
    """
    return EphemeralApiKey(username)


def resolve_api_key(key: str) -> str | None:
    """Return the username that ``key`` authenticates as, or ``None``.

    Low level helper used by the authentication hook; most callers should
    not need it.
    """
    if not key:
        return None
    entry = _keys.get(key)
    if entry is None:
        return None
    return entry.username


def username_from_headers(headers: Mapping[str, str]) -> str | None:
    """Return the username authenticated by an ephemeral key in ``headers``.

    Header name matching is case insensitive.  Returns ``None`` if there is
    no key, or if the key is unknown or has expired.
    """
    for name, value in headers.items():
        if name.lower() == API_KEY_HEADER:
            return resolve_api_key(value)
    return None
