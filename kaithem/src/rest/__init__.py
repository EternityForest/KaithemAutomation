# SPDX-License-Identifier: GPL-3.0-or-later

"""Stable public HTTP APIs.

Everything defined under this package is part of Kaithem's documented,
stable API surface.  Importing the package registers every endpoint,
and it is imported once during startup.

New endpoints belong in their own submodule here, imported below so
they are always available.  Each endpoint should be described, with
its parameters and assertions, in the Bruno collection under
``rest/bruno``.
"""

from . import theming  # noqa: F401
