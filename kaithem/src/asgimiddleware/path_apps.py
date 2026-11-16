# SPDX-License-Identifier: GPL-3.0-or-later
"""Dispatch requests to dynamically mounted path based applications.

Resources mount ASGI applications at a path prefix (for example
``/apps/myapp``) while Kaithem is running, so unlike the fixed prefix
dispatch table built at startup these mounts have to be looked up per
request.  Everything that is not claimed by a mounted application is
passed straight through to the wrapped application.
"""

from __future__ import annotations

from collections.abc import Callable

from hypercorn.typing import Scope

from kaithem.api import web as webapi


class PathDispatcher:
    """Route requests to the ASGI application mounted for their path.

    Any request whose path is not covered by a dynamic mount is sent to
    the wrapped application unchanged, so this can wrap the normal path
    based dispatcher.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Callable, send: Callable
    ) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            mounted = webapi.lookup_path_app(path)
            if mounted is not None:
                await mounted(scope, receive, send)
                return
        await self.app(scope, receive, send)
