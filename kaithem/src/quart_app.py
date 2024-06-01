import traceback

from quart import Quart, Response
from werkzeug.exceptions import InternalServerError, NotFound

from kaithem.src import pages

app = Quart(__name__)


@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, InternalServerError):
        e = e.original_exception
    r = pages.get_template("errors/e500.html").render(e="".join(traceback.format_exception(None, e, e.__traceback__)))
    return Response(r, status=500)


@app.errorhandler(NotFound)
def handle_404_exception(e):
    r = pages.get_template("errors/e404.html").render()
    return Response(r, status=404)
