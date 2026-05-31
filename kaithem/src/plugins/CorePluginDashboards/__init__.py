"""
Kaithem plugin for Dashboards resource type and file management.
Provides storage, APIs, and UI for managing dashboard boards and their assets (images, CSS, etc).
"""

import logging
import os
import shutil
from typing import Any
from urllib.parse import quote

import quart
from quart import Blueprint, jsonify, request

# Import Kaithem APIs
from kaithem.api import modules, resource_types, web
from kaithem.api.web import quart_app
from kaithem.api.web.dialogs import SimpleDialog
from kaithem.src import modules_state

logger = logging.getLogger(__name__)


# dashboard-resource-{module}-{resource} to
# (module, resource)


def parseDashboardId(id: str):
    id = id[len("dashboard-resource-") :]
    parts = id.split("-", 1)
    return parts[0], parts[1]


class DashboardResourceType(resource_types.ResourceType):
    """
    Resource type for Dashbeard dashboards.
    Stores dashboard definitions as YAML and manages associated file resources.
    """

    def __init__(self):
        super().__init__(
            type="dashboard",
            mdi_icon="view-dashboard",
            priority=50.0,
            title="Dashboard",
        )

    def create_page(self, module, path):
        d = SimpleDialog(f"New {self.type.capitalize()} in {module}")
        d.text_input("name")
        d.submit_button("Create")
        return d.render(self.get_create_target(module, path))

    def on_create_request(
        self, module: str, resource: str, kwargs: dict[str, Any]
    ):
        return {
            "resource": {
                "type": self.type,
            },
            "board": {
                "id": f"dashboard-resource-{module}-{resource}",
                "metadata": {},
                "rootComponent": {
                    "id": "root",
                    "name": "Main Layout",
                    "type": "plain-layout",
                    "config": {},
                    "children": [],
                },
                "bindings": [],
            },
        }

    def on_load(
        self, module: str, resource: str, data: modules.ResourceDictType
    ):
        """Initialize dashboard when loaded."""

    def on_delete(
        self, module: str, resource: str, data: modules.ResourceDictType
    ):
        """Clean up associated file resources when dashboard is deleted."""
        try:
            filedata_path = modules.filename_for_file_resource(module, resource)
            if os.path.isdir(filedata_path):
                shutil.rmtree(filedata_path)
        except Exception:
            logger.exception(
                "Error cleaning up dashboard files for %s/%s", module, resource
            )

    def edit_page(
        self, module: str, resource: str, data: modules_state.ResourceDictType
    ):
        """Redirect to the full-page dashboard editor."""

        url = f"/static/vite/kaithem/src/plugins/CorePluginDashboards/dashboards/index.html?board={quote(module)}:{quote(resource)}"

        return quart.redirect(url)


# Register the resource type
dashboard_rt = DashboardResourceType()
modules_state.resource_types["dashboard"] = dashboard_rt


class DashboardFilesAPI:
    """API for managing dashboard file resources."""

    @staticmethod
    def _resolve_virtual_path(dashboard_id: str, path: str) -> tuple[str, str]:
        """
        Resolve a virtual path to a real filesystem path.

        Virtual paths:
        - /board/... -> maps to {resource}.d folder (board's data folder)
        - /public_resources/... -> maps to public_resources/ in module root

        Returns (real_base_path, relative_path) where relative_path is the path
        within the base directory.
        """
        module, resource = parseDashboardId(dashboard_id)

        # Normalize path - remove leading slash
        path = path.lstrip("/")

        # Use exact match or proper path prefix to avoid false positives
        # Check for exact match first, then prefix match
        if path == "board" or path.startswith("board/"):
            # Board folder - maps to resource.d folder
            relative_path = path[6:] if path.startswith("board/") else ""
            base_path = modules.filename_for_file_resource(
                module, resource + ".d"
            )
            return base_path, relative_path
        elif path == "public_resources" or path.startswith("public_resources/"):
            # Public resources - maps to public_resources/ in module root
            relative_path = (
                path[17:] if path.startswith("public_resources/") else ""
            )
            base_path = modules.filename_for_file_resource(
                module, "public_resources"
            )
            return base_path, relative_path
        else:
            # Default to board folder for backward compatibility
            base_path = modules.filename_for_file_resource(
                module, resource + ".d"
            )
            return base_path, path

    @staticmethod
    def get_file(dashboard_id: str, path: str) -> tuple[str, str] | None:
        """
        Get a file's content and MIME type.
        Returns (content, mime_type) or None if not found.
        """
        base_path, relative_path = DashboardFilesAPI._resolve_virtual_path(
            dashboard_id, path
        )

        target_path = os.path.join(base_path, relative_path)

        # Security check - ensure path is within base
        if not os.path.normpath(target_path).startswith(
            os.path.normpath(base_path)
        ):
            return None

        if not os.path.isfile(target_path):
            return None

        # Determine MIME type
        import mimetypes

        mime_type = (
            mimetypes.guess_type(target_path)[0] or "application/octet-stream"
        )

        with open(target_path, "rb") as f:
            return f.read(), mime_type

    @staticmethod
    def list_resources(
        dashboard_id: str, subfolder: str = ""
    ) -> dict[str, Any]:
        """
        List available file resources in a given subfolder.
        Supports virtual paths:
        - /board/... -> lists from board's .d folder
        - /public_resources/... -> lists from module's public_resources folder
        - "" (empty) -> lists virtual root folders (imaginary folders)

        Returns dict with {resources: [...], error: ...}.
        """
        subfolder = subfolder.removeprefix("/")
        module, resource = parseDashboardId(dashboard_id)

        # Return virtual root folders when empty path is provided
        if not subfolder:
            return {
                "resources": [
                    {
                        "name": "board",
                        "type": "folder",
                        "url": f"/api/dashboards/{dashboard_id}/files/list?path=board",
                    },
                    {
                        "name": "public_resources",
                        "type": "folder",
                        "url": f"/api/dashboards/{dashboard_id}/files/list?path=public_resources",
                    },
                ],
                "error": None,
            }

        # Determine base path and relative path based on virtual path
        # Use exact match or proper path prefix to avoid false positives
        # (e.g., "board" should match but "board_something" should not)
        if subfolder == "public_resources" or subfolder.startswith(
            "public_resources/"
        ):
            # Public resources folder
            if subfolder.startswith("public_resources/"):
                relative_path = subfolder[
                    17:
                ]  # Remove "public_resources/" prefix
            else:
                relative_path = ""
            base_path = modules.filename_for_file_resource(
                module, "public_resources"
            )
        elif subfolder == "board" or subfolder.startswith("board/"):
            # Board folder
            if subfolder.startswith("board/"):
                relative_path = subfolder[6:]  # Remove "board/" prefix
            else:
                relative_path = ""
            base_path = modules.filename_for_file_resource(
                module, resource + ".d"
            )
        else:
            # Unknown path - return empty list with error
            return {"resources": [], "error": f"Unknown path: {subfolder}"}

        try:
            target_path = (
                os.path.join(base_path, relative_path)
                if relative_path
                else base_path
            )

            resources = []
            for filename in os.listdir(target_path):
                filepath = os.path.join(target_path, filename)
                virtual_path = (
                    f"{subfolder}/{filename}" if subfolder else filename
                )

                if os.path.isdir(filepath):
                    resources.append(
                        {
                            "name": os.path.basename(filepath),
                            "size": 0,
                            "type": "folder",
                            "url": f"/api/dashboards/{dashboard_id}/files/list?path={virtual_path}",
                        }
                    )
                elif os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    resources.append(
                        {
                            "name": os.path.basename(filepath),
                            "size": stat.st_size,
                            "type": "file",
                            "url": f"/api/dashboards/{dashboard_id}/files/get?path={virtual_path}",
                        }
                    )

            return {
                "resources": sorted(resources, key=lambda x: x["name"]),
                "error": None,
            }
        except FileNotFoundError:
            # Directory doesn't exist - return empty list
            return {"resources": [], "error": None}
        except Exception as e:
            logger.exception("Error listing resources")
            return {"resources": [], "error": str(e)}


# Create Quart Blueprint for API routes
api_bp = Blueprint("dashboard_api", __name__, url_prefix="/api/dashboards")


@api_bp.route("/<boardid>/files/list", methods=["GET"])
async def list_resources_endpoint(boardid: str):
    """List resources in a subfolder.

    Query params:
    - path: virtual path like "/board/subfolder" or "/public_resources"
    """
    web.require("system_admin")
    subfolder = request.args.get("path", "")
    result = DashboardFilesAPI.list_resources(boardid, subfolder)
    return jsonify(result)


@api_bp.route("/<boardid>/files/get", methods=["GET"])
async def get_file_endpoint(boardid: str):
    """Get a file."""
    web.require("system_admin")
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "Missing path"}), 400

    result = DashboardFilesAPI.get_file(boardid, path)
    if result is None:
        return jsonify({"error": "File not found"}), 404

    data, mime_type = result
    return data, 200, {"Content-Type": mime_type}


@api_bp.route("/<boardid>/load", methods=["GET"])
async def load_board_endpoint(boardid: str):
    """Load a board from Kaithem."""
    web.require("system_admin")
    module, resource = parseDashboardId(boardid)
    board_data = modules_state.ActiveModules[module][resource]["board"]
    return jsonify({"board": board_data, "error": None})


@api_bp.route("/<boardid>/save", methods=["POST"])
async def save_board_endpoint(boardid: str):
    """Save a board to Kaithem."""
    web.require("system_admin")
    module, resource = parseDashboardId(boardid)

    try:
        request_data = await request.json
        board = request_data.get("board")
        if not board:
            return jsonify({"error": "Missing board data"}), 400

        with modules_state.modulesLock:
            # Update the resource in Kaithem
            modules_state.raw_insert_resource(
                module,
                resource,
                {
                    "resource": {
                        "type": "dashboard",
                    },
                    "board": board,
                },
            )

        return jsonify({"success": True, "error": None})
    except Exception as e:
        logger.exception("Error saving board")
        return jsonify({"error": str(e)}), 500


@api_bp.route("/system-themes", methods=["GET"])
async def get_system_themes_endpoint():
    """Get list of available system themes."""
    from kaithem.api import settings as api_settings

    themes = api_settings.get_system_themes()
    return jsonify({"themes": themes, "error": None})


quart_app.register_blueprint(api_bp)
