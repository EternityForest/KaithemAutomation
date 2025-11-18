from typing import Any

from .src import main

started = False


def initialize_app(cfg: dict[str, Any] | None = None):
    """Initialize the app"""
    global started
    if not started:
        main.initialize(cfg)

    else:
        # pragma: no cover
        raise RuntimeError("The app has already been set up")

    started = True


# Call this to start a
def start_server():
    """Calling this function starts the web server."""
    main.start_server()
