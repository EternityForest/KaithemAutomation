# kaithem.api.modules

## Attributes

| [`modules_lock`](#kaithem.api.modules.modules_lock)                   |    |
|-----------------------------------------------------------------------|----|
| [`mutable_copy_resource`](#kaithem.api.modules.mutable_copy_resource) |    |

## Classes

| [`FileResourceInfo`](#kaithem.api.modules.FileResourceInfo)   |    |
|---------------------------------------------------------------|----|

## Functions

| [`set_resource_error`](#kaithem.api.modules.set_resource_error)(module, resource, error)                        | Set an error notice for a resource.  Cleared when the resource is moved,   |
|-----------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| [`filename_for_file_resource`](#kaithem.api.modules.filename_for_file_resource)(→ str)                          | Given the module and resource for a file, return                           |
| [`filename_for_resource`](#kaithem.api.modules.filename_for_resource)(→ str)                                    | DEPRECATED: use filename_for_file_resource instead                         |
| [`admin_url_for_file_resource`](#kaithem.api.modules.admin_url_for_file_resource)(→ str)                        |                                                                            |
| [`scan_file_resources`](#kaithem.api.modules.scan_file_resources)(module)                                       | Scan the resources in the filedata folder for the specified module.        |
| [`get_resource_data`](#kaithem.api.modules.get_resource_data)(→ dict[str, Any])                                 | Get the dict data for a resource.                                          |
| [`insert_resource`](#kaithem.api.modules.insert_resource)(module, resource, resourceData)                       | Create a new resource, if it doesn't already exist,                        |
| [`update_resource`](#kaithem.api.modules.update_resource)(module, resource, resourceData)                       | Update an existing resource, triggering any relevant                       |
| [`delete_resource`](#kaithem.api.modules.delete_resource)(module, resource)                                     | Delete a resource, triggering                                              |
| [`list_resources`](#kaithem.api.modules.list_resources)(→ list[str])                                            | List the resources in a module.                                            |
| [`list_file_resources_by_prefix`](#kaithem.api.modules.list_file_resources_by_prefix)(→ list[FileResourceInfo]) | List the file resources in all modules combined,                           |
| [`resolve_file_resource`](#kaithem.api.modules.resolve_file_resource)(→ str | None)                             | Given a name of a file resource or a folder in the file resources,         |
| [`save_resource`](#kaithem.api.modules.save_resource)(module, resource, resourceData)                           | Save a resource without triggering any other events.                       |

## Module Contents

### kaithem.api.modules.modules_lock

### kaithem.api.modules.mutable_copy_resource

### kaithem.api.modules.set_resource_error(module: [str](../../src/pages/index.md#kaithem.src.pages.str), resource: [str](../../src/pages/index.md#kaithem.src.pages.str), error: [str](../../src/pages/index.md#kaithem.src.pages.str) | None)

Set an error notice for a resource.  Cleared when the resource is moved,
updated or deleted,
or by setting the error to None.

### kaithem.api.modules.filename_for_file_resource(module: [str](../../src/pages/index.md#kaithem.src.pages.str), resource: [str](../../src/pages/index.md#kaithem.src.pages.str)) → [str](../../src/pages/index.md#kaithem.src.pages.str)

Given the module and resource for a file, return
: the actual file for a file resource, or

file data dir for directory resource

### kaithem.api.modules.filename_for_resource(module: [str](../../src/pages/index.md#kaithem.src.pages.str), resource: [str](../../src/pages/index.md#kaithem.src.pages.str)) → [str](../../src/pages/index.md#kaithem.src.pages.str)

DEPRECATED: use filename_for_file_resource instead

### kaithem.api.modules.admin_url_for_file_resource(module: [str](../../src/pages/index.md#kaithem.src.pages.str), resource: [str](../../src/pages/index.md#kaithem.src.pages.str)) → [str](../../src/pages/index.md#kaithem.src.pages.str)

### kaithem.api.modules.scan_file_resources(module: [str](../../src/pages/index.md#kaithem.src.pages.str))

Scan the resources in the filedata folder for the specified module.
Call if you directly change something, to update the UI.  May not
take effect immediately

### kaithem.api.modules.get_resource_data(module: [str](../../src/pages/index.md#kaithem.src.pages.str), resource: [str](../../src/pages/index.md#kaithem.src.pages.str)) → dict[[str](../../src/pages/index.md#kaithem.src.pages.str), Any]

Get the dict data for a resource.
May only be called under the modules_lock.

### kaithem.api.modules.insert_resource(module: [str](../../src/pages/index.md#kaithem.src.pages.str), resource: [str](../../src/pages/index.md#kaithem.src.pages.str), resourceData: kaithem.src.modules_state.ResourceDictType)

Create a new resource, if it doesn’t already exist,
and initializing it as appropriate for it’s resource type
May only be called under the modules_lock.

### kaithem.api.modules.update_resource(module: [str](../../src/pages/index.md#kaithem.src.pages.str), resource: [str](../../src/pages/index.md#kaithem.src.pages.str), resourceData: kaithem.src.modules_state.ResourceDictType)

Update an existing resource, triggering any relevant
: effects for that resource type.

May only be called under the modules_lock.

### kaithem.api.modules.delete_resource(module: [str](../../src/pages/index.md#kaithem.src.pages.str), resource: [str](../../src/pages/index.md#kaithem.src.pages.str))

Delete a resource, triggering
any relevant effects for that resource type.
May only be called under the modules_lock.

### kaithem.api.modules.list_resources(module: [str](../../src/pages/index.md#kaithem.src.pages.str)) → [list](../../src/pages/index.md#kaithem.src.pages.list)[[str](../../src/pages/index.md#kaithem.src.pages.str)]

List the resources in a module.
May only be called under the modules_lock.

### *class* kaithem.api.modules.FileResourceInfo(module: [str](../../src/pages/index.md#kaithem.src.pages.str), name: [str](../../src/pages/index.md#kaithem.src.pages.str), abs_path: [str](../../src/pages/index.md#kaithem.src.pages.str))

#### module

Name as would be passed to resolve_file_resource

#### name

Absolute path to the file

#### abs_path

#### modified

#### size

### kaithem.api.modules.list_file_resources_by_prefix(prefix: [str](../../src/pages/index.md#kaithem.src.pages.str)) → [list](../../src/pages/index.md#kaithem.src.pages.list)[[FileResourceInfo](#kaithem.api.modules.FileResourceInfo)]

List the file resources in all modules combined,
only including ones with a specified relative folder.

You could use this to list all fonts with public_resources/fonts/,

The return value is a list of FileResourceInfo objects
with module, name and absolute path.

### kaithem.api.modules.resolve_file_resource(relative_path: [str](../../src/pages/index.md#kaithem.src.pages.str)) → [str](../../src/pages/index.md#kaithem.src.pages.str) | None

Given a name of a file resource or a folder in the file resources,
return the full path to it, if it can be found in any module.

May only be called under the modules_lock.

### kaithem.api.modules.save_resource(module: [str](../../src/pages/index.md#kaithem.src.pages.str), resource: [str](../../src/pages/index.md#kaithem.src.pages.str), resourceData: kaithem.src.modules_state.ResourceDictType)

Save a resource without triggering any other events.
Use this in your flush_unsaved handler.
May only be called under the modules_lock.
