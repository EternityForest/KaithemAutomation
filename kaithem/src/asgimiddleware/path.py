# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Callable

from hypercorn.typing import Scope

from kaithem.api import web as webapi


class PathDispatcher:
    """Dispatch requests whose URL path matches a registered mount path to
    the ASGI application registered for that path.

    A mount path matches when the request path is exactly the path, or
    starts with the path followed by ``/``.  The longest matching path
    wins, so nested mounts behave predictably.

    Every other request is passed through unchanged to the wrapped
    application, so this can wrap the normal dispatcher.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Callable, send: Callable
    ) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope["path"]
            best = None
            for mount in webapi._path_apps:
                if path == mount or path.startswith(mount + "/"):
                    if best is None or len(mount) > len(best):
                        best = mount
            if best is not None:
                await webapi._path_apps[best](scope, receive, send)
                return
        await self.app(scope, receive, send)
