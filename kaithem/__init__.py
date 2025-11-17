from typing import Any, Dict, Optional

from .src import console_about_page, main

started = False


def initialize_app(cfg: dict[str, Any] | None = None):
    """Initialize the app"""
    global started
    if not started:
        console_about_page.do_splash_screen()
        main.initialize(cfg)
    else:
        # pragma: no cover
        raise RuntimeError("The app has already been set up")

    started = True


# Call this to start a
def start_server():
    """Calling this function starts the web server."""
    main.start_server()
