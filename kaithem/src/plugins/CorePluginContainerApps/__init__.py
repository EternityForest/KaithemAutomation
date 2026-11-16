# SPDX-License-Identifier: GPL-3.0-or-later
"""Container app resources.

Two resource types work together:

``container_app``
    A project folder holding a ``container-app.toml`` (see
    :mod:`appconfig`).  It owns the code and the build, and can be started
    in a throwaway dev mode whose ``/data`` lives in the vardir sandbox
    instead of the module.

``container_app_instance``
    A running instance of a ``container_app``.  It references the app by
    ``module:resource`` name, owns the persistent data, is started at boot
    and is reachable at ``/apps/<name>`` on the Kaithem host.

Creating a ``container_app`` interactively also creates a matching
``container_app_instance`` named ``<app>_default`` so there is always
something to start as soon as the project is built.  Building an app stops
every instance, rebuilds, and starts the instances that were running
before, so a rebuild never serves a half written build.
"""

from __future__ import annotations

from . import (
    api,  # noqa: E402,F401
    resource_types,  # noqa: E402,F401
)
