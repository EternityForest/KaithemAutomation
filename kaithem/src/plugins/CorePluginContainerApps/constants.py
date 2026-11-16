# SPDX-License-Identifier: GPL-3.0-or-later
"""Names and defaults shared by the container app resources and API.

Kept in a leaf module so both :mod:`__init__` and :mod:`api` can use them
without importing each other.
"""

from typing import Final

#: Resource type that owns project code and the build.
APP_RESOURCE_TYPE: Final = "container_app"

#: Resource type that runs a project.
INSTANCE_RESOURCE_TYPE: Final = "container_app_instance"

#: Permissions required to reach an app unless the app overrides them.
DEFAULT_PERMISSIONS: Final[list[str]] = ["view_status"]

#: Instances must be loadable after the apps they reference, so apps use a
#: lower priority and therefore load first.
APP_PRIORITY: Final = 40
INSTANCE_PRIORITY: Final = 60

#: Suffix appended to an app's name for its dev mode preview path.
DEV_PATH_SUFFIX: Final = "-dev"
