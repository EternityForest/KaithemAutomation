"""
This module deals with stable APIs that are acceptable for
User code.

"""


def docstring():
    """
    This is kaithem's public API, for use in plugins and user code,
    in pages and events.  Anything not in here is not part of a stable public
    API.

    Formerly the API included many utility features, but these are mostly now in
    separate libraries, or available through tag point APIs.

    See dev-build-docs in the Makefile for how to generate these.

    """
