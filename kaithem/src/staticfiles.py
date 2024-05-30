import os
import time

from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send
from structlog import get_logger

from kaithem.api import web

logger = get_logger(__name__)

sdn = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src")
ddn = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "data")


class TrivialCache:
    def __init__(self, app):
        self.app = app
        self.cache = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            p = scope["path"]

            old = self.cache.get(p, (None, 0))
            if old[1] > time.time() - 3600:
                for i in old[0]:
                    await send(i)
                return

            c = []

            async def send_wrapper(message):
                c.append(message)
                await send(message)

            await self.app(scope, receive, send_wrapper)
            self.cache[p] = (c, time.time())
            try:
                if len(self.cache) > 48:
                    self.cache.pop(next(iter(self.cache)))
            except Exception:
                logger.exception("Error in TrivialCache")
        else:
            await self.app(scope, receive, send)


class RemovePrefixMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if "path" in scope:
            scope["path"] = scope["path"].replace("/static/", "")
        await self.app(scope, receive, send)


def makeserver(dn):
    return TrivialCache(GZipMiddleware(RemovePrefixMiddleware(StaticFiles(directory=dn))))


src = makeserver(sdn)


def add_apps():
    web.add_asgi_app("/static/js/.*", src, "__guest__")
    web.add_asgi_app("/static/css/.*", src, "__guest__")
    web.add_asgi_app("/static/docs/.*", src, "__guest__")
    web.add_asgi_app("/static/vue/.*", src, "__guest__")
    web.add_asgi_app("/static/.*", TrivialCache(GZipMiddleware(StaticFiles(directory=ddn))), "__guest__")
