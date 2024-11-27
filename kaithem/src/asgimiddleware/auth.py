from typing import Callable

from hypercorn.typing import ASGIFramework, Scope

from kaithem.src import pages


class SimpleUserAuthMiddleware:
    def __init__(self, app: ASGIFramework, permissions: str) -> None:
        self.app = app
        self.permissions = permissions

    async def __call__(
        self, scope: Scope, receive: Callable, send: Callable
    ) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
        else:
            u = pages.getAcessingUser(asgi=scope)
            if not pages.canUserDoThis(self.permissions, u):
                raise RuntimeError("Todo this is a permissino err")
        await self.app(scope, receive, send)
