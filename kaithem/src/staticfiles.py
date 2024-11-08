import os

import quart
from structlog import get_logger

from kaithem.src import quart_app

logger = get_logger(__name__)

sdn = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "src"
)
ddn = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "data"
)


@quart_app.app.route("/static/<path:path>")
async def static_misc(path):
    return await quart.send_file(os.path.join(ddn, "static", path))


@quart_app.app.route("/static/js/<path:path>")
async def static_js(path):
    return await quart.send_file(os.path.join(sdn, "js", path))


@quart_app.app.route("/static/css/<path:path>")
async def static_css(path):
    return await quart.send_file(os.path.join(sdn, "css", path))


@quart_app.app.route("/static/vue/<path:path>")
async def static_vue(path):
    return await quart.send_file(os.path.join(sdn, "vue", path))


@quart_app.app.route("/static/docs/<path:path>")
async def static_docs(path):
    return await quart.send_file(os.path.join(sdn, "docs", path))


## Catchall isn't working
@quart_app.app.route("/static/mdicons/<path:path>")
async def static_icons(path):
    return await quart.send_file(os.path.join(ddn, "static", "mdicons", path))


@quart_app.app.route("/static/fonts/<path:path>")
async def static_fonts(path):
    return await quart.send_file(os.path.join(ddn, "static", "fonts", path))


@quart_app.app.route("/static/sounds/<path:path>")
async def static_fbsounds(path):
    return await quart.send_file(os.path.join(ddn, "static", "sounds", path))


@quart_app.app.route("/static/img/<path:path>")
async def static_img(path):
    return await quart.send_file(os.path.join(ddn, "static", "img", path))
