from __future__ import annotations

import base64
import getpass
import os
import pwd
from typing import Any, override

from kaithem.src.auth import (
    BaseAuthenticationPlugin,
    User,
    add_auth_plugin,
    logger,
    set_user_if_not_exists,
)
from kaithem.src.host_services_client.client import (
    check_password as check_password_on_host,
)
from kaithem.src.host_services_client.socket_path import default_socket_path

host_service_socket_path = default_socket_path()


class LinuxSystemUserAuthenticationPlugin(BaseAuthenticationPlugin):
    def __init__(self):
        self.token = base64.b64encode(os.urandom(24)).decode()
        self.user = getpass.getuser()

    @override
    def logout(self, token: str):
        if token == self.token:
            self.token = base64.b64encode(os.urandom(24)).decode()

    @override
    def token_to_user(self, token: str) -> User | None:
        if token == self.token:
            return self.get_system_user_db()[self.user]

    @override
    def password_login(
        self, username: str, password: str, **kwargs: Any
    ) -> str | None:
        runningUser = self.user

        if runningUser == username:
            if pwd.getpwnam(username):
                if os.path.exists(host_service_socket_path):
                    try:
                        if check_password_on_host(username, password):
                            return self.token
                    except Exception:
                        logger.exception("Failed to check password on host")

                import pam

                try:
                    p = pam.authenticate()  # type: ignore
                except Exception:
                    p = pam
                # pyrefly: ignore [missing-attribute]
                if p.authenticate(username, password):
                    return self.token


def addLinuxSystemUser() -> None:
    """
    Add an admin user, representing the Linux system user
    actually running the process, using the system
    login mechanism.

    The rationale for this is that the system user has full
    acess to everything anyway.  Restrict to LAN for the obvious
     reasons.
    """
    import getpass

    username = getpass.getuser()
    ud = User(
        {
            "username": username,
            "groups": ["Administrators"],
            "password": "system",  # pragma: allowlist secret
            "settings": {"restrict-lan": True},
        }
    )

    set_user_if_not_exists(username, ud)


# Must come before
add_auth_plugin(LinuxSystemUserAuthenticationPlugin())

addLinuxSystemUser()
