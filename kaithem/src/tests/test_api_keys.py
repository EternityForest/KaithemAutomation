# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for ephemeral API keys and the ``x-kaithem-api-key`` auth hook."""

from __future__ import annotations

import gc
from typing import Any

from kaithem.api import api_keys
from kaithem.src import auth, pages


def _add_user(username: str) -> None:
    auth.add_user(username, "test-password")
    auth.assignNewToken(username, logout_old=False)


def _scope(headers: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"localhost:8002"),
            *[(k.lower().encode(), v.encode()) for k, v in headers.items()],
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8002),
    }


def test_add_and_resolve():
    username = "apikeyuser"
    _add_user(username)
    key = api_keys.add_ephemeral_api_key(username)
    try:
        assert isinstance(key.key, str)
        assert key.key
        assert api_keys.resolve_api_key(key.key) == username
        assert (
            api_keys.username_from_headers({"x-kaithem-api-key": key.key})
            == username
        )
        # Header name matching is case insensitive.
        assert (
            api_keys.username_from_headers({"X-Kaithem-Api-Key": key.key})
            == username
        )
    finally:
        key.remove()


def test_remove_invalidates():
    username = "apikeyuser2"
    _add_user(username)
    key = api_keys.add_ephemeral_api_key(username)
    key.remove()
    assert api_keys.resolve_api_key(key.key) is None
    # remove() is idempotent.
    key.remove()
    assert (
        api_keys.username_from_headers({"x-kaithem-api-key": key.key}) is None
    )


def test_gc_invalidates():
    username = "apikeyuser3"
    _add_user(username)
    key = api_keys.add_ephemeral_api_key(username)
    raw = key.key
    assert api_keys.resolve_api_key(raw) == username
    del key
    gc.collect()
    assert api_keys.resolve_api_key(raw) is None


def test_unknown_key_is_guest():
    for bad in ("", "not-a-real-key"):
        scope = _scope({"x-kaithem-api-key": bad})
        assert pages.getAcessingUser(asgi=scope) == "__guest__"


def test_no_key_is_guest():
    scope = _scope({})
    assert pages.getAcessingUser(asgi=scope) == "__guest__"


def test_header_authenticates_request():
    username = "apikeyheaderuser"
    _add_user(username)
    key = api_keys.add_ephemeral_api_key(username)
    try:
        scope = _scope({"x-kaithem-api-key": key.key})
        assert pages.getAcessingUser(asgi=scope) == username
    finally:
        key.remove()

    # After removal the same header no longer authenticates.
    scope = _scope({"x-kaithem-api-key": key.key})
    assert pages.getAcessingUser(asgi=scope) == "__guest__"


def test_header_auth_drives_permission_checks():
    username = "apikeypermission"
    _add_user(username)
    group = "ApiKeyTestGroup"
    auth.addGroup(group)
    auth.addGroupPermission(group, "view_status")
    auth.add_user_to_group(username, group)

    key = api_keys.add_ephemeral_api_key(username)
    try:
        scope = _scope({"x-kaithem-api-key": key.key})
        assert pages.canUserDoThis("view_status", asgi=scope)
        assert not pages.canUserDoThis("system_admin", asgi=scope)
    finally:
        key.remove()
