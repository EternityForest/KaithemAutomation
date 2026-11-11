# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Callable

from hypercorn.typing import Scope

from kaithem.api import web as webapi
from kaithem.src import pages


class SubdomainDispatcher:
    """Dispatch requests whose Host header names a registered subdomain
    to the ASGI application registered for that subdomain.

    Every other request is passed through unchanged to the wrapped
    application, so this can wrap the normal path based dispatcher.
    """

    def __init__(self, app) -> None:
        self.app = app

    @staticmethod
    def _get_host(scope: Scope) -> str:
        for key, value in scope.get("headers", []):
            if key == b"host":
                return value.decode("latin-1")
        return ""

    async def __call__(
        self, scope: Scope, receive: Callable, send: Callable
    ) -> None:
        if scope["type"] in ("http", "websocket"):
            host = self._get_host(scope)
            subdomain = ".".join(pages.parse_subdomain(host))
            if subdomain:
                sub_app = webapi._subdomain_apps.get(subdomain)
                if sub_app is not None:
                    await sub_app(scope, receive, send)
                    return
        await self.app(scope, receive, send)
