from __future__ import annotations

import threading
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar


# Used to track if we are in a bottom level context that blocks everything else.
class _BottomLocal(threading.local):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.level = 0


_bottom = _BottomLocal()


class ContextError(Exception):
    pass


F = TypeVar("F", bound=Callable[..., Any])


class _Local(threading.local):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.level = 0
        self.session = None


class Context:
    """Context object for applying restrictions to where
    a function can be called.

    If exclusive is True, the context will also serve as a lock
    equivalent to threading.RLock(), only one thread can use it at a time
    and others will block.

    The context does not try to get the lock until after all of it's preconditions
    to open.
    """

    def __init__(
        self,
        name: str,
        exclusive: bool = False,
        bottom_level: bool = False,
        timeout=-1,
    ):
        self.name = name

        self._lock = threading.RLock() if exclusive else None
        self._local = _Local()
        self._opens_before: list[Context] = []
        self._preconditions: list[Callable[[], bool]] = []
        self._postconditions: list[Callable[[], bool]] = []
        self._lock_timeout = timeout
        self._is_bottom_level = bottom_level

    def __repr__(self):
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
        def requires_wrapper(*args, **kwargs):
            if not self.active:
                raise ContextError(f"{self.name} must be opened")
            return f(*args, **kwargs)

        return requires_wrapper  # type: ignore

    def excludes(self, f: F) -> F:
        """Decorator that causes function to raise a ContextError
        if the context is already active"""

        @wraps(f)
        def excludes_wrapper(*args, **kwargs):
            if self.active:
                raise ContextError(f"{self.name} must be opened")
            return f(*args, **kwargs)

        return excludes_wrapper  # type: ignore

    def entry_point(self, f: F) -> F:
        """Decorator that causes function to be considered as
        an entry point for the context.  Equivalent to
        wrapping in with ctx:
        """

        @wraps(f)
        def entry_point_wrapper(*args, **kwargs):
            if self._local.level > 0:
                return f(*args, **kwargs)
            else:
                with self:
                    return f(*args, **kwargs)

        return entry_point_wrapper  # type: ignore

    def session_entry_point(self, str) -> Callable[[F], F]:
        """Use as @session_entry_point(sessionname)
        Declares the function as an entry point with a specific session.
        The session remains active until the context is closed,
        and no other session in this context can be opened while this one is active.
        """

        def deco(f: F) -> F:
            @wraps(f)
            def session_entry_point_wrapper(*args, **kwargs):
                if self._local.session and self._local.session != str:
                    raise ContextError(
                        f"{self.name} open in session {self._local.session}"
                    )
                if self._local.level > 0:
                    return f(*args, **kwargs)
                else:
                    with self:
                        self._local.session = str
                        return f(*args, **kwargs)

            return session_entry_point_wrapper  # type: ignore

        return deco

    def session_required(self, str) -> Callable[[F], F]:
        """Use as @session_required(sessionname). Raises error unless the context
        is open with the given session ID.
        """

        def deco(f: F) -> F:
            @wraps(f)
            def session_required_wrapper(*args, **kwargs):
                if self._local.session != str:
                    raise ContextError(
                        f"{self.name} open in session {self._local.session}"
                    )

                return f(*args, **kwargs)

            return session_required_wrapper  # type: ignore

        return deco

    def object_session_entry_point(self, f: F) -> F:
        """Decorator you use on methods.  Will open a new session with the same ID as
        the object, and forbid opening a new session on a different object until the context
        is closed.

        Used when you have a set of objects and you want to enforce that they do not
        call methods of each other.
        """

        @wraps(f)
        def object_session_entry_point_wrapper(obj, *args, **kwargs):
            s = id(obj)
            if self._local.session and self._local.session != s:
                raise ContextError(
                    f"{self.name} open in session {self._local.session}"
                )
            if self._local.level > 0:
                return f(obj, *args, **kwargs)
            else:
                with self:
                    return f(obj, *args, **kwargs)

        return object_session_entry_point_wrapper  # type: ignore

    def object_session_required(self, f: F) -> F:
        """Decorator you use on methods.  Raises error unless the context
        is open with the same session ID as the object ID.
        """

        @wraps(f)
        def object_session_required_wrapper(obj, *args, **kwargs):
            s = id(obj)
            if self._local.session != s:
                raise ContextError(
                    f"{self.name} open in session {self._local.session}"
                )
            return f(obj, *args, **kwargs)

        return object_session_required_wrapper  # type: ignore

    def __enter__(self):
        if not self._local.level:
            if _bottom.level:
                raise ContextError(
                    "Cannot open a new context while already in a bottom-level context"
                )

            for i in self._preconditions:
                if not i():
                    raise ContextError(
                        f"{self.name} precondition failed: {i.__name__}"
                    )

            for i in self._opens_before:
                if i.active:
                    raise ContextError(
                        f"{self.name} must be opened before {i.name} if both are used"
                    )

        if self._lock:
            if not self._lock.acquire(True, timeout=self._lock_timeout):
                raise ContextError(f"{self.name} is locked by another thread")

        self._local.level += 1
        if self._is_bottom_level:
            _bottom.level += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._local.level -= 1

        if self._is_bottom_level:
            _bottom.level -= 1

        if self._lock:
            self._lock.release()
        if not self._local.level:
            self._local.session = None
            for i in self._postconditions:
                if not i():
                    raise ContextError(
                        f"{self.name} postcondition failed: {i.__name__}"
                    )
