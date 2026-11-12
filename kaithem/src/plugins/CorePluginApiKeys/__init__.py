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


class ApiKeyAuthenticationPlugin(BaseAuthenticationPlugin):
    """Resolve a user from the ``x-kaithem-api-key`` header."""

    @override
    def request_to_user(self, headers: dict[str, str]) -> User | None:
        username = api_keys.username_from_headers(headers)
        if username is None:
            return None
        return Users.get(username)


add_auth_plugin(ApiKeyAuthenticationPlugin())
