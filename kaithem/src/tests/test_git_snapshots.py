# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the CorePluginGitSnapshots plugin.

The snapshot logic is exercised against the real ``git`` binary in a
throwaway folder under the /dev/shm test sandbox, so the exact subprocess
behaviour (branch handling, detached restores, lazy init, nested-repo
refusal) is covered for real rather than mocked.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid

import pytest

from kaithem.src.plugins.CorePluginGitSnapshots import git_backend

from .helpers import make_client

#: Identity for the git commands the tests run for setup.  A fixed
#: identity keeps test repos independent of any global git config.
_IDENTITY = ["-c", "user.name=Test", "-c", "user.email=test@localhost"]


def _git(path: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git for test setup/fixtures with a deterministic identity."""
    return subprocess.run(
        ["git", "--no-pager", *_IDENTITY, *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )


def _write(path: str, name: str, text: str) -> None:
    with open(os.path.join(path, name), "w", encoding="utf-8") as handle:
        handle.write(text)


def _read(path: str, name: str) -> str:
    with open(os.path.join(path, name), encoding="utf-8") as handle:
        return handle.read()


def _branch(path: str) -> str:
    name = _git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return "" if name == "HEAD" else name


def _subject(path: str, ref: str = "HEAD") -> str:
    return _git(path, "log", "-1", "--format=%s", ref).stdout.strip()


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch):
    """Keep git away from the developer's global config.

    git_backend strips every GIT_* variable from the environment, so HOME
    is the only lever left to isolate git's configuration for the tests.
    """
    home = "/dev/shm/kaithem_tests/git-home"
    os.makedirs(home, exist_ok=True)
    monkeypatch.setenv("HOME", home)


@pytest.fixture
def workspace():
    """A throwaway server folder under the /dev/shm test sandbox."""
    path = tempfile.mkdtemp(dir="/dev/shm/kaithem_tests")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _make_repo(path: str, branch: str = "main") -> None:
    """Create a one-commit repository at ``path`` without the backend."""
    _git(path, "init", "-b", branch)
    _write(path, "seed.txt", "seed")
    _git(path, "add", "-A")
    _git(path, "commit", "--quiet", "-m", "seed")


# -- repo classification --------------------------------------------------


def test_repo_state_classifies_folders(workspace):
    assert git_backend.repo_state(workspace) == git_backend.NOT_A_REPO
    _make_repo(workspace)
    assert git_backend.repo_state(workspace) == git_backend.OWN_REPO
    nested = os.path.join(workspace, "inner")
    os.makedirs(nested)
    assert git_backend.repo_state(nested) == git_backend.NESTED_REPO


def test_repo_state_rejects_a_missing_folder(workspace):
    missing = os.path.join(workspace, "nope")
    with pytest.raises(git_backend.GitError):
        git_backend.repo_state(missing)


# -- listing --------------------------------------------------------------


def test_list_snapshots_empty_without_a_repo(workspace):
    assert git_backend.list_snapshots(workspace) == []


def test_list_snapshots_empty_without_main(workspace):
    _make_repo(workspace, branch="trunk")
    # The folder is its own repo, but there is no main branch yet, so it
    # looks exactly like a folder that never used snapshots.
    assert git_backend.list_snapshots(workspace) == []


def test_list_snapshots_newest_first(workspace):
    _make_repo(workspace)
    _write(workspace, "a.txt", "a")
    _git(workspace, "add", "-A")
    _git(workspace, "commit", "--quiet", "-m", "second")
    snapshots = git_backend.list_snapshots(workspace)
    assert [snap.subject for snap in snapshots] == ["second", "seed"]
    assert snapshots[0].author == "Test"
    assert snapshots[0].commit == snapshots[0].commit.strip()
    assert len(snapshots[0].short) < len(snapshots[0].commit)


# -- taking snapshots -----------------------------------------------------


def test_take_snapshot_initializes_the_repo(workspace):
    _write(workspace, "hello.txt", "hi")
    commit = git_backend.take_snapshot(workspace, "first snapshot")

    assert git_backend.repo_state(workspace) == git_backend.OWN_REPO
    assert _branch(workspace) == "main"
    assert _subject(workspace) == "first snapshot"
    snapshots = git_backend.list_snapshots(workspace)
    assert [snap.subject for snap in snapshots] == ["first snapshot"]
    assert snapshots[0].commit == commit
    # A plain init must not leave a stray temp branch behind.
    branches = _git(workspace, "branch", "--format=%(refname:short)")
    assert branches.stdout.split() == ["main"]


def test_take_snapshot_requires_a_message(workspace):
    with pytest.raises(git_backend.GitError) as excinfo:
        git_backend.take_snapshot(workspace, "   ")
    assert "message" in str(excinfo.value)
    assert not os.path.isdir(os.path.join(workspace, ".git"))


def test_take_snapshot_with_nothing_new_fails(workspace):
    _write(workspace, "hello.txt", "hi")
    git_backend.take_snapshot(workspace, "first")
    with pytest.raises(git_backend.GitError) as excinfo:
        git_backend.take_snapshot(workspace, "again")
    assert "Nothing to snapshot" in str(excinfo.value)


def test_take_snapshot_creates_main_from_another_branch(workspace):
    _make_repo(workspace, branch="trunk")
    _write(workspace, "new.txt", "new")
    commit = git_backend.take_snapshot(workspace, "onto main")

    assert _branch(workspace) == "main"
    assert _subject(workspace) == "onto main"
    assert _git(workspace, "rev-parse", "HEAD").stdout.strip() == commit
    # The pre-existing commit is preserved on main, so the snapshot sits
    # on top of the old history rather than replacing it.
    assert [snap.subject for snap in git_backend.list_snapshots(workspace)] == [
        "onto main",
        "seed",
    ]
    assert _read(workspace, "new.txt") == "new"
    assert _read(workspace, "seed.txt") == "seed"
    branches = _git(workspace, "branch", "--format=%(refname:short)")
    assert branches.stdout.split() == ["main", "trunk"]


def test_snapshot_from_a_feature_branch_lands_on_main(workspace):
    _make_repo(workspace)
    _git(workspace, "switch", "--quiet", "-c", "feature")
    _write(workspace, "feature.txt", "work")
    commit = git_backend.take_snapshot(workspace, "from feature")

    # We never merge: main simply gains the working tree as one commit.
    assert _branch(workspace) == "main"
    assert _git(workspace, "rev-parse", "HEAD").stdout.strip() == commit
    assert _read(workspace, "feature.txt") == "work"
    branches = _git(workspace, "branch", "--format=%(refname:short)")
    assert "feature" in branches.stdout.split()
    # No throwaway snapshot branch survived.
    assert not [
        name
        for name in branches.stdout.split()
        if name.startswith("snapshot-")
    ]
    assert [snap.subject for snap in git_backend.list_snapshots(workspace)] == [
        "from feature",
        "seed",
    ]


# -- restoring ------------------------------------------------------------


def test_restore_snapshot_discards_changes(workspace):
    _write(workspace, "a.txt", "one")
    first = git_backend.take_snapshot(workspace, "one")
    _write(workspace, "a.txt", "two")
    _write(workspace, "b.txt", "extra")
    git_backend.take_snapshot(workspace, "two")

    git_backend.restore_snapshot(workspace, first)

    assert _read(workspace, "a.txt") == "one"
    assert not os.path.exists(os.path.join(workspace, "b.txt"))
    # A restore never rewrites main, so both snapshots stay listed.
    assert len(git_backend.list_snapshots(workspace)) == 2
    assert _branch(workspace) == ""


def test_snapshot_after_restore_returns_to_main(workspace):
    _write(workspace, "a.txt", "one")
    first = git_backend.take_snapshot(workspace, "one")
    _write(workspace, "a.txt", "two")
    git_backend.take_snapshot(workspace, "two")
    git_backend.restore_snapshot(workspace, first)

    # Taking a snapshot from the detached HEAD is the "undo the undo"
    # path: it must put main back in a normal state.
    git_backend.take_snapshot(workspace, "recovered")

    assert _branch(workspace) == "main"
    assert _subject(workspace) == "recovered"
    assert _read(workspace, "a.txt") == "one"
    assert len(git_backend.list_snapshots(workspace)) == 3


def test_restore_rejects_an_unknown_commit(workspace):
    _make_repo(workspace)
    with pytest.raises(git_backend.GitError) as excinfo:
        git_backend.restore_snapshot(workspace, "deadbeef" * 5)
    assert "could not be found" in str(excinfo.value)


def test_restore_requires_a_repo(workspace):
    with pytest.raises(git_backend.GitError):
        git_backend.restore_snapshot(workspace, "HEAD")


# -- nested repositories --------------------------------------------------


def test_nested_repo_is_refused_and_left_untouched(workspace):
    _make_repo(workspace)
    nested = os.path.join(workspace, "inner")
    os.makedirs(nested)
    _write(nested, "file.txt", "content")
    before = _git(workspace, "rev-list", "--count", "HEAD").stdout.strip()

    with pytest.raises(git_backend.GitError) as excinfo:
        git_backend.take_snapshot(nested, "should not happen")
    assert "another Git repository" in str(excinfo.value)

    # No submodule, no nested repository, no commit against the parent.
    assert not os.path.isdir(os.path.join(nested, ".git"))
    assert not os.path.exists(os.path.join(workspace, ".gitmodules"))
    after = _git(workspace, "rev-list", "--count", "HEAD").stdout.strip()
    assert after == before
    assert git_backend.list_snapshots(nested) == []


# -- status ---------------------------------------------------------------


def test_status_reports_an_empty_folder(workspace):
    status = git_backend.status(workspace)
    assert status["state"] == git_backend.NOT_A_REPO
    assert status["snapshots"] == []
    assert status["workspace"] == os.path.realpath(workspace)
    assert status["name"] == os.path.basename(os.path.realpath(workspace))


def test_status_reports_snapshots_and_head(workspace):
    _write(workspace, "a.txt", "one")
    commit = git_backend.take_snapshot(workspace, "only")
    status = git_backend.status(workspace)
    assert status["state"] == git_backend.OWN_REPO
    assert status["head"] == commit
    assert [snap["subject"] for snap in status["snapshots"]] == ["only"]


# -- web routes -----------------------------------------------------------


async def test_api_rejects_guests(workspace):
    from kaithem.src import quart_app

    client = quart_app.app.test_client(use_cookies=True)
    response = await client.get(
        "/git-snapshots/api/status", query_string={"workspace": workspace}
    )
    assert response.status_code == 401
    assert (await response.get_json())["error"] == "not_logged_in"


async def test_api_requires_a_workspace():
    client = await make_client()
    response = await client.get("/git-snapshots/api/status")
    assert response.status_code == 400
    assert (await response.get_json())["error"] == "missing_workspace"


async def test_api_status_returns_the_folder_state(workspace):
    client = await make_client()
    response = await client.get(
        "/git-snapshots/api/status",
        query_string={"workspace": workspace},
    )
    assert response.status_code == 200
    assert (await response.get_json())["state"] == git_backend.NOT_A_REPO


async def test_api_snapshot_and_restore_round_trip(workspace):
    client = await make_client()
    _write(workspace, "a.txt", "one")

    taken = await client.post(
        "/git-snapshots/api/snapshot",
        form={"workspace": workspace, "message": "first"},
    )
    assert taken.status_code == 200
    commit = (await taken.get_json())["commit"]

    _write(workspace, "a.txt", "two")
    restored = await client.post(
        "/git-snapshots/api/restore",
        form={"workspace": workspace, "commit": commit},
    )
    assert restored.status_code == 200
    assert _read(workspace, "a.txt") == "one"


async def test_api_snapshot_needs_a_message(workspace):
    client = await make_client()
    response = await client.post(
        "/git-snapshots/api/snapshot",
        form={"workspace": workspace, "message": "  "},
    )
    assert response.status_code == 400
    assert (await response.get_json())["error"] == "missing_message"


async def test_api_snapshot_reports_git_errors(workspace):
    client = await make_client()
    _write(workspace, "a.txt", "one")
    response = await client.post(
        "/git-snapshots/api/snapshot",
        form={"workspace": workspace, "message": "first"},
    )
    assert response.status_code == 200
    second = await client.post(
        "/git-snapshots/api/snapshot",
        form={"workspace": workspace, "message": "again"},
    )
    assert second.status_code == 400
    body = await second.get_json()
    assert body["error"] == "git_error"
    assert "Nothing to snapshot" in body["message"]


async def test_page_route_rejects_guests(workspace):
    from kaithem.src import quart_app

    client = quart_app.app.test_client(use_cookies=True)
    response = await client.get(
        "/git-snapshots", query_string={"workspace": workspace}
    )
    assert response.status_code == 403


async def test_page_route_redirects_admins_to_the_bundle(workspace):
    from urllib.parse import quote

    client = await make_client()
    response = await client.get(
        "/git-snapshots", query_string={"workspace": workspace}
    )
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "CorePluginGitSnapshots" in location
    assert quote(workspace, safe="") in location
    # A missing workspace is a bad request rather than a broken page.
    empty = await client.get("/git-snapshots")
    assert empty.status_code == 400


async def test_page_route_requires_a_workspace():
    client = await make_client()
    response = await client.get("/git-snapshots")
    assert response.status_code == 400


def test_workspace_helper_is_a_plain_path(workspace):
    # Guards against a future refactor that starts treating the folder as
    # an opaque token: the backend must see the raw filesystem path.
    assert os.path.isabs(git_backend.status(workspace)["workspace"])
    token = uuid.uuid4().hex
    assert token not in workspace
