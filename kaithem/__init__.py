from typing import Any, Dict, Optional

from .src import main

# Config keys exactly the same as config.yaml.  Note that not all take effect instantly.
config = main.config
started = False


def initialize_app(cfg: Optional[Dict[str, Any]] = None):
    """Initialize the app"""
    global started
    if not started:
        main.initialize(cfg)
    else:
        raise RuntimeError("The app has already been set up")

    started = True


# Call this to start a
def start_server():
    """Calling this function starts the web server."""
    main.start_server()
