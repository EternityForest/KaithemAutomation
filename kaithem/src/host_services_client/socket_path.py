"""Resolve the per-user Unix-domain socket path for the host services daemon"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SOCKET_NAME = "kaithem-host-services.sock"


def default_socket_path() -> Path:
    """Return the canonical per-user socket path.

    Uses ``$XDG_RUNTIME_DIR`` (Linux convention for per-user runtime files).
    Falls back to ``/tmp/kaithem-host-services-<uid>.sock`` if it is unset,
    but in normal systemd-user / desktop usage it will always be set.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / DEFAULT_SOCKET_NAME
    return Path(f"/tmp/kaithem-host-services-{os.getuid()}.sock")
