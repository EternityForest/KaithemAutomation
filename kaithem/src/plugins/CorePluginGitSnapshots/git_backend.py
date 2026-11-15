# SPDX-License-Identifier: GPL-3.0-or-later
"""Git backed snapshot backups for a server folder.

This is deliberately a thin layer over the system ``git`` binary: every
operation is a plain subprocess call, with no library in between.  A
"snapshot" is just an ordinary commit on the ``main`` branch, so anything
this tool does stays readable and usable by a full Git client.

Two rules keep the tool from surprising anyone:

* We only ever operate on a folder that is the root of its own
  repository.  If the folder sits inside a larger repository we refuse to
  touch it (we never create a submodule and never commit to the parent).
* Taking and listing snapshots hides ``git init`` completely.  ``init``
  only ever happens the moment the user asks for their first snapshot.

All commands run as the server user, in the folder's own directory, with
any inherited ``GIT_*`` variables stripped so a stray ``GIT_DIR`` in the
server environment cannot redirect a command at some other repository.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass

#: Nothing here should need to reach the network, so a generous timeout is
#: really just a guard against a git process wedging itself forever.
GIT_TIMEOUT_S = 120

#: Fallback author identity, used only when git has none configured.  A
#: snapshot is a local backup, so a stable placeholder beats failing.
_FALLBACK_IDENTITY = [
    "-c",
    "user.name=Kaithem Snapshot",
    "-c",
    "user.email=kaithem@localhost",
]

#: The branch snapshots are always committed to.
MAIN_BRANCH = "main"

# Repository shapes reported by :func:`repo_state`.
NOT_A_REPO = "no_repo"
OWN_REPO = "own_repo"
NESTED_REPO = "nested_repo"


class GitError(RuntimeError):
    """A git command failed for a reason worth showing the user."""


@dataclass(frozen=True)
class Snapshot:
    """One commit on ``main``, presented to the user as a snapshot."""

    commit: str
    short: str
    subject: str
    author: str
    timestamp: int

    def as_dict(self) -> dict[str, object]:
        return {
            "commit": self.commit,
            "short": self.short,
            "subject": self.subject,
            "author": self.author,
            "timestamp": self.timestamp,
        }


def _env() -> dict[str, str]:
    """A clean environment for a git subprocess."""
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_"):
            del env[key]
    # Never block a snapshot waiting for credentials on a terminal.
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git(
    path: str, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run one git command inside ``path`` and return the result."""
    try:
        proc = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=path,
            env=_env(),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise GitError(
            "The git command is not installed on the server"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError("A git command took too long and was stopped") from exc
    if check and proc.returncode != 0:
        raise GitError(_error_text(proc))
    return proc


def _error_text(proc: subprocess.CompletedProcess[str]) -> str:
    """A short, single line reason from a failed git command."""
    text = (proc.stderr or proc.stdout or "git failed").strip()
    if not text:
        text = f"git exited with status {proc.returncode}"
    return text.splitlines()[-1].strip()


def _validated(path: str) -> str:
    """Resolve a workspace path and insist that it is a folder."""
    real = os.path.realpath(path)
    if not os.path.isdir(real):
        raise GitError(f"Not a folder on the server: {path}")
    return real


def repo_state(path: str) -> str:
    """Classify ``path`` as its own repo, nested in one, or not a repo."""
    real = _validated(path)
    top = _git(real, "rev-parse", "--show-toplevel", check=False)
    if top.returncode != 0:
        return NOT_A_REPO
    try:
        toplevel = os.path.realpath(top.stdout.strip())
    except OSError:
        return NOT_A_REPO
    return OWN_REPO if toplevel == real else NESTED_REPO


def _has_main(path: str) -> bool:
    proc = _git(
        path, "rev-parse", "--verify", "--quiet", "refs/heads/main", check=False
    )
    return proc.returncode == 0


def _has_commits(path: str) -> bool:
    proc = _git(path, "rev-parse", "--verify", "--quiet", "HEAD", check=False)
    return proc.returncode == 0


def _current_branch(path: str) -> str:
    """The current branch name, or an empty string when detached.

    ``symbolic-ref`` reports the branch even before the first commit, so
    a freshly initialised repository reads as being on ``main`` rather
    than looking detached.
    """
    proc = _git(path, "symbolic-ref", "--short", "HEAD", check=False)
    if proc.returncode == 0:
        return proc.stdout.strip()
    return ""


def list_snapshots(path: str) -> list[Snapshot]:
    """Commits on ``main``, newest first.

    Returns an empty list whenever there is no repository or no ``main``
    branch, so that a folder without any snapshots is indistinguishable
    from one that has never used this tool.
    """
    if repo_state(path) != OWN_REPO:
        return []
    real = os.path.realpath(path)
    if not _has_main(real):
        return []
    proc = _git(
        real, "log", MAIN_BRANCH, "--format=%H%x1f%h%x1f%at%x1f%an%x1f%s"
    )
    snapshots: list[Snapshot] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\x1f", 4)
        if len(parts) != 5:
            continue
        commit, short, timestamp, author, subject = parts
        snapshots.append(
            Snapshot(
                commit=commit,
                short=short,
                subject=subject,
                author=author,
                timestamp=int(timestamp or 0),
            )
        )
    return snapshots


def _ensure_main(path: str) -> None:
    """Make sure a ``main`` branch exists, without losing any commit."""
    if _has_main(path):
        return
    if not _has_commits(path):
        # Unborn HEAD: just point it at main so the first commit lands
        # there, whatever the machine's init.defaultBranch happens to be.
        _git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    else:
        # Existing history on another branch: mark the current commit as
        # main so snapshots accumulate there.
        _git(path, "branch", MAIN_BRANCH)


def _ensure_repo(path: str) -> None:
    """Create ``path`` as its own repository if it is not one already."""
    state = repo_state(path)
    if state == NESTED_REPO:
        raise GitError(
            "This folder is inside another Git repository. Snapshots must "
            "be taken from that repository, so nothing was changed here."
        )
    if state == NOT_A_REPO:
        _git(path, "init")
    _ensure_main(path)


def _identity_args(path: str) -> list[str]:
    """Extra ``-c`` identity args, only when git has none configured."""
    proc = _git(path, "config", "--get", "user.email", check=False)
    return [] if proc.stdout.strip() else list(_FALLBACK_IDENTITY)


def _commit(path: str, message: str, *, allow_empty: bool = False) -> None:
    args = [*_identity_args(path), "commit", "--quiet"]
    if allow_empty:
        # The throwaway carrier branch may hold a tree identical to the
        # commit it started from (e.g. snapshotting a restored folder),
        # and it exists only to carry a tree, so an empty commit is fine.
        args.append("--allow-empty")
    args += ["-m", message]
    _git(path, *args)


def take_snapshot(path: str, message: str) -> str:
    """Commit the current folder contents to ``main`` and return the sha.

    On ``main`` the snapshot is a normal commit.  Otherwise the snapshot
    is first committed to a throwaway branch, then reproduced as a single
    commit on ``main`` (never a merge), so ``main`` always stays a clean
    linear list of snapshots.
    """
    real = _validated(path)
    message = (message or "").strip()
    if not message:
        raise GitError("A snapshot needs a message")
    _ensure_repo(real)

    _git(real, "add", "-A")
    if _has_main(real):
        diff = _git(
            real, "diff", "--cached", "--quiet", MAIN_BRANCH, check=False
        )
        if diff.returncode == 0:
            raise GitError("Nothing to snapshot: no changes since the last one")

    if _current_branch(real) == MAIN_BRANCH:
        _commit(real, message)
    else:
        temp_branch = "snapshot-" + uuid.uuid4().hex
        _git(real, "switch", "--quiet", "-c", temp_branch)
        _commit(real, message, allow_empty=True)
        _git(real, "switch", "--quiet", MAIN_BRANCH)
        _git(
            real,
            "restore",
            f"--source={temp_branch}",
            "--staged",
            "--worktree",
            "--",
            ".",
        )
        _commit(real, message)
        # The carrier branch is thrown away on purpose: its commit may
        # carry nothing new (an empty tree), so it is force deleted
        # rather than needing to be reachable from main.
        _git(real, "branch", "-D", temp_branch)

    return _git(real, "rev-parse", "HEAD").stdout.strip()


def restore_snapshot(path: str, commit: str) -> None:
    """Check out a snapshot into a detached HEAD, discarding changes.

    This deliberately moves ``main`` nowhere: the newest snapshots stay
    listed.  The working tree simply becomes an exact copy of the chosen
    snapshot, which is the "restore my files" gesture users expect.
    """
    real = _validated(path)
    if repo_state(real) != OWN_REPO:
        raise GitError("This folder is not a snapshot repository")
    commit = (commit or "").strip()
    if not commit:
        raise GitError("No snapshot was selected")
    verify = _git(
        real,
        "rev-parse",
        "--verify",
        "--quiet",
        f"{commit}^{{commit}}",
        check=False,
    )
    if verify.returncode != 0:
        raise GitError("That snapshot could not be found")
    _git(
        real,
        "-c",
        "advice.detachedHead=false",
        "checkout",
        "--force",
        "--detach",
        commit,
    )


def status(path: str) -> dict[str, object]:
    """Everything the snapshot UI needs to render one workspace."""
    real = _validated(path)
    state = repo_state(real)
    if state != OWN_REPO:
        return {
            "state": state,
            "workspace": real,
            "name": os.path.basename(real) or real,
            "snapshots": [],
        }
    head = _git(real, "rev-parse", "HEAD", check=False)
    return {
        "state": state,
        "workspace": real,
        "name": os.path.basename(real) or real,
        "snapshots": [s.as_dict() for s in list_snapshots(real)],
        "head": head.stdout.strip() if head.returncode == 0 else "",
    }
