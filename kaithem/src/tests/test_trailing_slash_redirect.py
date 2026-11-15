# SPDX-License-Identifier: GPL-3.0-or-later
"""In-process ASGI tests for the trailing-slash redirects.

Both :class:`kaithem.src.plugins.CorePluginProxies.proxy.PathProxy` and
:class:`kaithem.src.plugins.CorePluginContainerApps.static_apps.StaticFilesApp`
have their own, separate implementation that 301s a request for the bare
mount prefix to the canonical URL with a trailing slash.  These tests drive
the ASGI apps directly, so no live server port is needed.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest

from kaithem.src.plugins.CorePluginContainerApps.static_apps import (
    StaticFilesApp,
)
from kaithem.src.plugins.CorePluginProxies.proxy import PathProxy

_counter = 0


def _unique_path() -> str:
    global _counter
    _counter += 1
    return f"/tsslash{os.getpid()}{_counter}"


def _http_scope(path: str, query: str = "") -> dict[str, Any]:
    return {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [(b"host", b"localhost:8002")],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8002),
    }


async def _drive(app: Any, scope: dict[str, Any]) -> list[dict[str, Any]]:
    """Run ``app`` for one request and return the ASGI messages it sent."""
    messages: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    await app(scope, receive, send)
    return messages


def _location(messages: list[dict[str, Any]]) -> str | None:
    for key, value in messages[0].get("headers", []):
        if key == b"location":
            return value.decode("latin-1")
    return None


@pytest.mark.asyncio
async def test_path_proxy_redirects_bare_prefix():
    path = _unique_path()
    proxy = PathProxy(prefix=path, target="http://127.0.0.1:1")
    try:
        messages = await _drive(proxy, _http_scope(path))
        assert messages[0]["type"] == "http.response.start"
        assert messages[0]["status"] == 301
        assert _location(messages) == path + "/"
    finally:
        proxy.close()


@pytest.mark.asyncio
async def test_path_proxy_redirect_preserves_query():
    path = _unique_path()
    proxy = PathProxy(prefix=path, target="http://127.0.0.1:1")
    try:
        messages = await _drive(proxy, _http_scope(path, "a=1&b=2"))
        assert messages[0]["status"] == 301
        assert _location(messages) == path + "/?a=1&b=2"
    finally:
        proxy.close()


@pytest.mark.asyncio
async def test_path_proxy_does_not_redirect_prefixed_path():
    path = _unique_path()
    proxy = PathProxy(prefix=path, target="http://127.0.0.1:1")
    try:
        # A path with the trailing slash must not be redirected; it is
        # forwarded to the (unreachable) backend and fails as a 502.
        messages = await _drive(proxy, _http_scope(path + "/"))
        assert messages[0]["status"] == 502
    finally:
        proxy.close()


@pytest.mark.asyncio
async def test_static_files_app_redirects_bare_prefix():
    path = _unique_path()
    source_dir = tempfile.mkdtemp(prefix="kaithem_static_redirect_")
    app = StaticFilesApp(prefix=path, source_dir=source_dir, title="Test")
    try:
        messages = await _drive(app, _http_scope(path))
        assert messages[0]["type"] == "http.response.start"
        assert messages[0]["status"] == 301
        assert _location(messages) == path + "/"
    finally:
        app.close()


@pytest.mark.asyncio
async def test_static_files_app_redirect_preserves_query():
    path = _unique_path()
    source_dir = tempfile.mkdtemp(prefix="kaithem_static_redirect_")
    app = StaticFilesApp(prefix=path, source_dir=source_dir, title="Test")
    try:
        messages = await _drive(app, _http_scope(path, "x=9"))
        assert messages[0]["status"] == 301
        assert _location(messages) == path + "/?x=9"
    finally:
        app.close()
