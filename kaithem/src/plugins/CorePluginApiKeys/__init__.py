# SPDX-License-Identifier: GPL-3.0-or-later
"""Core plugin that authenticates requests carrying an ephemeral API key.

A request with a valid ``x-kaithem-api-key`` header (see
:mod:`kaithem.api.api_keys`) is treated as the user that key belongs to.
This lets container apps and other internal services call Kaithem without
a cookie or password.
"""

from __future__ import annotations

from typing import override

from kaithem.api import api_keys
from kaithem.src.auth import (
    BaseAuthenticationPlugin,
    User,
    Users,
    add_auth_plugin,
)


def _synthesize_admin() -> User:
    """Return an in-memory ``__admin__`` user.

    ``__admin__`` is a virtual user that is never stored in the user
    database, so it is not in :data:`Users`.  Building it on the fly keeps
    the API key path working without writing anything to disk.
    """
    user = User({"username": "__admin__", "groups": []})
    user.permissions = {"__all_permissions__"}
    user.limits = {}
    return user


class ApiKeyAuthenticationPlugin(BaseAuthenticationPlugin):
    """Resolve a user from the ``x-kaithem-api-key`` header."""

    @override
    def request_to_user(self, headers: dict[str, str]) -> User | None:
        username = api_keys.username_from_headers(headers)
        if username is None:
            return None
        if username == "__admin__":
            return _synthesize_admin()
        return Users.get(username)


add_auth_plugin(ApiKeyAuthenticationPlugin())
