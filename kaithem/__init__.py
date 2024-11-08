from typing import Any, Dict, Optional

from .src import main

# Config keys exactly the same as config.yaml.  Note that not all take effect instantly.
config = main.config
api = None


def initialize_app(cfg: Optional[Dict[str, Any]] = None):
    """Initialize the app and return an API object
    identical to the kaithem namespace in web-created modules"""
    global api
    if not api:
        main.initialize(cfg)
    else:
        raise RuntimeError("The app has already been set up")
    from .src.kaithemobj import kaithem

    api = api
    return kaithem


# Call this to start a
def start_server():
    """Calling this function starts the web server."""
    main.start_server()
