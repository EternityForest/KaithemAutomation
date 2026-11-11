# SPDX-License-Identifier: GPL-3.0-or-later
"""``proxy`` resource type for the proxy management framework.

A ``proxy`` resource exposes a backend HTTP server (or Unix domain
socket) on a subdomain of the Kaithem host.  Creating, editing, and
deleting the resource registers and unregisters the proxy through the
public :class:`kaithem.api.proxies.Proxy` API.

The runtime object wraps a live proxy.  If the resource data is invalid
(for example an unusable subdomain) the error is captured and shown on
the module page instead of breaking module loading.
"""

from __future__ import annotations

import html
from typing import Any

from kaithem.api import resource_types
from kaithem.api.proxies import Proxy

#: JSON schema describing the proxy resource's data.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subdomain": {
            "type": "string",
            "title": "Subdomain",
            "description": (
                "A single DNS label, for example 'myapp'.  The backend "
                "is served at '<subdomain>.<kaithem host>'."
            ),
            "pattern": "^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
        },
        "target": {
            "type": "string",
            "title": "Backend target",
            "description": (
                "An http:// or https:// URL, or unix:///path/to.sock."
            ),
            "minLength": 1,
        },
        "title": {
            "type": "string",
            "title": "Title",
            "description": (
                "Shown on the apps page.  Defaults to the subdomain."
            ),
        },
        "permissions": {
            "type": "array",
            "title": "Required permissions",
            "description": (
                "Permissions a user must hold to reach the backend.  "
                "Empty allows any user."
            ),
            "items": {"type": "string"},
        },
    },
    "required": ["subdomain", "target"],
}

#: Default resource data.  Must satisfy ``SCHEMA`` because the framework
#: validates it while registering the type.
DEFAULT: dict[str, Any] = {
    "subdomain": "example",
    "target": "http://127.0.0.1:8080",
    "title": "",
    "permissions": [],
}


class ProxyResource(resource_types.ResourceTypeRuntimeObject):
    """Runtime state for one ``proxy`` resource."""

    def __init__(self, module: str, resource: str, data: dict[str, Any]):
        self.module = module
        self.resource = resource
        self.proxy: Proxy | None = None
        self.error: str | None = None
        try:
            self.proxy = Proxy(
                subdomain=data["subdomain"],
                target=data["target"],
                title=data.get("title") or None,
                permissions=list(data.get("permissions") or []),
                module=module,
                resource=resource,
            )
        except Exception as exc:
            # Bad data should be visible, not fatal to module loading.
            self.error = str(exc)

    def close(self) -> None:
        if self.proxy is not None:
            self.proxy.close()
            self.proxy = None


def _blurb(obj: ProxyResource, module: str, resource: str) -> str:
    if obj.error is not None:
        return (
            f'<div class="error" data-testid="proxy-error-'
            f'{html.escape(resource)}">{html.escape(obj.error)}</div>'
        )
    assert obj.proxy is not None
    url = obj.proxy.apps_page_url()
    return (
        f'<div data-testid="proxy-blurb-{html.escape(resource)}">'
        f"<p><strong>{html.escape(obj.proxy.title)}</strong></p>"
        f"<p>Proxying to <code>{html.escape(obj.proxy.target)}</code></p>"
        f'<a href="{html.escape(url)}" class="btn" '
        f'data-testid="open-proxy">Open</a>'
        f"</div>"
    )


resource_types.resource_type_from_schema(
    resource_type="proxy",
    title="Proxy",
    icon="swap-horizontal",
    schema=SCHEMA,
    runtime_object_cls=ProxyResource,
    default=DEFAULT,
    blurb=_blurb,
)
