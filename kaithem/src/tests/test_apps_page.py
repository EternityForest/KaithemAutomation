import gc

import pytest


def test_apps_page():
    """A lot of this stuff is implicitly tested in the UI test stuff,
    so we just need the duplicate detection logic
    """
    from kaithem.api.apps_page import App, add_app, remove_app

    a = App("test123", "test123", "test123")
    add_app(a)

    # ID already exists
    with pytest.raises(ValueError):
        a2 = App("test123", "test123", "test123")

    # already added
    with pytest.raises(ValueError):
        add_app(a)

    remove_app(a)
    # Idempotent removal
    remove_app(a)
    del a

    gc.collect()
    gc.collect()

    a2 = App("test123", "test123", "test123")
    add_app(a2)
