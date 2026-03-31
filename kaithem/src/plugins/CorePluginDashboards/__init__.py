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
    def get_file(dashboard_id: str, path: str):
        module, resource = parseDashboardId(dashboard_id)

        base_path = modules.filename_for_file_resource(module, resource + ".d")

        target_path = os.path.join(base_path, path)

        with open(target_path) as f:
            return f.read()

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
            base_path = modules.filename_for_file_resource(
                module, resource + ".d"
            )

            target_path = (
                os.path.join(base_path, subfolder) if subfolder else base_path
            )

            resources = []
            for filename in os.listdir(target_path):
                filepath = os.path.join(target_path, filename)

                # Skip directories in listing (they're just organization)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    resources.append(
                        {
                            "url": f"{dashboard_id}/files/get{filepath}",
                            "size": stat.st_size,
                            "name": os.path.basename(filepath),
                            "type": "file",
                        }
                    )

            return {
                "resources": sorted(resources, key=lambda x: x["displayName"]),
                "error": None,
            }
        except Exception as e:
            logger.exception("Error listing resources")
            return {"resources": [], "error": str(e)}


# Create Quart Blueprint for API routes
api_bp = Blueprint("dashboard_api", __name__, url_prefix="/api/dashboards")


@api_bp.route("/<boardid>/files/list", methods=["GET"])
async def list_resources_endpoint(boardid: str):
    """List resources in a subfolder."""
    web.require("system_admin")
    subfolder = request.args.get("subfolder", "")
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


quart_app.register_blueprint(api_bp)
