# SPDX-License-Identifier: GPL-3.0-or-later
"""Integration tests for the proxy management framework.

These tests exercise the real ASGI stack: a small echo backend is served
by Hypercorn on both a TCP port and a Unix domain socket, and a
:class:`kaithem.api.proxies.Proxy` forwards requests to it through the
Kaithem server on ``127.0.0.1:8002``.
"""

from __future__ import annotations

import asyncio
import gc
import json
import os
import socket
import tempfile
import threading
import time
from typing import Any

import niquests
import pytest
from websockets.sync.client import connect as sync_ws_connect

from kaithem.src import auth

SERVER_HOST = "127.0.0.1:8002"
SERVER_BASE = f"http://{SERVER_HOST}"


class EchoBackend:
    """A minimal ASGI echo server used as a proxy target.

    HTTP responses report the headers, path, query, and body that were
    received.  Websocket text messages come back prefixed with ``echo:``.
    """

    async def _read_body(self, receive) -> bytes:
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] == "http.request":
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                break
        return b"".join(chunks)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

        if scope["type"] == "http":
            body = await self._read_body(receive)
            headers = {
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in scope["headers"]
            }
            payload = json.dumps(
                {
                    "headers": headers,
                    "method": scope["method"],
                    "path": scope["path"],
                    "query": scope.get("query_string", b"").decode("latin-1"),
                    "body": body.decode("latin-1"),
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"x-backend", b"echo"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": payload})
            return

        if scope["type"] == "websocket":
            await receive()  # websocket.connect
            await send({"type": "websocket.accept"})
            while True:
                message = await receive()
                if message["type"] == "websocket.receive":
                    text = message.get("text")
                    if text is not None:
                        await send(
                            {
                                "type": "websocket.send",
                                "text": "echo:" + text,
                            }
                        )
                    else:
                        await send(
                            {
                                "type": "websocket.send",
                                "bytes": message.get("bytes") or b"",
                            }
                        )
                elif message["type"] == "websocket.disconnect":
                    return


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def echo_backend():
    """Serve :class:`EchoBackend` on a TCP port and a Unix socket."""
    from hypercorn.asyncio import serve
    from hypercorn.config import Config

    port = _free_port()
    tmpdir = tempfile.mkdtemp(prefix="kaithem_proxy_test_")
    unix_path = os.path.join(tmpdir, "echo.sock")

    config = Config()
    config.bind = [f"127.0.0.1:{port}", f"unix:{unix_path}"]
    config.accesslog = None

    loop = asyncio.new_event_loop()
    stop_event = asyncio.Event()

    async def run() -> None:
        await serve(EchoBackend(), config, shutdown_trigger=stop_event.wait)

    def target() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run())

    thread = threading.Thread(target=target, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:  # pragma: no cover - backend failed to start
        raise RuntimeError("Echo backend did not start")

    yield {
        "port": port,
        "unix_path": unix_path,
        "http_target": f"http://127.0.0.1:{port}",
        "unix_target": f"unix://{unix_path}",
    }

    loop.call_soon_threadsafe(stop_event.set)
    thread.join(timeout=5)
    loop.close()


_counter = 0


def _unique_subdomain() -> str:
    global _counter
    _counter += 1
    return f"tstproxy{os.getpid()}{_counter}"


def _admin_token() -> str:
    auth.add_user("admin", "test-admin-password")
    auth.add_user_to_group("admin", "Administrators")
    auth.assignNewToken("admin", logout_old=False)
    return auth.Users["admin"].token


def _worker_token() -> str:
    auth.add_user("worker", "worker-password")
    auth.assignNewToken("worker", logout_old=False)
    return auth.Users["worker"].token


def _request(
    host: str,
    path: str,
    method: str = "GET",
    token: str | None = None,
    data: Any = None,
    headers: dict[str, str] | None = None,
) -> niquests.Response:
    """Send a real HTTP request to the Kaithem server with a custom Host."""
    request_headers = {"Host": host}
    if token is not None:
        request_headers["Cookie"] = f"kaithem_auth={token}"
    if headers:
        request_headers.update(headers)
    session = niquests.Session()
    try:
        return session.request(
            method,
            f"{SERVER_BASE}{path}",
            headers=request_headers,
            data=data,
            allow_redirects=False,
            timeout=15,
        )
    finally:
        session.close()


def _backend_json(response: niquests.Response) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    return json.loads(response.text)


# ---------------------------------------------------------------------------
# Registration / apps page
# ---------------------------------------------------------------------------


def test_proxy_registers_and_closes(echo_backend):
    from kaithem.api.proxies import Proxy
    from kaithem.api.web import _subdomain_apps
    from kaithem.src.apps_page import all_apps

    subdomain = _unique_subdomain()
    token = _admin_token()
    proxy = Proxy(
        subdomain=subdomain,
        target=echo_backend["http_target"],
        title="Echo Proxy",
    )

    assert _subdomain_apps.get(subdomain) is proxy
    assert all_apps.get("proxy_" + subdomain) is not None

    # The apps page links straight to the proxy subdomain on the parent
    # host the user is currently browsing.
    response = _request("localhost:8002", "/apps", token=token)
    assert response.status_code == 200
    assert f"//{subdomain}.localhost:8002/" in response.text

    proxy.close()

    assert _subdomain_apps.get(subdomain) is None
    assert all_apps.get("proxy_" + subdomain) is None

    response = _request("localhost:8002", "/apps", token=token)
    assert f"//{subdomain}.localhost:8002/" not in response.text

    # close() is idempotent.
    proxy.close()


def test_proxy_subdomain_is_unique(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    first = Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    try:
        with pytest.raises(ValueError):
            Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    finally:
        first.close()


def test_proxy_validates_arguments():
    from kaithem.api.proxies import Proxy

    with pytest.raises(ValueError):
        Proxy(subdomain="bad.subdomain", target="http://127.0.0.1:1")
    with pytest.raises(ValueError):
        Proxy(subdomain="UPPER", target="http://127.0.0.1:1")
    with pytest.raises(ValueError):
        Proxy(subdomain="ok", target="ftp://127.0.0.1:1")
    with pytest.raises(ValueError):
        Proxy(subdomain="ok", target="http://127.0.0.1:1/path")
    with pytest.raises(ValueError):
        Proxy(subdomain="ok", target="unix:relative.sock")


# ---------------------------------------------------------------------------
# Proxying and headers
# ---------------------------------------------------------------------------


def test_proxy_forwards_request_and_sets_user_headers(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    token = _admin_token()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    try:
        host = f"{subdomain}.localhost:8002"
        response = _request(
            host,
            "/some/path?q=1",
            method="POST",
            token=token,
            data=b"payload-body",
        )
        assert response.status_code == 200
        body = _backend_json(response)
        assert body["path"] == "/some/path"
        assert body["query"] == "q=1"
        assert body["method"] == "POST"
        assert body["body"] == "payload-body"
        assert body["headers"]["x-kaithem-username"] == "admin"
        assert body["headers"]["x-kaithem-is-admin"] == "true"
        assert (
            body["headers"]["host"]
            == echo_backend["http_target"].split("//")[1]
        )
    finally:
        proxy.close()


def test_proxy_strips_kaithem_auth_and_client_headers(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    token = _admin_token()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    try:
        host = f"{subdomain}.localhost:8002"
        response = _request(
            host,
            "/",
            token=token,
            headers={
                "x-kaithem-username": "bad",
                "x-kaithem-is-admin": "true",
                "x-kaithem-secret": "leak",  # pragma: allowlist secret
            },
        )
        body = _backend_json(response)
        headers = body["headers"]
        # The native auth token never reaches the backend.
        assert "kaithem_auth" not in headers.get("cookie", "")
        # Client supplied x-kaithem-* headers are dropped.
        assert "x-kaithem-secret" not in headers
        assert headers["x-kaithem-username"] == "admin"
        assert headers["x-kaithem-is-admin"] == "true"
    finally:
        proxy.close()


def test_proxy_keeps_other_cookies(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    token = _admin_token()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    try:
        host = f"{subdomain}.localhost:8002"
        response = _request(
            host,
            "/",
            headers={
                "Cookie": f"kaithem_auth={token}; app_session=keepme",
            },
        )
        headers = _backend_json(response)["headers"]
        assert "kaithem_auth" not in headers.get("cookie", "")
        assert "app_session=keepme" in headers.get("cookie", "")
    finally:
        proxy.close()


def test_proxy_is_admin_false_for_plain_user(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    token = _worker_token()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    try:
        host = f"{subdomain}.localhost:8002"
        response = _request(host, "/", token=token)
        headers = _backend_json(response)["headers"]
        assert headers["x-kaithem-username"] == "worker"
        assert headers["x-kaithem-is-admin"] == "false"
    finally:
        proxy.close()


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def test_proxy_requires_permission(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    admin = _admin_token()
    proxy = Proxy(
        subdomain=subdomain,
        target=echo_backend["http_target"],
        permissions=["system_admin"],
    )
    try:
        host = f"{subdomain}.localhost:8002"

        # Guest is redirected to the login page on the parent host.
        response = _request(host, "/")
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("//localhost:8002/login?go=")

        # A URL containing "login" gets a plain 403 instead of a loop.
        response = _request(host, "/login")
        assert response.status_code == 403

        # A user without the permission is also denied.
        worker = _worker_token()
        response = _request(host, "/", token=worker)
        assert response.status_code == 302

        # The admin reaches the backend.
        response = _request(host, "/", token=admin)
        assert response.status_code == 200
    finally:
        proxy.close()


def test_proxy_add_permission(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    worker = _worker_token()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    try:
        host = f"{subdomain}.localhost:8002"
        assert _request(host, "/", token=worker).status_code == 200

        proxy.add_permission("system_admin")
        assert _request(host, "/", token=worker).status_code == 302
    finally:
        proxy.close()


# ---------------------------------------------------------------------------
# Unix domain sockets
# ---------------------------------------------------------------------------


def test_proxy_unix_socket(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["unix_target"])
    try:
        host = f"{subdomain}.localhost:8002"
        response = _request(host, "/unix-path?x=2")
        body = _backend_json(response)
        assert body["path"] == "/unix-path"
        assert body["query"] == "x=2"
    finally:
        proxy.close()


# ---------------------------------------------------------------------------
# Target switching
# ---------------------------------------------------------------------------


def test_proxy_set_target_switches_backend(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    try:
        host = f"{subdomain}.localhost:8002"
        http_host = echo_backend["http_target"].split("//")[1]

        # Starts out talking to the TCP backend: the upstream Host header
        # is the TCP authority.
        body = _backend_json(_request(host, "/"))
        assert body["headers"]["host"] == http_host

        # Switch to the unix socket.  Reusing the same proxy and its
        # already-created session must still reach the unix backend.
        proxy.set_target(echo_backend["unix_target"])
        assert proxy.target == echo_backend["unix_target"]
        body = _backend_json(_request(host, "/"))
        assert body["headers"]["host"] == "localhost"

        # And switch back to TCP again.
        proxy.set_target(echo_backend["http_target"])
        assert proxy.target == echo_backend["http_target"]
        body = _backend_json(_request(host, "/"))
        assert body["headers"]["host"] == http_host
    finally:
        proxy.close()


def test_proxy_set_target_rejects_invalid(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    try:
        with pytest.raises(ValueError):
            proxy.set_target("ftp://127.0.0.1:1")
        # A rejected target leaves the working one in place.
        assert proxy.target == echo_backend["http_target"]
        host = f"{subdomain}.localhost:8002"
        http_host = echo_backend["http_target"].split("//")[1]
        body = _backend_json(_request(host, "/"))
        assert body["headers"]["host"] == http_host
    finally:
        proxy.close()


def test_proxy_set_target_websocket(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    token = _admin_token()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    try:
        proxy.set_target(echo_backend["unix_target"])
        uri = f"ws://{subdomain}.localhost:8002/ws"
        with sync_ws_connect(
            uri,
            sock=_ws_socket(),
            additional_headers={"Cookie": f"kaithem_auth={token}"},
            proxy=None,
        ) as ws:
            ws.send("switch")
            assert ws.recv() == "echo:switch"
    finally:
        proxy.close()


# ---------------------------------------------------------------------------
# Websockets
# ---------------------------------------------------------------------------


def _ws_socket() -> socket.socket:
    return socket.create_connection(("127.0.0.1", 8002))


def test_proxy_websocket(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    token = _admin_token()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["http_target"])
    try:
        uri = f"ws://{subdomain}.localhost:8002/ws"
        with sync_ws_connect(
            uri,
            sock=_ws_socket(),
            additional_headers={"Cookie": f"kaithem_auth={token}"},
            proxy=None,
        ) as ws:
            ws.send("hello")
            assert ws.recv() == "echo:hello"
            ws.send("again")
            assert ws.recv() == "echo:again"
    finally:
        proxy.close()


def test_proxy_websocket_denied(echo_backend):
    from websockets.exceptions import InvalidStatus

    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    proxy = Proxy(
        subdomain=subdomain,
        target=echo_backend["http_target"],
        permissions=["system_admin"],
    )
    try:
        uri = f"ws://{subdomain}.localhost:8002/ws"
        with pytest.raises(InvalidStatus):
            with sync_ws_connect(uri, sock=_ws_socket(), proxy=None):
                pass
    finally:
        proxy.close()


def test_proxy_unix_websocket(echo_backend):
    from kaithem.api.proxies import Proxy

    subdomain = _unique_subdomain()
    proxy = Proxy(subdomain=subdomain, target=echo_backend["unix_target"])
    try:
        uri = f"ws://{subdomain}.localhost:8002/ws"
        with sync_ws_connect(uri, sock=_ws_socket(), proxy=None) as ws:
            ws.send("over-unix")
            assert ws.recv() == "echo:over-unix"
    finally:
        proxy.close()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_gc_without_close_warns(monkeypatch, echo_backend):
    from kaithem.src.plugins.CorePluginProxies import proxy as proxy_module

    class FakeLogger:
        def __init__(self) -> None:
            self.warnings: list[str] = []

        def warning(self, *args: Any, **kwargs: Any) -> None:
            self.warnings.append(str(args))

        def exception(self, *args: Any, **kwargs: Any) -> None:
            pass

    fake = FakeLogger()
    monkeypatch.setattr(proxy_module, "logger", fake)

    subdomain = _unique_subdomain()
    leaked = proxy_module.Proxy(
        subdomain=subdomain, target=echo_backend["http_target"]
    )
    del leaked
    gc.collect()
    assert fake.warnings

    fake.warnings.clear()
    subdomain = _unique_subdomain()
    closed = proxy_module.Proxy(
        subdomain=subdomain, target=echo_backend["http_target"]
    )
    closed.close()
    del closed
    gc.collect()
    assert not fake.warnings


# ---------------------------------------------------------------------------
# Resource type
# ---------------------------------------------------------------------------


def test_proxy_resource_type_lifecycle(echo_backend):
    from kaithem.api import modules as modules_api
    from kaithem.api.web import _subdomain_apps
    from kaithem.src import modules, modules_state

    subdomain = _unique_subdomain()
    module = "testproxies" + str(time.time()).replace(".", "_")
    modules.newModule(module)

    resource_type = modules_state.resource_types["proxy"]
    data = resource_type.on_create_request(
        module,
        "p1",
        {
            "name": "p1",
            "data": json.dumps(
                {
                    "subdomain": subdomain,
                    "target": echo_backend["http_target"],
                    "title": "",
                    "permissions": [],
                }
            ),
        },
    )
    resource_type._validate(data)
    with modules_api.modules_lock:
        modules_state.raw_insert_resource(module, "p1", data)
    resource_type.on_load(module, "p1", data)

    assert _subdomain_apps.get(subdomain) is not None

    resource_type.on_delete(module, "p1", data)
    assert _subdomain_apps.get(subdomain) is None

    modules.rmModule(module)


def test_proxy_resource_type_rejects_invalid_data():
    from kaithem.src import modules_state

    resource_type = modules_state.resource_types["proxy"]
    with pytest.raises(Exception):
        resource_type.on_create_request(
            "somemodule",
            "p1",
            {
                "name": "p1",
                "data": json.dumps({"subdomain": "bad.name", "target": ""}),
            },
        )


# ---------------------------------------------------------------------------
# Path proxies
# ---------------------------------------------------------------------------


def _unique_prefix() -> str:
    global _counter
    _counter += 1
    return f"/apps/tstpath{os.getpid()}{_counter}"


def test_path_proxy_registers_and_closes(echo_backend):
    from kaithem.api.proxies import PathProxy
    from kaithem.api.web import _path_apps
    from kaithem.src.apps_page import all_apps

    prefix = _unique_prefix()
    token = _admin_token()
    proxy = PathProxy(
        prefix=prefix,
        target=echo_backend["http_target"],
        title="Path Echo",
    )

    assert _path_apps.get(prefix) is proxy
    assert all_apps.get("proxy_path_" + prefix.strip("/").replace("/", "_"))

    # Paths under the prefix reach the backend unchanged.
    body = _backend_json(_request("localhost:8002", prefix + "/deep/path"))
    assert body["path"] == prefix + "/deep/path"

    # The prefix itself is served too, and the apps page links to it.
    response = _request("localhost:8002", "/apps", token=token)
    assert response.status_code == 200
    assert f'"{prefix}/"' in response.text or prefix in response.text

    proxy.close()

    assert _path_apps.get(prefix) is None
    assert (
        all_apps.get("proxy_path_" + prefix.strip("/").replace("/", "_"))
        is None
    )

    # The mount is gone, so the path falls through to the ordinary router.
    response = _request("localhost:8002", prefix + "/deep/path")
    assert response.status_code == 404

    proxy.close()


def test_path_proxy_does_not_match_sibling_prefix(echo_backend):
    from kaithem.api.proxies import PathProxy
    from kaithem.src.apps_page import all_apps

    prefix = _unique_prefix()
    proxy = PathProxy(prefix=prefix, target=echo_backend["http_target"])
    try:
        # A longer name sharing the prefix text must not be captured.
        assert _request("localhost:8002", prefix + "x").status_code == 404
        assert _request("localhost:8002", prefix + "/ok").status_code == 200
    finally:
        proxy.close()
        assert (
            all_apps.get("proxy_path_" + prefix.strip("/").replace("/", "_"))
            is None
        )


def test_path_proxy_login_redirect_is_root_relative(echo_backend):
    from kaithem.api.proxies import PathProxy

    prefix = _unique_prefix()
    proxy = PathProxy(
        prefix=prefix,
        target=echo_backend["http_target"],
        permissions=["system_admin"],
    )
    try:
        response = _request("localhost:8002", prefix + "/secret")
        assert response.status_code == 302
        assert response.headers["location"].startswith("/login?go=")

        # A URL containing "login" gets a plain 403 instead of a loop.
        assert _request("localhost:8002", prefix + "/login").status_code == 403
    finally:
        proxy.close()


def test_path_proxy_websocket(echo_backend):
    from kaithem.api.proxies import PathProxy

    prefix = _unique_prefix()
    token = _admin_token()
    proxy = PathProxy(prefix=prefix, target=echo_backend["http_target"])
    try:
        uri = f"ws://localhost:8002{prefix}/ws"
        with sync_ws_connect(
            uri,
            sock=_ws_socket(),
            additional_headers={"Cookie": f"kaithem_auth={token}"},
            proxy=None,
        ) as ws:
            ws.send("path-hello")
            assert ws.recv() == "echo:path-hello"
    finally:
        proxy.close()


def test_path_proxy_duplicate_prefix_rejected(echo_backend):
    from kaithem.api.proxies import PathProxy

    prefix = _unique_prefix()
    first = PathProxy(prefix=prefix, target=echo_backend["http_target"])
    try:
        with pytest.raises(ValueError):
            PathProxy(prefix=prefix, target=echo_backend["http_target"])
    finally:
        first.close()


def test_path_proxy_validates_prefix(echo_backend):
    from kaithem.api.proxies import PathProxy

    target = echo_backend["http_target"]
    for bad in ("", "apps/x", "/", "relative"):
        with pytest.raises(ValueError):
            PathProxy(prefix=bad, target=target)
