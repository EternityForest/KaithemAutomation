# SPDX-License-Identifier: GPL-3.0-or-later
"""Public API for exposing backends on Kaithem subdomains.

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
"""

from kaithem.src.plugins.CorePluginProxies.proxy import Proxy

__all__ = ["Proxy"]
