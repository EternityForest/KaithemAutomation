# SPDX-License-Identifier: GPL-3.0-or-later
"""Container app resources.

Two resource types work together:

``container_app``
    A project folder holding a ``container-app.toml`` (see
    :mod:`appconfig`).  It owns the code, the optional app, and any
    manually triggered scripts, and can be started in a throwaway dev
    mode whose ``/data`` lives in the vardir sandbox instead of the
    module.

``container_app_instance``
    A running instance of a ``container_app``.  It references the app by
    ``module:resource`` name, owns the persistent data, is started at boot
    and is reachable at ``/apps/<name>`` on the Kaithem host.

Creating a ``container_app`` interactively also creates a matching
``container_app_instance`` named ``<app>_default`` so there is always
somewhere to run the project.  Building is never automatic: a project
that needs a build exposes it as an ordinary script the developer runs
by hand, and a project may have no app at all and only scripts.
"""

from __future__ import annotations

from . import (
    api,  # noqa: E402,F401
    resource_types,  # noqa: E402,F401
)
