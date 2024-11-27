import mimetypes
import os
import traceback

import quart
from quart import Quart, Response
from quart.ctx import copy_current_request_context
from werkzeug.exceptions import InternalServerError, NotFound

from kaithem.src import pages

app = Quart(__name__)


@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, pages.KaithemUserPermissionError):
        return pages.loginredirect(quart.request.url)
    if isinstance(e, InternalServerError):
        e = e.original_exception
    r = pages.get_template("errors/e500.html").render(
        e="".join(traceback.format_exception(None, e, e.__traceback__))
    )
    return Response(r, status=500)


@app.route("/errors/loginerror")
def handle_login_exception():
    r = pages.get_template("errors/loginerror.html").render()
    return Response(r, status=500)


@app.errorhandler(NotFound)
def handle_404_exception(e):
    r = pages.get_template("errors/e404.html").render()
    return Response(r, status=404)


def wrap_sync_route_handler(f):
    """
    Decorator that reads form data, passes it to function
    as keword args.
    and wraps the whole thing as async.
    """

    async def f2(*a, **k):
        kwargs = dict(await quart.request.form)
        kwargs.update(quart.request.args)

        @copy_current_request_context
        def f3():
            return f(*a, **k, **kwargs)

        return await f3()

    f2.__name__ = f.__name__ + "_wrapped"

    return f2


async def send_file_range(file_path: str):
    try:

        @quart.ctx.copy_current_request_context
        def f():
            range_header = quart.request.headers.get("Range", "").replace(
                "bytes=", ""
            )
            if "-" in range_header:
                r = range_header.split("-")
                start = int(r[0])
                fs = os.path.getsize(file_path)
                if len(r) > 1 and r[1]:
                    end = int(r[1])
                else:
                    end = fs - 1

                end = min(end, fs - 1)
            else:
                start = 0
                end = os.path.getsize(file_path) - 1

            with open(file_path, "rb") as file:
                file.seek(start)
                data = file.read(end - start + 1)

            response = quart.Response(
                data, mimetype=mimetypes.guess_type(file_path)[0]
            )
            response.headers["Content-Range"] = (
                f"bytes {start}-{end}/{os.path.getsize(file_path)}"
            )
            response.headers["Content-Length"] = str(end - start + 1)
            response.status_code = 206
            return response

        return await f()

    except FileNotFoundError:
        return "File not found", 404
