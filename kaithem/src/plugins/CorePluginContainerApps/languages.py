# SPDX-License-Identifier: GPL-3.0-or-later
"""Registry of supported container project languages.

Each language is a :class:`~.runtime.ContainerProjectRuntime` subclass that
knows how to build, run, and stop a project of that kind.  The resource
type stores a language name and this module turns it into a runtime.
"""

from __future__ import annotations

from typing import Any

from .node import NodeRuntime
from .runtime import ContainerProjectRuntime

#: Language name to runtime class.  Python slots in here later.
LANGUAGES: dict[str, type[ContainerProjectRuntime]] = {
    "node": NodeRuntime,
}


def language_names() -> list[str]:
    """Return the supported language names, sorted for stable UI order."""
    return sorted(LANGUAGES)


def create_runtime(
    language: str,
    project_folder: str,
    data_dir: str,
    options: dict[str, Any] | None = None,
) -> ContainerProjectRuntime:
    """Build the runtime for ``language``.

    ``options`` are language specific keyword arguments (image names,
    commands, dev port ...).  Unknown keys are rejected so a typo in the
    resource data fails loudly instead of being silently ignored.
    """
    try:
        runtime_cls = LANGUAGES[language]
    except KeyError:
        raise ValueError(f"Unsupported language {language!r}") from None
    return runtime_cls(project_folder, data_dir, **(options or {}))
