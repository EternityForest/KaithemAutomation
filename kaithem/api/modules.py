import os
from typing import Any

from scullery import workers

from kaithem.src import modules, modules_state, util
from kaithem.src.modules_state import ResourceDictType

# This lock can be used to synchronize access to modules
# Be extremely careful what you do with it!
# It is meant to be the top-level lock, so you must acquire this
# before getting any other locks that you plan to get.
# Because of this, it also serves as a de facto GIL in some places

# Almost every function in this file will raise an
# exception if this lock is not held.
modules_lock = modules_state.modulesLock


def set_resource_error(module: str, resource: str, error: str | None):
    """
    Set an error notice for a resource.  Cleared when the resource is moved, updated or deleted,
    or by setting the error to None.
    """
    modules_state.set_resource_error(module, resource, error)


def filename_for_file_resource(module: str, resource: str) -> str:
    """Given the module and resource for a file, return the actual file for a file resource, or
    file data dir for directory resource"""

    return modules_state.filename_for_file_resource(module, resource)


def filename_for_resource(module: str, resource: str) -> str:
    """DEPRECATED: use filename_for_file_resource instead"""
    return filename_for_file_resource(module, resource)


def admin_url_for_file_resource(module: str, resource: str) -> str:
    return f"/modules/module/{util.url(module) }/getfileresource/{resource}"


def scan_file_resources(module: str):
    """Scan the resources in the filedata folder for the specified module.
    Call if you directly change something, to update the UI.  May not
    take effect immediately
    """

    def f():
        modules_state.importFiledataFolderStructure(module)
        modules_state.recalcModuleHashes()

    workers.do(f)


@modules_state.modulesLock.required
def get_resource_data(module: str, resource: str) -> dict[str, Any]:
    "Get the dict data for a resource. May only be called under the modules_lock."
    d = modules_state.ActiveModules[module][resource]
    return modules_state.mutable_copy_resource(d)


@modules_lock.required
def insert_resource(module: str, resource: str, resourceData: ResourceDictType):
    """
    Create a new resource, if it doesn't already exist,
    and initializing it as appropriate for it's resource type
    May only be called under the modules_lock.
    """
    if resource in modules_state.ActiveModules[module]:
        raise ValueError(
            f"Resource {resource} already exists in module {module}"
        )

    with modules_state.modulesLock:
        modules_state.rawInsertResource(module, resource, resourceData)
        modules.handleResourceChange(module, resource, newly_added=True)


@modules_lock.required
def update_resource(module: str, resource: str, resourceData: ResourceDictType):
    """Update an existing resource, triggering any relevant effects for that resource type.
    May only be called under the modules_lock."""

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


@modules_lock.required
def delete_resource(module: str, resource: str):
    """Delete a resource, triggering any relevant effects for that resource type.
    May only be called under the modules_lock.
    """
    modules.rmResource(module, resource)


@modules_lock.required
def list_resources(module: str) -> list[str]:
    """List the resources in a module.
    May only be called under the modules_lock."""
    return list(modules_state.ActiveModules[module].keys())


@modules_lock.required
def resolve_file_resource(relative_path: str) -> str | None:
    """Given a name of a file resource or a folder in the file resources,
    return the full path to it, if it can be found in any module.

    May only be called under the modules_lock."""
    for i in sorted(list(modules_state.ActiveModules.keys())):
        path = modules_state.filename_for_file_resource(i, relative_path)
        if os.path.exists(path):
            return path


@modules_lock.required
def save_resource(module: str, resource: str, resourceData: ResourceDictType):
    """Save a resource without triggering any other events.
    Use this in your flush_unsaved handler. May only be called under the modules_lock.
    """
    modules_state.rawInsertResource(module, resource, resourceData)
