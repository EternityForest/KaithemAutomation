# SPDX-License-Identifier: GPL-3.0-or-later
"""Serve a directory of static files as a path mounted ASGI app.

Container apps whose ``[app]`` section is ``type = "staticfiles"`` build a
platform independent directory of files (HTML, CSS, JS, images) and expose
it under ``/apps/<name>`` on the Kaithem host.  Requests are handled here
rather than by a subprocess, so there is nothing to start or stop and the
files are served straight from disk behind the usual permission checks.
"""

from __future__ import annotations

import base64
import os
import time
from collections.abc import Callable
from posixpath import normpath
from typing import Any
from urllib.parse import unquote

import structlog
from starlette.responses import FileResponse

import kaithem.api.apps_page as apps_page
from kaithem.api import web
from kaithem.src import pages

logger = structlog.get_logger(__name__)


def _host(scope: dict[str, Any]) -> str:
    for key, value in scope.get("headers", []):
        if key == b"host":
            return value.decode("latin-1")
    return ""


def _request_url(scope: dict[str, Any]) -> str:
    """Rebuild the full URL a client requested, as seen by the app."""
    scheme = scope.get("scheme", "http")
    path = scope.get("path", "/")
    query = scope.get("query_string", b"").decode("latin-1")
    url = f"{scheme}://{_host(scope)}{path}"
    if query:
        url += "?" + query
    return url


def _login_redirect(url: str) -> str:
    """Build a ``/login`` redirect that returns the user to ``url``."""
    return (
        "/login?go="
        + base64.b64encode(url.encode()).decode()
        + "&maxgotime-"
        + str(time.time() + 300)
    )


async def _send_text(send, status: int, text: str) -> None:
    body = text.encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class StaticFilesApp:
    """Serve ``source_dir`` under ``prefix`` as an ASGI application.

    The app is registered with :func:`kaithem.api.web.add_path_app`, so
    requests arrive with their path untouched and the prefix is stripped
    here before resolving the file.
    """

    def __init__(
        self,
        prefix: str,
        source_dir: str,
        title: str,
        permissions: list[str] | None = None,
        module: str | None = None,
        resource: str | None = None,
        permissions_provider: Callable[[], list[str]] | None = None,
        fallback_to_index: bool = True,
    ) -> None:
        """Create and register a static file mount.

        Args:
            prefix: The absolute path to mount at, for example
                ``"/apps/myapp"``.
            source_dir: The directory holding the built files.
            title: Title shown on the apps page.
            permissions: Permissions a user must have to reach the
                files.  An empty list allows any user.
            module: Module name, used for the apps page icon.
            resource: Resource name, used for the apps page icon.
            permissions_provider: Optional callback returning additional
                permissions, evaluated on every request.
            fallback_to_index: When true, an unknown path serves
                ``index.html`` if present, which is what single page
                applications expect.
        """
        if not isinstance(prefix, str) or not prefix.startswith("/"):
            raise ValueError(f"Path prefix {prefix!r} must start with '/'")
        prefix = prefix.rstrip("/")
        if not prefix:
            raise ValueError("Path prefix must not be the root path")

        self.prefix = prefix
        self.source_dir = source_dir
        self.title = title
        self.permissions = list(permissions or [])
        self.permissions_provider = permissions_provider
        self.module = module
        self.resource = resource
        self.fallback_to_index = fallback_to_index

        self._closed = False
        self._app: apps_page.App | None = None
        self._register()

    def __del__(self) -> None:
        try:
            closed = self._closed
        except Exception:  # pragma: no cover - partially constructed object
            return
        if not closed:
            logger.warning(
                "Static file mount %r was garbage collected without being "
                "closed; call close() to release it",
                self.prefix,
            )

    # -- Registration -------------------------------------------------

    def _register(self) -> None:
        app = apps_page.App(
            id="container_static_" + self.prefix.strip("/").replace("/", "_"),
            title=self.title,
            url=self.prefix + "/",
            module=self.module,
            resource=self.resource,
        )
        web.add_path_app(self.prefix, self)
        try:
            apps_page.add_app(app)
        except Exception:
            web.remove_path_app(self.prefix, self)
            raise
        self._app = app

    def close(self) -> None:
        """Unmount the app.  Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        web.remove_path_app(self.prefix, self)
        if self._app is not None:
            apps_page.remove_app(self._app)
            self._app = None

    # -- Authorization ------------------------------------------------

    def _current_permissions(self) -> list[str]:
        permissions = list(self.permissions)
        if self.permissions_provider is not None:
            permissions.extend(self.permissions_provider() or [])
        return permissions

    def _is_authorized(self, user: str) -> bool:
        permissions = self._current_permissions()
        if not permissions:
            return True
        return pages.canUserDoThis(permissions, user)

    # -- Request handling ---------------------------------------------

    def _find_file(self, path: str) -> str | None:
        """Return the file to serve for ``path``, or None for a 404."""
        root = os.path.realpath(self.source_dir)
        relative = path[len(self.prefix) :].lstrip("/")
        # Collapse ``..`` and redundant separators before joining, then
        # re-check with realpath so symlinks cannot escape the root.
        relative = normpath("/" + unquote(relative)).lstrip("/")
        candidate = os.path.realpath(os.path.join(root, relative))
        if candidate != root and not candidate.startswith(root + os.sep):
            return None
        if os.path.isdir(candidate):
            candidate = os.path.join(candidate, "index.html")
        if os.path.isfile(candidate):
            return candidate
        if self.fallback_to_index:
            index = os.path.join(root, "index.html")
            if os.path.isfile(index):
                return index
        return None

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket":
            # Nothing to upgrade to; the frontend is served as files.
            await send({"type": "websocket.close"})
            return
        if scope["type"] != "http":  # pragma: no cover - dispatcher
            raise RuntimeError(
                f"Static file mount cannot handle scope {scope['type']!r}"
            )

        user = pages.getAcessingUser(asgi=scope)
        if not self._is_authorized(user):
            location = _login_redirect(_request_url(scope))
            await send(
                {
                    "type": "http.response.start",
                    "status": 302,
                    "headers": [(b"location", location.encode("latin-1"))],
                }
            )
            await send({"type": "http.response.body", "body": b""})
            return

        target = self._find_file(scope.get("path", "/"))
        if target is None:
            await _send_text(send, 404, "Not Found")
            return

        response = FileResponse(target)
        await response(scope, receive, send)
