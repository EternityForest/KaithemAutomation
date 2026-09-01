#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Zero-dependency wrapper that ensures its child process is killed when
this wrapper (and therefore its parent) dies.

This exists specifically to wrap ``jack_midi_dump``.  We spawn one
``jack_midi_dump`` subprocess per MIDI source.  If our Python process
dies unexpectedly (segfault, SIGKILL, oom-kill, etc.) the kernel will
normally leave the children behind.  That is bad for two reasons:

1. They keep holding JACK client slots and ports, polluting the graph
   even after a restart.
2. JACK itself may refuse to come back up cleanly if it sees clients
   that reference ports that no longer exist.

We solve this with ``prctl(PR_SET_PDEATHSIG, SIGTERM)`` set on ourselves
via ctypes.  After the prctl call, if our parent process dies the
kernel will deliver SIGTERM to us, which we then forward by exiting.
We then ``os.execvp`` the actual command so it replaces our process;
it inherits the same parent-death signal, so it dies too when our
parent dies.

This works because the death signal is inherited across exec().

Usage::

    jack_midi_dump_pdeathsig.py <command> [args...]

stdio is passed through unchanged.  Exit status is the wrapped
command's exit status.  On platforms where prctl is not available we
just ``execvp`` without the prctl call.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import signal
import sys


def _set_pdeathsig() -> None:
    """Set PR_SET_PDEATHSIG to SIGTERM so the kernel kills us when our
    parent dies.

    No-op on non-Linux platforms (and on Linux with no libc).
    """
    if not sys.platform.startswith("linux"):
        return

    libc_name = ctypes.util.find_library("c") or "libc.so.6"
    try:
        libc = ctypes.CDLL(libc_name, use_errno=True)
    except OSError:
        return

    # On Linux these constants live in <sys/prctl.h> / <signal.h>.
    PR_SET_PDEATHSIG = 1
    SIGTERM = signal.SIGTERM

    # prctl returns 0 on success and -1 on error (errno set).
    try:
        rc = libc.prctl(PR_SET_PDEATHSIG, SIGTERM, 0, 0, 0)
    except AttributeError:
        return
    if rc != 0:
        # Not fatal; just means the wrapper won't self-terminate if
        # the parent dies.  Surface the error to stderr so it's
        # visible in the log, then continue with exec().
        err = ctypes.get_errno()
        print(
            f"jack_midi_dump_pdeathsig: prctl(PR_SET_PDEATHSIG) failed (errno={err})",
            file=sys.stderr,
        )


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: jack_midi_dump_pdeathsig.py <command> [args...]",
            file=sys.stderr,
        )
        return 2

    # Set the parent-death signal before we replace our image with the
    # real command; the prctl attribute is preserved across exec().
    _set_pdeathsig()

    # Replace ourselves with the requested command.  stdin/stdout/
    # stderr are inherited unchanged.
    try:
        os.execvp(sys.argv[1], sys.argv[1:])
    except OSError as e:
        print(
            f"jack_midi_dump_pdeathsig: failed to exec {sys.argv[1]!r}: {e}",
            file=sys.stderr,
        )
        # 127 is the conventional "command not found" exit code, but
        # OSError.errno for ENOENT is the more accurate signal.
        return 127

    # Unreachable; execvp only returns on failure.
    return 1


if __name__ == "__main__":
    sys.exit(main())
