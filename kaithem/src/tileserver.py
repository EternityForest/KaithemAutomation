# This code runs once when the event loads. It also runs when you save the event during the test compile
# and may run multiple times when kaithem boots due to dependancy resolution
__doc__ = ""

import tornado
import os
import random
from tornado import httpclient
from . import pages, directories


http_client = httpclient.AsyncHTTPClient()


def get_fn(x, y, z):
    return os.path.join(directories.vardir, "maptiles", "opentopomap", z, x, y + ".png")


async def get_tile(x, y, z, r):
    if pages.canUserDoThis("/admin/settings.edit", pages.getAcessingUser(r)):
        if os.path.isfile(get_fn(x, y, z)):
            return

        os.makedirs(os.path.dirname(get_fn(x, y, z)), exist_ok=True)

        if random.random() > 0.5:
            r = http_client.fetch(f"https://b.tile.opentopomap.org/{z}/{x}/{y}.png")
        else:
            r = http_client.fetch(f"https://a.tile.opentopomap.org/{z}/{x}/{y}.png")

        r = await r
        with open(get_fn(x, y, z), "wb") as f:
            f.write(r.body)


class MainHandler(tornado.web.RequestHandler):
    def serve(self, path):
        file_location = path
        if not os.path.isfile(file_location):
            raise tornado.web.HTTPError(status_code=404)
        self.add_header("Content-Type", "image/png")
        with open(file_location, "rb") as source_file:
            self.write(source_file.read())
        self.finish()

    async def get(self):
        components = [x for x in self.request.path.replace(".png", "").split("/") if x]

        z, x, y = components[-3], components[-2], components[-1]
        if pages.canUserDoThis(
            "/users/maptiles.view", pages.getAcessingUser(self.request)
        ):
            if os.path.exists(get_fn(x, y, z)):
                return self.serve(get_fn(x, y, z))

            if os.path.exists(
                os.path.join(
                    os.path.expanduser("~/.local/share/marble/maps/earth/opentopomap"),
                    z,
                    x,
                    y,
                )
            ):
                return self.serve(
                    os.path.join(
                        os.path.expanduser(
                            "~/.local/share/marble/maps/earth/opentopomap"
                        ),
                        z,
                        x,
                        y,
                    )
                )

            if os.path.exists(
                os.path.join(
                    "/home/pi/.local/share/marble/maps/earth/opentopomap", z, x, y
                )
            ):
                return self.serve(
                    os.path.exists(
                        os.path.join(
                            "/home/pi/share/marble/maps/earth/opentopomap", z, x, y
                        )
                    )
                )

            await get_tile(x, y, z, self.request)

            if os.path.exists(get_fn(x, y, z)):
                return self.serve(get_fn(x, y, z))
        raise RuntimeError("No Tile Found")
