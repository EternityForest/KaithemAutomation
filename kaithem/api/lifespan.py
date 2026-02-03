from collections.abc import Callable

from scullery import messagebus

from kaithem.src import shutdown as shutdownapi

_shutdown_handler_refs = []

# True if the system is shutting down
is_shutting_down: bool = False


def shutdown_now():
    """Shut down the system now"""
    shutdownapi.shutdown()


def at_shutdown(f: Callable[[], None]) -> None:
    """Register a function to be called when the system shuts down,
    before atexit would trigger"""

    def f2(*a):
        f()

    _shutdown_handler_refs.append(f2)
    messagebus.subscribe("/system/shutdown", f2)


def _state(*a):
    global is_shutting_down
    is_shutting_down = True


at_shutdown(_state)
