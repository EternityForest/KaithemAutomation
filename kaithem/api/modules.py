import os

from kaithem.src import modules, modules_state, util
from kaithem.src.modules_state import ResourceDictType


def filename_for_resource(module: str, resource: str) -> str:
    """Given the module and resource, return the actual file for a file resource, or
    file data dir for directory resource"""

    return os.path.join(modules.getModuleDir(module), "__filedata__", resource)


def admin_url_for_file_resource(module: str, resource: str) -> str:
    return f"/modules/module/{util.url(module) }/getfileresource/{resource}"


def get_resource_data(module: str, resource: str) -> ResourceDictType:
    "Get the dict data for a resource"
    return modules_state.ActiveModules[module][resource]


def insert_resource(module: str, resource: str, resourceData: ResourceDictType):
    """
    Create a new resource, if it doesn't already exist,
    and initializing it as appropriate for it's resource type
    """
    if resource in modules_state.ActiveModules[module]:
        raise ValueError(
            f"Resource {resource} already exists in module {module}"
        )

    modules_state.rawInsertResource(module, resource, resourceData)
    modules.handleResourceChange(module, resource, newly_added=True)


def update_resource(module: str, resource: str, resourceData: ResourceDictType):
    """Update an existing resource"""
    if resource not in modules_state.ActiveModules[module]:
        raise ValueError(
            f"Resource {resource} does not exist in module {module}"
        )
    if (
        not get_resource_data(module, resource)["resource_type"]
        == resourceData["resource_type"]
    ):
        raise ValueError(
            f"Resource {resource} in {module} is of type {resourceData['resource_type']}"
        )
    modules_state.rawInsertResource(module, resource, resourceData)
    modules.handleResourceChange(module, resource)


def delete_resource(module: str, resource: str):
    modules.rmResource(module, resource)


def list_resources(module: str) -> list[str]:
    with modules_state.modulesLock:
        return list(modules_state.ActiveModules[module].keys())


def scan_file_resources(module: str):
    """Scan the resources in the filedata folder for the specified module.
    Call if you directly change something, to update the UI.
    """
    modules_state.importFiledataFolderStructure(module)
    modules_state.recalcModuleHashes()
