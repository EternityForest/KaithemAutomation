# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
import threading
import time
import urllib.parse
import webbrowser

from flask import redirect, url_for
from sqlite_web import app, initialize_app, sqlite_web

from kaithem.src.api import web as webapi


def install_auth_handler():
    "Does nothin because auths handled by kaithem at the routing level"

    @app.before_request
    def check_password():
        return
        return redirect(url_for("login"))


def open_browser_tab(name, host, port):
    url = f"http://{host}:{port}/{name}/"

    def _open_tab(url):
        time.sleep(1.5)
        webbrowser.open_new_tab(url)

    thread = threading.Thread(target=_open_tab, args=(url,))
    thread.daemon = True
    thread.start()


def get_app():
    # This resolver runs in the Flask contexts and translates
    # A name into a file plus  flag indicating writable
    def resolve(name):
        return urllib.parse.unquote_plus(name), True

    sqlite_web.resolve_dataset = resolve

    install_auth_handler()

    app.config["ROWS_PER_PAGE"] = 50

    # Initialize the dataset instance and (optionally) authentication handler.
    initialize_app("database")

    return app


webapi.add_wsgi_app("/database.*", get_app(), "system_admin")
