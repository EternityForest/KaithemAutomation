"""Add support for discovering mDNS services."""
from typing import List  # noqa: F401

import zeroconf


class MDNS:
    """Base class to discover mDNS services."""

    def __init__(self):
        """Initialize the discovery."""
        self.zeroconf = None
        self.services = []  # type: List[zeroconf.ServiceInfo]
        self._browsers = []  # type: List[zeroconf.ServiceBrowser]

    def register_service(self, service):
        """Register a mDNS service."""
        self.services.append(service)

    def start(self):
        """Start discovery."""
        try:
            self.zeroconf = zeroconf.Zeroconf()

            for service in self.services:
                self._browsers.append(zeroconf.ServiceBrowser(
                    self.zeroconf, service.typ, service))
        except Exception:  # pylint: disable=broad-except
            self.stop()
            raise

    def stop(self):
        """Stop discovering."""
        while self._browsers:
            self._browsers.pop().cancel()

        for service in self.services:
            service.reset()

        if self.zeroconf:
            self.zeroconf.close()
            self.zeroconf = None

    @property
    def entries(self):
        """Return all entries in the cache."""
        return self.zeroconf.cache.entries()
