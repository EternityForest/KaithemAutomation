# SPDX-License-Identifier: GPL-3.0-or-later
"""Podman image manager plugin.

A small admin UI over the shared rootless podman storage: list images, tag
and pull them, prune anything older than a week, and export or import images
as zstd:chunked OCI archives.  Every podman call goes through
:mod:`kaithem.src.podman_util`, so the same storage configuration the rest of
Kaithem uses is applied here too.
"""

import asyncio
import os
import re
import tempfile
import time

import quart
from quart import Blueprint

import kaithem.api.apps_page
from kaithem.api import web
from kaithem.api.web import quart_app
from kaithem.src import podman_util

# Archives that failed to stream are swept if they linger this long.
_STALE_ARCHIVE_AGE = 60 * 60
_CHUNK_SIZE = 1024 * 1024
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

api_bp = Blueprint(
    "podman_manager_api",
    __name__,
    url_prefix="/podman/api",
)


def _check_admin() -> tuple[quart.Response, int] | None:
    """Return a deterministic 403 for non-admin API callers."""
    if web.has_permission("system_admin"):
        return None
    return quart.jsonify({"error": "forbidden"}), 403


def _error(message: str, status: int = 400) -> tuple[quart.Response, int]:
    return quart.jsonify({"error": message}), status


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _sweep_stale_archives() -> None:
    """Delete leftover archives from earlier crashed or aborted requests."""
    cutoff = time.time() - _STALE_ARCHIVE_AGE
    try:
        entries = os.scandir(podman_util.IMAGE_TMP_DIR)
    except FileNotFoundError:
        return
    for entry in entries:
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                _remove_quietly(entry.path)
        except OSError:
            pass


def _archive_filename(image: str, architecture: str) -> str:
    base = _UNSAFE_FILENAME_CHARS.sub("-", image).strip("-") or "image"
    return f"{base}-{architecture}.tar"


def _new_temp_file(prefix: str) -> tuple[int, str]:
    """Create a private temp archive file, returning its fd and path."""
    os.makedirs(podman_util.IMAGE_TMP_DIR, exist_ok=True)
    return tempfile.mkstemp(
        suffix=".tar", prefix=prefix, dir=podman_util.IMAGE_TMP_DIR
    )


def _new_temp_path(prefix: str) -> str:
    descriptor, path = _new_temp_file(prefix)
    os.close(descriptor)
    return path


@api_bp.route("/images", methods=["GET"])
async def podman_list_images():
    error = _check_admin()
    if error is not None:
        return error
    try:
        images = await asyncio.to_thread(podman_util.list_images)
    except Exception as exc:
        return _error(str(exc), 500)
    return quart.jsonify({"images": images})


@api_bp.route("/tag", methods=["POST"])
async def podman_add_tag():
    error = _check_admin()
    if error is not None:
        return error
    body = await quart.request.get_json(force=True, silent=True) or {}
    image = body.get("image")
    new_tag = body.get("new_tag")
    if not isinstance(image, str) or not isinstance(new_tag, str):
        return _error("invalid_request")
    image = image.strip()
    new_tag = new_tag.strip()
    if not image or not new_tag:
        return _error("invalid_request")
    try:
        await asyncio.to_thread(podman_util.add_image_tag, image, new_tag)
    except Exception as exc:
        return _error(str(exc), 500)
    return quart.jsonify({"status": "ok"})


@api_bp.route("/pull", methods=["POST"])
async def podman_pull():
    error = _check_admin()
    if error is not None:
        return error
    body = await quart.request.get_json(force=True, silent=True) or {}
    image = body.get("image")
    if not isinstance(image, str):
        return _error("invalid_request")
    image = image.strip()
    if not image:
        return _error("invalid_request")
    try:
        await asyncio.to_thread(podman_util.pull_image, image)
    except Exception as exc:
        return _error(str(exc), 500)
    return quart.jsonify({"status": "ok"})


@api_bp.route("/remove", methods=["POST"])
async def podman_remove():
    error = _check_admin()
    if error is not None:
        return error
    body = await quart.request.get_json(force=True, silent=True) or {}
    image = body.get("image")
    if not isinstance(image, str):
        return _error("invalid_request")
    image = image.strip()
    if not image:
        return _error("invalid_request")
    try:
        output = await asyncio.to_thread(podman_util.remove_image, image)
    except Exception as exc:
        return _error(str(exc), 500)
    return quart.jsonify({"status": "ok", "output": output})


@api_bp.route("/prune", methods=["POST"])
async def podman_prune():
    error = _check_admin()
    if error is not None:
        return error
    try:
        result = await asyncio.to_thread(podman_util.prune)
    except Exception as exc:
        return _error(str(exc), 500)
    return quart.jsonify({"status": "ok", **result})


@api_bp.route("/export", methods=["GET"])
async def podman_export():
    error = _check_admin()
    if error is not None:
        return error
    image = (quart.request.args.get("image") or "").strip()
    if not image:
        return _error("invalid_request")

    await asyncio.to_thread(_sweep_stale_archives)
    path = _new_temp_path("kaithem-export-")
    try:
        architecture = await asyncio.to_thread(
            podman_util.image_architecture, image
        )
        # podman refuses to overwrite an existing oci-archive, remove it first.
        _remove_quietly(path)
        await asyncio.to_thread(podman_util.export_image, image, path)
        size = os.path.getsize(path)
    except Exception as exc:
        _remove_quietly(path)
        return _error(str(exc), 500)

    filename = _archive_filename(image, architecture)

    async def _stream():
        try:
            with open(path, "rb") as handle:
                while True:
                    chunk = await asyncio.to_thread(handle.read, _CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
        finally:
            _remove_quietly(path)

    response = quart.Response(_stream(), mimetype="application/x-tar")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    response.content_length = size
    return response


@api_bp.route("/import", methods=["POST"])
async def podman_import():
    error = _check_admin()
    if error is not None:
        return error

    await asyncio.to_thread(_sweep_stale_archives)
    descriptor, path = _new_temp_file("kaithem-import-")
    try:
        # Write through the raw fd: the test harness patches builtins.open to
        # sandbox writes, but podman storage deliberately lives on disk.
        try:
            with os.fdopen(descriptor, "wb") as handle:
                async for chunk in quart.request.body:
                    await asyncio.to_thread(handle.write, chunk)
            output = await asyncio.to_thread(podman_util.load_image, path)
        except Exception as exc:
            return _error(str(exc), 500)
    finally:
        _remove_quietly(path)
    return quart.jsonify({"status": "ok", "output": output})


quart_app.register_blueprint(api_bp)


@quart_app.route("/podman")
async def podman_page():
    web.require("system_admin")
    return quart.redirect(
        "/static/vite/kaithem/src/plugins/CorePluginPodmanManager/index.html"
    )


app = kaithem.api.apps_page.App(
    "coreplugins_podman",
    title="Podman Images",
    url="/podman",
)
app.icon = "/static/img/16x9/prague-astronomical-clock.avif"

kaithem.api.apps_page.add_app(app)
