"""Client library for talking to the host-services UDS.

The client is paranoid on purpose: it refuses to send credentials unless it
has verified that:

  1. The socket file exists, is a socket, is owned by the calling UID, and
     is mode ``0o600`` (no group/other bits).
  2. The peer it actually connected to presents ``SO_PEERCRED`` credentials
     whose ``uid`` matches the calling UID.

This protects against a hostile local user replacing the socket, hard-linking
it, or running a man-in-the-middle that hands our connection off to a server
running as another user.
"""

from __future__ import annotations

import os
import socket
import stat
from pathlib import Path
from typing import Any

from .socket_path import default_socket_path


class InsecureConnectionError(RuntimeError):
    """The host-services socket failed a safety check."""


class AuthServerUnavailable(RuntimeError):
    """Could not reach the host-services server (after safety checks passed)."""


# We speak HTTP/1.1 by hand here so we can fully control the AF_UNIX connect
# (and run SO_PEERCRED checks) before sending any credential.
class UDSClient:
    def __init__(self, socket_path: Path, expected_uid: int, timeout: float):
        self.socket_path = socket_path
        self.expected_uid = expected_uid
        self.timeout = timeout

    def _connect_and_verify(self) -> socket.socket:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        try:
            s.connect(str(self.socket_path))
        except OSError as e:
            s.close()
            raise AuthServerUnavailable(f"connect failed: {e!r}")

        try:
            creds = s.getsockopt(
                socket.SOL_SOCKET,
                getattr(socket, "SO_PEERCRED", 16),
                12,
            )
        except OSError as e:
            s.close()
            raise InsecureConnectionError(f"could not read SO_PEERCRED: {e!r}")

        if isinstance(creds, tuple):
            pid, uid, _gid = creds[0], creds[1], creds[2]
        else:
            pid = int.from_bytes(creds[0:4], "little", signed=True)
            uid = int.from_bytes(creds[4:8], "little", signed=False)

        if uid != self.expected_uid:
            s.close()
            raise InsecureConnectionError(
                f"socket peer uid={uid} does not match expected uid={self.expected_uid}"
            )
        if pid <= 0:
            s.close()
            raise InsecureConnectionError(
                f"socket peer pid={pid} looks invalid"
            )
        return s

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        import json

        body = json.dumps(payload).encode("utf-8")
        req = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: localhost\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("ascii") + body

        s = self._connect_and_verify()
        try:
            s.sendall(req)
            buf = bytearray()
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf.extend(chunk)
        finally:
            s.close()

        text = bytes(buf).decode("iso-8859-1", errors="replace")
        header_blob, _, rest = text.partition("\r\n\r\n")
        status_line = header_blob.split("\r\n", 1)[0]
        try:
            status_code = int(status_line.split(" ", 2)[1])
        except (IndexError, ValueError) as e:
            raise AuthServerUnavailable(
                f"bad status line: {status_line!r}"
            ) from e

        if status_code != 200:
            raise AuthServerUnavailable(f"server returned HTTP {status_code}")

        try:
            return json.loads(rest)
        except ValueError as e:
            raise AuthServerUnavailable(f"server returned non-JSON body: {e!r}")


def _verify_socket_file(path: Path, expected_uid: int) -> None:
    """Pre-flight checks on the socket file itself."""
    try:
        st = path.stat()
    except FileNotFoundError as e:
        raise AuthServerUnavailable(f"socket not found: {path}") from e

    if not stat.S_ISSOCK(st.st_mode):
        raise InsecureConnectionError(f"{path} is not a socket")

    if st.st_uid != expected_uid:
        raise InsecureConnectionError(
            f"{path} owned by uid {st.st_uid}, expected {expected_uid}"
        )

    # Reject any group/other permissions — the socket must be 0o600.
    if st.st_mode & 0o077:
        raise InsecureConnectionError(
            f"{path} has group/other permissions (mode={oct(st.st_mode & 0o777)}); refusing"
        )

    # Refuse if it's a hardlink or symlink that could be redirected mid-flight.
    nlinks = getattr(st, "st_nlink", 1)
    if nlinks != 1:
        raise InsecureConnectionError(
            f"{path} has st_nlink={nlinks}; refusing hardlinked socket"
        )


def check_password(
    username: str,
    password: str,
    *,
    socket_path: Path | None = None,
    timeout: float = 5.0,
) -> bool:
    """Return True if ``username``/``password`` authenticates against PAM on the host.

    Raises:
        InsecureConnectionError: the socket failed a safety check.
        AuthServerUnavailable: the server is not reachable or returned an error.
    """
    path = socket_path or default_socket_path()
    my_uid = os.getuid()

    _verify_socket_file(path, my_uid)

    client = UDSClient(path, my_uid, timeout=timeout)
    resp = client.post_json(
        "/check_password", {"user": username, "password": password}
    )
    return bool(resp.get("ok"))
