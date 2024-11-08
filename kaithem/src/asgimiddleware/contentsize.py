# MIT License specified in pyproject.toml
# By Steinn Eldjárn Sigurðarson <steinnes@gmail.com>
# Modified by Daniel Dunn

import structlog

from kaithem.src import auth, pages


class ContentSizeLimitMiddleware:
    """Content size limiting middleware for ASGI applications.
    Limit acording to Kaithem's web.maxbytes setting per user.

    Args:
      app (ASGI application): ASGI application
    """

    def __init__(
        self,
        app,
    ):
        self.app = app
        self.max_content_size = 128 * 1024
        self.exception_cls = PermissionError

        self.logger = structlog.get_logger(__name__)

    def receive_wrapper(self, receive, scope):
        received = 0
        verified_limit = self.max_content_size

        async def inner():
            nonlocal received, verified_limit
            message = await receive()
            if (
                message["type"] != "http.request"
                or self.max_content_size is None
            ):
                return message
            body_len = len(message.get("body", b""))
            received += body_len
            if received > verified_limit:
                user = pages.getAcessingUser(scope)
                verified_limit = max(
                    auth.getUserLimit(user, "web.maxbytes"), 128 * 1024
                )
                if received > verified_limit:
                    raise self.exception_cls(
                        f"Maximum content size limit ({self.max_content_size}) exceeded ({received} bytes read)"
                    )
            return message

        return inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        wrapper = self.receive_wrapper(receive, scope)
        await self.app(scope, wrapper, send)
