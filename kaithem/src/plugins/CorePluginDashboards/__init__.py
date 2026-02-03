"""
Kaithem plugin for Dashboards resource type and file management.
Provides storage, APIs, and UI for managing dashboard boards and their assets (images, CSS, etc).
"""

import logging
import mimetypes
import os
import shutil
from typing import Any
from urllib.parse import quote

import quart
import yaml
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

    def scan_dir(self, dir: str) -> dict[str, resource_types.ResourceDictType]:
        """Scan directory for .yaml dashboard files."""
        r = {}
        try:
            for filename in os.listdir(dir):
                if filename.endswith(".yaml") and not filename.startswith("_"):
                    filepath = os.path.join(dir, filename)
                    try:
                        with open(filepath) as f:
                            data = yaml.safe_load(f) or {}
                        resource_name = filename[:-5]  # Remove .yaml
                        r[resource_name] = data
                    except Exception:
                        logger.exception("Error loading dashboard %s", filename)
        except Exception:
            logger.exception("Error scanning dashboard directory %s", dir)
        return r

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
                    "id": "layout-1",
                    "name": "Main Layout",
                    "type": "flex-layout",
                    "config": {
                        "direction": "column",
                        "gap": "1rem",
                    },
                    "children": [],
                },
                "bindings": [],
            },
        }

    def to_files(
        self, name: str, resource: resource_types.ResourceDictType
    ) -> dict[str, str]:
        """Convert resource to YAML file."""
        name = name.split("/")[-1]  # Get base name only
        return {f"{name}.yaml": yaml.dump(resource, default_flow_style=False)}

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
    def list_resources(
        dashboard_id: str, subfolder: str = ""
    ) -> dict[str, Any]:
        """
        List available file resources in a given subfolder of the board resources dir.
        Returns list of {path, displayName, type, size, modified}.
        """
        module, resource = parseDashboardId(dashboard_id)
        try:
            base_path = modules.filename_for_file_resource(module, resource)
            target_path = (
                os.path.join(base_path, subfolder) if subfolder else base_path
            )

            if not os.path.isdir(target_path):
                os.makedirs(target_path, exist_ok=True)
                return {"resources": [], "error": None}

            resources = []
            for filename in os.listdir(target_path):
                filepath = os.path.join(target_path, filename)
                rel_path = os.path.relpath(filepath, base_path)

                # Skip directories in listing (they're just organization)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    resources.append(
                        {
                            "path": rel_path,
                            "displayName": filename,
                            "type": "file",
                            "mimeType": mimetypes.guess_type(filepath)[0],
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                        }
                    )

            return {
                "resources": sorted(resources, key=lambda x: x["displayName"]),
                "error": None,
            }
        except Exception as e:
            logger.exception("Error listing resources")
            return {"resources": [], "error": str(e)}

    @staticmethod
    def get_builtin_resources() -> dict[str, Any]:
        """
        List URLs and display names of builtin stock resources.
        Returns list of {url, displayName, category}.
        """
        builtins = [
            {
                "url": "/static/dashbeard/css/barrel.css",
                "displayName": "Barrel (Default)",
                "category": "theme",
                "type": "css",
            },
            {
                "url": "/static/dashbeard/css/dark.css",
                "displayName": "Dark Theme",
                "category": "theme",
                "type": "css",
            },
            {
                "url": "/static/dashbeard/css/light.css",
                "displayName": "Light Theme",
                "category": "theme",
                "type": "css",
            },
        ]
        return {"resources": builtins, "error": None}

    @staticmethod
    def upload_file(
        dashboard_id: str, path: str, file_data: bytes
    ) -> dict[str, Any]:
        """Upload a file to the board resources directory."""
        module, resource = parseDashboardId(dashboard_id)
        try:
            # Prevent directory traversal
            if ".." in path or path.startswith("/"):
                return {"success": False, "error": "Invalid path"}

            base_path = modules.filename_for_file_resource(module, resource)
            filepath = os.path.join(base_path, path)

            # Ensure target is within base_path
            if not os.path.normpath(filepath).startswith(
                os.path.normpath(base_path)
            ):
                return {
                    "success": False,
                    "error": "Path outside resource directory",
                }

            # Create parent directories
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # Write file
            with open(filepath, "wb") as f:
                f.write(file_data)

            return {
                "success": True,
                "path": os.path.relpath(filepath, base_path),
                "size": len(file_data),
            }
        except Exception as e:
            logger.exception("Error uploading file")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_file(dashboard_id: str, path: str) -> tuple[bytes, str] | None:
        """Get file binary blob."""
        module, resource = parseDashboardId(dashboard_id)
        try:
            if ".." in path or path.startswith("/"):
                return None

            base_path = modules.filename_for_file_resource(module, resource)
            filepath = os.path.join(base_path, path)

            if not os.path.normpath(filepath).startswith(
                os.path.normpath(base_path)
            ):
                return None

            if not os.path.isfile(filepath):
                return None

            with open(filepath, "rb") as f:
                data = f.read()

            mime_type = (
                mimetypes.guess_type(filepath)[0] or "application/octet-stream"
            )
            return data, mime_type
        except Exception:
            logger.exception("Error reading file")
            return None

    @staticmethod
    def search_files(dashboard_id: str, query: str) -> dict[str, Any]:
        """Search for files by filename in the resource directory."""
        module, resource = parseDashboardId(dashboard_id)
        try:
            base_path = modules.filename_for_file_resource(module, resource)
            results = []
            query_lower = query.lower()

            for root, dirs, files in os.walk(base_path):
                for filename in files:
                    if query_lower in filename.lower():
                        filepath = os.path.join(root, filename)
                        rel_path = os.path.relpath(filepath, base_path)
                        results.append(
                            {
                                "path": rel_path,
                                "displayName": filename,
                                "fullPath": rel_path,
                            }
                        )

            return {"results": results, "error": None}
        except Exception as e:
            logger.exception("Error searching files")
            return {"results": [], "error": str(e)}


# Create Quart Blueprint for API routes
api_bp = Blueprint("dashboard_api", __name__, url_prefix="/api/dashboards")


@api_bp.route("/<boardid>/files/list", methods=["GET"])
async def list_resources_endpoint(boardid: str):
    """List resources in a subfolder."""
    web.require("system_admin")
    subfolder = request.args.get("subfolder", "")
    result = DashboardFilesAPI.list_resources(boardid, subfolder)
    return jsonify(result)


@api_bp.route("/<boardid>/files/upload", methods=["POST"])
async def upload_file_endpoint(boardid: str):
    """Upload a file."""
    web.require("system_admin")
    module, resource = parseDashboardId(boardid)
    path = (await request.form).get("path")
    files = await request.files

    if not path or "file" not in files:
        return jsonify({"success": False, "error": "Missing path or file"}), 400

    file = files["file"]
    file_data = await file.read()
    result = DashboardFilesAPI.upload_file(boardid, path, file_data)
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


@api_bp.route("/<boardid>/files/search", methods=["GET"])
async def search_files_endpoint(boardid: str):
    """Search for files."""
    web.require("system_admin")

    query = request.args.get("q", "")
    result = DashboardFilesAPI.search_files(boardid, query)
    return jsonify(result)


@api_bp.route("/builtin", methods=["GET"])
async def get_builtin_resources_endpoint():
    """Get list of builtin stock resources."""
    web.require("system_admin")
    result = DashboardFilesAPI.get_builtin_resources()
    return jsonify(result)


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

        # Update the resource in Kaithem
        modules.insert_resource(
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


@api_bp.route("/<boardid>/delete", methods=["DELETE"])
async def delete_board_endpoint(boardid: str):
    """Delete a board from Kaithem."""
    web.require("system_admin")
    raise NotImplementedError("You can Delete board like any other resource")


quart_app.register_blueprint(api_bp)
