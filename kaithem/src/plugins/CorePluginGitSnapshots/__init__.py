# SPDX-License-Identifier: GPL-3.0-or-later
"""Git backed snapshot backups, as a reusable web plugin.

The user facing idea is a "snapshot backup" of a server folder, with none
of git's vocabulary in sight.  Under the hood each snapshot is an ordinary
commit on ``main`` (see :mod:`.git_backend`), so the folder stays usable
by any real Git client.

The plugin is deliberately standalone: it only needs a folder path, and
the whole UI lives behind an iframe-able page route, so it can be dropped
into the text editor sidebar or any other host.
"""

from __future__ import annotations

import functools
from typing import Any
from urllib.parse import quote

import quart
import quart.utils
import structlog

from kaithem.api import web
from kaithem.api.web import quart_app
from kaithem.src import pages

from . import git_backend

logger = structlog.get_logger(__name__)

_VITE_PAGE = (
    "/static/vite/kaithem/src/plugins/CorePluginGitSnapshots/html/index.html"
)

api_bp = quart.Blueprint(
    "git_snapshots_api",
    __name__,
    url_prefix="/git-snapshots/api",
)


def _admin_api(f: Any) -> Any:
    """Require ``system_admin`` and answer with JSON, never a redirect.

    The snapshot UI is embedded in an iframe, so an authentication failure
    must arrive as data the frontend can render, not as a login page.
    """

    @functools.wraps(f)
    async def wrapper(*arg: Any, **kwargs: Any):
        try:
            pages.require("system_admin")
        except pages.KaithemUserPermissionError:
            if pages.getAcessingUser() == "__guest__":
                return quart.jsonify({"error": "not_logged_in"}), 401
            return quart.jsonify({"error": "forbidden"}), 403
        return await f(*arg, **kwargs)  # noqa: F821

    return wrapper


def _workspace() -> str:
    """The workspace path argument shared by every endpoint."""
    return (quart.request.args.get("workspace") or "").strip()


async def _run(job: Any) -> Any:
    """Run a blocking git operation off the event loop."""
    return await quart.utils.run_sync(job)()


@api_bp.route("/status", methods=["GET"])
@_admin_api
async def api_status():

    def job():
        path = _workspace()
        if not path:
            return quart.jsonify({"error": "missing_workspace"}), 400
        try:
            return quart.jsonify(git_backend.status(path))
        except git_backend.GitError as exc:
            return (
                quart.jsonify({"error": "git_error", "message": str(exc)}),
                400,
            )

    return await _run(job)


@api_bp.route("/snapshot", methods=["POST"])
@_admin_api
async def api_snapshot():
    form = dict(await quart.request.form)

    def job():
        path = (form.get("workspace") or "").strip()
        message = (form.get("message") or "").strip()
        if not path:
            return quart.jsonify({"error": "missing_workspace"}), 400
        if not message:
            return quart.jsonify({"error": "missing_message"}), 400
        try:
            commit = git_backend.take_snapshot(path, message)
        except git_backend.GitError as exc:
            return (
                quart.jsonify({"error": "git_error", "message": str(exc)}),
                400,
            )
        return quart.jsonify({"status": "ok", "commit": commit})

    return await _run(job)


@api_bp.route("/restore", methods=["POST"])
@_admin_api
async def api_restore():
    form = dict(await quart.request.form)

    def job():
        path = (form.get("workspace") or "").strip()
        commit = (form.get("commit") or "").strip()
        if not path:
            return quart.jsonify({"error": "missing_workspace"}), 400
        if not commit:
            return quart.jsonify({"error": "missing_commit"}), 400
        try:
            git_backend.restore_snapshot(path, commit)
        except git_backend.GitError as exc:
            return (
                quart.jsonify({"error": "git_error", "message": str(exc)}),
                400,
            )
        return quart.jsonify({"status": "ok"})

    return await _run(job)


quart_app.register_blueprint(api_bp)


@quart_app.route("/git-snapshots", methods=["GET"])
async def git_snapshots_page():
    """Iframe-able snapshot page for a server folder.

    The folder is a ``workspace`` query argument rather than a path
    segment, because it is an absolute filesystem path.  The page itself
    is a static Vite bundle; the permission check happens on every API
    call, and this route simply refuses to point a non-admin at it.
    """
    if not web.has_permission(["system_admin"]):
        return quart.jsonify({"error": "forbidden"}), 403
    workspace = _workspace()
    if not workspace:
        return quart.jsonify({"error": "missing_workspace"}), 400
    url = f"{_VITE_PAGE}?workspace={quote(workspace, safe='')}"
    return quart.redirect(url)
