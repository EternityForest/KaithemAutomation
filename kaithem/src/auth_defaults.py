# SPDX-License-Identifier: GPL-3.0-or-later

# ruff: noqa: E501

"""These are the "built in" permissions required to control basic functions
User code can add to these"""

BasePermissions: dict[str, str] = {
    "system_admin": "The main admin permission. Implies that the user can do anything the base account running the server can.",
    "view_admin_info": "Allows read but not write access to most of the system state",
    "view_status": "View the main page of the application, the active alerts, the about box, and other basic overview info",
    "enumerate_endpoints": "Required for any action that reveals whether something like a page or tagpoint exists.",
    "acknowledge_alerts": "Required to acknowledge alerts",
    "view_devices": "The default permission used to expose device points for reading, but devices can be configured to use others.",
    "write_devices": "The default permission used to expose device points for writing, but devices can be configured to use others.",
    "own_account_settings": "Edit ones own account preferences",
    "chandler_operator": "Access the Chandler console, jump to cues, change input fields.  Does not allow editing settings or groups.",
    "__guest__": "Everyone always has this permission even when not logged in",
    "__all_permissions__": "Special universal permission that grants all permissions in the system. Use with care.",
    "__never__": "Even admin cannot do this.",
}

default_data = {
    "groups": {
        "Administrators": {"permissions": ["__all_permissions__"]},
        "Guests": {
            "permissions": [
                "view_admin_info",
                "view_admin_info",
                "view_status",
                "enumerate_endpoints",
            ]
        },
    },
    "users": {
        "__guest__": {
            "groups": ["Guests"],
            "password": "V+hZrbd22NjvNwvQAfwOAzLrudfX/+SMuddMmetm0Vk=",  # pragma: allowlist secret
            "salt": "AtTjOSUQyNFoklVv+i8Lbw==",  # pragma: allowlist secret
            "settings": {"restrict-lan": False},
            "username": "__guest__",
        }
    },
}
