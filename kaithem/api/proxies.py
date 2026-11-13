# SPDX-License-Identifier: GPL-3.0-or-later
"""Public API for exposing backends through Kaithem.

The implementation lives in the ``CorePluginProxies`` plugin; this module
is the stable import surface for other code::

    from kaithem.api.proxies import Proxy

    proxy = Proxy(
        subdomain="myapp",
        target="http://127.0.0.1:8080",
        permissions=["view_status"],
    )
    ...
    proxy.close()

Two addressing modes are available:

* :class:`Proxy` mounts a backend on its own subdomain, for example
  ``myapp.example.com``.  This is what the ``proxy`` resource type uses.
* :class:`PathProxy` mounts a backend under a path prefix on the Kaithem
  host, for example ``/apps/myapp``.  Paths are forwarded unchanged, so
  the backend has to know its own prefix.
"""

from kaithem.src.plugins.CorePluginProxies.proxy import (
    HeaderInterceptor,
    PathProxy,
    Proxy,
)

__all__ = ["Proxy", "PathProxy", "HeaderInterceptor"]
