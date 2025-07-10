from typing import Any

from kaithem.src import auth


def list_all_permissions() -> dict[str, dict[str, Any]]:
    """Return a dict of all permissions.
    They will all have a description item

    """
    d: dict[str, dict[str, Any]] = {}
    for i in auth.Permissions:
        x = {}
        x["description"] = auth.Permissions[i].get("description", "")
        d[i] = x

    return d
