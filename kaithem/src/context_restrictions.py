from __future__ import annotations

import threading
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar


class ContextError(Exception):
    pass


F = TypeVar("F", bound=Callable[..., Any])


class Context:
    """Context object for applying restrictions to where
    a function can be called.

    If exclusive is True, the context will also serve as a lock
    equivalent to threading.RLock(), only one thread can use it at a time
    and others will block.

    The context does not try to get the lock until after all of it's preconditions
    to open.
    """

    def __init__(self, name: str, exclusive: bool = False):
        self.name = name

        self._lock = threading.RLock() if exclusive else None
        self._local = threading.local()
        self._local.level = 0
        self._local.session = None
        self._opens_before: list[Context] = []
        self._preconditions: list[Callable[[], bool]] = []
        self._postconditions: list[Callable[[], bool]] = []
        self._lock_timeout = -1

    def __repr__(self) -> str:
        return f"<Context {self.name} active={self.active} session={self.session} exclusive={self._lock is not None}>"

    def precondition(self, f: Callable[[], bool]):
        self._preconditions.append(f)

    def postcondition(self, f: Callable[[], bool]):
        self._postconditions.append(f)

    @property
    def active(self):
        return self._local.level > 0

    @property
    def session(self) -> None | str:
        return self._local.session

    def opens_before(self, ctx: Context):
        """Declare that this context cannot be newly opened if ctx is active.
        However the other contexts may still be opened after this is opened.
        """
        self._opens_before.append(ctx)

    def required(self, f: F) -> F:
        """Decorator that causes function to raise a ContextError
        if the context is not already active"""

        @wraps(f)
        def g(*args, **kwargs):
            if not self.active:
                raise ContextError(f"{self.name} must be opened")
            return f(*args, **kwargs)

        return g  # type: ignore

    def excludes(self, f: F) -> F:
        """Decorator that causes function to raise a ContextError
        if the context is already active"""

        @wraps(f)
        def g(*args, **kwargs):
            if self.active:
                raise ContextError(f"{self.name} must be opened")
            return f(*args, **kwargs)

        return g  # type: ignore

    def entry_point(self, f: F) -> F:
        """Decorator that causes function to be considered as
        an entry point for the context.  Equivalent to
        wrapping in with ctx:
        """

        @wraps(f)
        def g(*args, **kwargs):
            with self:
                return f(*args, **kwargs)

        return g  # type: ignore

    def session_entry_point(self, str) -> Callable[[F], F]:
        def deco(f: F) -> F:
            @wraps(f)
            def g(*args, **kwargs):
                if self._local.session and self._local.session != str:
                    raise ContextError(f"{self.name} open in session {str}")
                with self:
                    self._local.session = str
                    return f(*args, **kwargs)

            return g  # type: ignore

        return deco

    def __enter__(self):
        if not self._local.level:
            for i in self._preconditions:
                if not i():
                    raise ContextError(f"{self.name} precondition failed: {i.__name__}")

            for i in self._opens_before:
                if i.active:
                    raise ContextError(f"{self.name} must be opened before {i.name}")

        if self._lock:
            if not self._lock.acquire(True, timeout=self._lock_timeout):
                raise ContextError(f"{self.name} is locked by another thread")

        self._local.level += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._local.level -= 1
        if self._lock:
            self._lock.release()
        if not self._local.level:
            self._local.session = None
            for i in self._postconditions:
                if not i():
                    raise ContextError(f"{self.name} postcondition failed: {i.__name__}")
