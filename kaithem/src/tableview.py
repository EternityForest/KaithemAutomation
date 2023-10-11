
import webbrowser
import urllib.parse
import time
import threading

from flask import request, redirect, session, flash, url_for
from sqlite_web import initialize_app
from sqlite_web import die
from sqlite_web import app
from sqlite_web import LOG
from sqlite_web import render_template

from sqlite_web import sqlite_web

def install_auth_handler():

    @app.before_request
    def check_password():
        return
        return redirect(url_for("login"))


def open_browser_tab(name, host, port):
    url = "http://%s:%s/%s/" % (host, port, name)

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
