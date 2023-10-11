import optparse
import logging
import os
from getpass import getpass
from logging.handlers import WatchedFileHandler
import webbrowser
import hashlib
import urllib.parse
import time
import threading

from flask import request, redirect, session, flash, url_for
from .sqlite_web import initialize_app
from .sqlite_web import die
from .sqlite_web import app
from .sqlite_web import LOG
from .sqlite_web import render_template

from . import sqlite_web


@app.route("/login/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == app.config["PASSWORD"]:
            session["authorized"] = True
            return redirect(session.get("next_url") or url_for("index"))
        flash("The password you entered is incorrect.", "danger")
        LOG.debug("Received incorrect password attempt from %s" % request.remote_addr)
    return render_template("login.html")


@app.route("/logout/", methods=["GET"])
def logout():
    session.pop("authorized", None)
    return redirect(url_for("login"))


def install_auth_handler(password):
    app.config["PASSWORD"] = password

    @app.before_request
    def check_password():
        if (
            not session.get("authorized")
            and request.path != "/login/"
            and not request.path.startswith(("/static/", "/favicon"))
        ):
            flash("You must log-in to view the database browser.", "danger")
            session["next_url"] = request.base_url
            return redirect(url_for("login"))


def open_browser_tab(name, host, port):
    url = "http://%s:%s/%s/" % (host, port, name)

    def _open_tab(url):
        time.sleep(1.5)
        webbrowser.open_new_tab(url)

    thread = threading.Thread(target=_open_tab, args=(url,))
    thread.daemon = True
    thread.start()


#
# Script options.
#


def get_option_parser():
    parser = optparse.OptionParser()
    parser.add_option(
        "-p",
        "--port",
        default=8089,
        help="Port for web interface, default=8080",
        type="int",
    )
    parser.add_option(
        "-H",
        "--host",
        default="127.0.0.1",
        help="Host for web interface, default=127.0.0.1",
    )
    parser.add_option(
        "-d", "--debug", action="store_true", help="Run server in debug mode"
    )
    parser.add_option(
        "-x",
        "--no-browser",
        action="store_false",
        default=True,
        dest="browser",
        help="Do not automatically open browser page.",
    )
    parser.add_option(
        "-l", "--log-file", dest="log_file", help="Filename for application logs."
    )
    parser.add_option(
        "-P",
        "--password",
        action="store_true",
        dest="prompt_password",
        help="Prompt for password to access database browser.",
    )
    parser.add_option(
        "-r",
        "--read-only",
        action="store_true",
        dest="read_only",
        help="Open database in read-only mode.",
    )
    parser.add_option(
        "-R",
        "--rows-per-page",
        default=50,
        dest="rows_per_page",
        help="Number of rows to display per page (default=50)",
        type="int",
    )
    parser.add_option(
        "-u", "--url-prefix", dest="url_prefix", help="URL prefix for application."
    )
    parser.add_option(
        "-e",
        "--extension",
        action="append",
        dest="extensions",
        help="Path or name of loadable extension.",
    )
    ssl_opts = optparse.OptionGroup(parser, "SSL options")
    ssl_opts.add_option(
        "-c", "--ssl-cert", dest="ssl_cert", help="SSL certificate file path."
    )
    ssl_opts.add_option(
        "-k", "--ssl-key", dest="ssl_key", help="SSL private key file path."
    )
    ssl_opts.add_option(
        "-a",
        "--ad-hoc",
        action="store_true",
        dest="ssl_ad_hoc",
        help="Use ad-hoc SSL context.",
    )
    parser.add_option_group(ssl_opts)
    return parser


def main():
    # This function exists to act as a console script entry-point.
    parser = get_option_parser()
    options, args = parser.parse_args()

    args = ["/home/daniel/Downloads/Chinook_Sqlite.sqlite"]
    if not args:
        die("Error: missing required path to database file.")

    if options.log_file:
        fmt = logging.Formatter("[%(asctime)s] - [%(levelname)s] - %(message)s")
        handler = WatchedFileHandler(options.log_file)
        handler.setLevel(logging.DEBUG if options.debug else logging.WARNING)
        handler.setFormatter(fmt)
        LOG.addHandler(handler)

    url_name = urllib.parse.quote_plus(args[0].replace("/", "-"))

    # This resolver runs in the Flask contexts and translates
    # A name into a file plus  flag indicating writable
    def resolve(name):
        if name == url_name:
            return args[0], (not options.read_only)
        raise RuntimeError("The database " + name + " isn't here.")

    sqlite_web.resolve_dataset = resolve

    password = None
    if options.prompt_password:
        if os.environ.get("SQLITE_WEB_PASSWORD"):
            password = os.environ["SQLITE_WEB_PASSWORD"]
        else:
            while True:
                password = getpass("Enter password: ")
                password_confirm = getpass("Confirm password: ")
                if password != password_confirm:
                    print("Passwords did not match!")
                else:
                    break

        install_auth_handler(password)

    if options.rows_per_page:
        app.config["ROWS_PER_PAGE"] = options.rows_per_page

    # Initialize the dataset instance and (optionally) authentication handler.
    initialize_app(options.url_prefix, options.extensions)

    if options.browser:
        open_browser_tab(url_name, options.host, options.port)

    if password:
        key = b"sqlite-web-" + args[0].encode("utf8") + password.encode("utf8")
        app.secret_key = hashlib.sha256(key).hexdigest()

    # Set up SSL context, if specified.
    kwargs = {}
    if options.ssl_ad_hoc:
        kwargs["ssl_context"] = "adhoc"

    if options.ssl_cert and options.ssl_key:
        if not os.path.exists(options.ssl_cert) or not os.path.exists(options.ssl_key):
            die("ssl cert or ssl key not found. Please check the file-paths.")
        kwargs["ssl_context"] = (options.ssl_cert, options.ssl_key)
    elif options.ssl_cert:
        die('ssl key "-k" is required alongside the ssl cert')
    elif options.ssl_key:
        die('ssl cert "-c" is required alongside the ssl key')

    # Run WSGI application.
    app.run(host=options.host, port=options.port, debug=options.debug, **kwargs)


if __name__ == "__main__":
    main()
