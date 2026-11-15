# SPDX-License-Identifier: GPL-3.0-or-later
"""Append only LDJSON storage for conversation threads.

A conversation is shared between users, but each user gets their own
threads.  Every thread is one file with one JSON object per line, under
``<conversations dir>/<id>/<user>/<slug>.ldjson``.  Malformed lines are
ignored when reading, so a partial write or a hand edit can never break a
conversation.

The conversation level config lives at
``<conversations dir>/<id>/conversation.json``, deliberately outside any
user folder because the id, model and permissions are shared.

When a conversation is not persistent the same interface is served from
memory, so the rest of the code never has to branch on persistence.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
import uuid

import structlog
from scullery import persist

from .models import (
    DEFAULT_USER,
    ChatEntry,
    Entry,
    ThreadHeader,
    ThreadInfo,
    dump_entry,
    parse_entry,
)

logger = structlog.get_logger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MAX_SLUG = 60
_SUFFIX = ".ldjson"
_CONFIG_FILE = "conversation.json"
_FORBIDDEN_IN_NAME = ("/", "\\", "\x00")


def slugify(text: str) -> str:
    """Turn a human title into a filesystem safe thread slug."""
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug[:_MAX_SLUG] or "thread"


def _safe_slug(slug: str) -> str:
    """Reject any slug that could escape the conversation directory."""
    if not slug or slug in (".", ".."):
        raise ValueError(f"Invalid thread slug {slug!r}")
    if any(char in slug for char in _FORBIDDEN_IN_NAME):
        raise ValueError(f"Invalid thread slug {slug!r}")
    return slug


def _safe_user(user: str) -> str:
    """Reject any user name that could escape the conversation directory."""
    if not user or user in (".", ".."):
        raise ValueError(f"Invalid conversation user {user!r}")
    if any(char in user for char in _FORBIDDEN_IN_NAME):
        raise ValueError(f"Invalid conversation user {user!r}")
    return user


class ConversationStorage:
    """Storage for every thread belonging to one conversation and user."""

    def __init__(
        self,
        base_dir: str | None,
        conversation_id: str,
        user: str = DEFAULT_USER,
    ):
        self.conversation_id = conversation_id
        self.user = _safe_user(user)
        self.base_dir = base_dir
        self._memory: dict[str, list[Entry]] = {}
        # Reentrant so create_thread -> list_threads -> read can nest.
        self._lock = threading.RLock()

    @property
    def persistent(self) -> bool:
        return self.base_dir is not None

    @property
    def directory(self) -> str | None:
        if self.base_dir is None:
            return None
        return os.path.join(self.base_dir, self.conversation_id, self.user)

    def _path(self, slug: str) -> str:
        directory = self.directory
        assert directory is not None
        return os.path.join(directory, _safe_slug(slug) + _SUFFIX)

    def _ensure_dir(self) -> None:
        directory = self.directory
        assert directory is not None
        os.makedirs(directory, mode=0o700, exist_ok=True)

    # -- thread lifecycle -------------------------------------------------

    def create_thread(self, title: str) -> ThreadInfo:
        """Create a new thread, returning its summary.

        The slug is derived from the title and made unique by appending
        a numeric suffix.  A header line records the title.
        """
        title = title.strip() or "Thread"
        with self._lock:
            existing = {info.slug for info in self.list_threads()}
            slug = slugify(title)
            candidate, index = slug, 2
            while candidate in existing:
                candidate = f"{slug}-{index}"
                index += 1
            header = ThreadHeader(
                id=uuid.uuid4().hex,
                timestamp=time.time(),
                slug=candidate,
                title=title,
            )
            self._append_locked(candidate, header)
        return ThreadInfo(
            slug=candidate,
            title=title,
            message_count=0,
            updated=header.timestamp,
        )

    def delete_thread(self, slug: str) -> None:
        with self._lock:
            if not self.persistent:
                self._memory.pop(slug, None)
                return
            path = self._path(slug)
            if os.path.exists(path):
                os.remove(path)

    def has_thread(self, slug: str) -> bool:
        with self._lock:
            if not self.persistent:
                return slug in self._memory
            return os.path.exists(self._path(slug))

    # -- entries ----------------------------------------------------------

    def append(self, slug: str, entry: Entry) -> None:
        """Append one entry to a thread."""
        with self._lock:
            self._append_locked(slug, entry)

    def _append_locked(self, slug: str, entry: Entry) -> None:
        if not self.persistent:
            self._memory.setdefault(slug, []).append(entry)
            return

        self._ensure_dir()
        line = dump_entry(entry)
        # A single write of a short line to an O_APPEND descriptor is
        # effectively atomic, so a crash cannot interleave two records.
        fd = os.open(
            self._path(slug),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)

    def read(self, slug: str) -> list[Entry]:
        """Read all entries of a thread, skipping malformed lines."""
        with self._lock:
            if not self.persistent:
                return list(self._memory.get(slug, []))
            path = self._path(slug)
            if not os.path.exists(path):
                raise KeyError(f"Unknown thread {slug!r}")
            entries: list[Entry] = []
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    entry = parse_entry(line)
                    if entry is not None:
                        entries.append(entry)
            return entries

    # -- listing ----------------------------------------------------------

    def list_threads(self) -> list[ThreadInfo]:
        """Summaries of every thread, oldest first."""
        if not self.persistent:
            infos = [
                self._summarize(slug, entries)
                for slug, entries in self._memory.items()
            ]
        else:
            directory = self.directory
            infos = []
            if directory and os.path.isdir(directory):
                for name in sorted(os.listdir(directory)):
                    if not name.endswith(_SUFFIX):
                        continue
                    slug = name[: -len(_SUFFIX)]
                    try:
                        infos.append(self._summarize(slug, self.read(slug)))
                    except KeyError:
                        continue
        infos.sort(key=lambda info: info.updated)
        return infos

    def _summarize(self, slug: str, entries: list[Entry]) -> ThreadInfo:
        title = slug
        count = 0
        updated = 0.0
        for entry in entries:
            updated = max(updated, entry.timestamp)
            if isinstance(entry, ThreadHeader):
                title = entry.title or slug
            elif isinstance(entry, ChatEntry):
                count += 1
        return ThreadInfo(
            slug=slug,
            title=title,
            message_count=count,
            updated=updated,
        )

    # -- whole user -------------------------------------------------------

    def delete(self) -> None:
        """Delete every thread this user has.  Irreversible."""
        with self._lock:
            self._memory.clear()
            directory = self.directory
            if directory and os.path.isdir(directory):
                shutil.rmtree(directory, ignore_errors=True)


def conversation_dir(base_dir: str, conversation_id: str) -> str:
    """The directory holding one conversation's config and user folders."""
    return os.path.join(base_dir, conversation_id)


def write_conversation_config(
    base_dir: str, conversation_id: str, data: dict
) -> None:
    """Persist the conversation config, shared by every user."""
    directory = conversation_dir(base_dir, conversation_id)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    persist.save(data, os.path.join(directory, _CONFIG_FILE))


def load_conversation_config(
    base_dir: str, conversation_id: str
) -> dict | None:
    """Read a persisted conversation config, if there is one."""
    directory = conversation_dir(base_dir, conversation_id)
    path = os.path.join(directory, _CONFIG_FILE)
    if not os.path.exists(path):
        return None
    try:
        data = persist.load(path)
    except Exception:
        logger.exception("Could not read conversation config %s", path)
        return None
    if isinstance(data, dict):
        return data
    return None


def delete_conversation_dir(base_dir: str, conversation_id: str) -> None:
    """Delete a conversation's config and the history of every user."""
    directory = conversation_dir(base_dir, conversation_id)
    if os.path.isdir(directory):
        shutil.rmtree(directory, ignore_errors=True)
