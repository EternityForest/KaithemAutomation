import os
import threading
import time
from collections.abc import Callable

import icemedia.sound_player
from rich.console import Console
from scullery import messagebus, workers

from .print_thread_tracebacks import print_thread_tracebacks

_shutdown_handlers: list[Callable[[], None]] = []


def add_shutdown_handler(event: Callable[[], None]):
    _shutdown_handlers.append(event)


def _monitor_shutdown_timeout():
    """Monitor shutdown and print thread tracebacks if it takes too long."""
    time.sleep(30)
    print_thread_tracebacks("Shutdown is taking too long.")
    time.sleep(30)
    print_thread_tracebacks("Shutdown took too long.")
    os._exit(1)


def shutdown():
    # Start a daemon thread to monitor shutdown timeout
    monitor_thread = threading.Thread(
        target=_monitor_shutdown_timeout,
        daemon=True,
        name="ShutdownTimeoutMonitor",
    )
    monitor_thread.start()

    for event in _shutdown_handlers:
        try:
            event()
        except Exception:
            console = Console()
            console.print_exception()
            raise

    threading.Thread(
        target=icemedia.sound_player.stop_all_sounds, daemon=True
    ).start()
    messagebus.post_message(
        "/system/notifications/shutdown", "Recieved SIGINT or SIGTERM."
    )
    messagebus.post_message("/system/shutdown", "Recieved SIGINT or SIGTERM.")
    workers.stop()
