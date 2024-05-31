import traceback

from quart import Quart
from werkzeug.exceptions import NotFound

from kaithem.src import pages

app = Quart(__name__)


@app.errorhandler(Exception)
def handle_exception(e):
    return pages.get_template("errors/e500.html").render(e=traceback.format_exc())


@app.errorhandler(NotFound)
def handle_404_exception(e):
    return pages.get_template("errors/e404.html").render()
