import asyncio
import sys
import threading
import time
import traceback

import icemedia.sound_player
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from scullery import messagebus, workers

_shutdown_events: list[asyncio.Event] = []


def add_shutdown_event(event: asyncio.Event):
    _shutdown_events.append(event)


def _print_thread_tracebacks():
    """Print formatted tracebacks of all threads to help debug shutdown hangs."""
    console = Console()

    console.print("\n")
    console.print(
        Panel(
            "[bold red]Shutdown is taking longer than 30 seconds![/bold red]\n"
            "[yellow]Printing thread tracebacks for debugging...[/yellow]",
            title="⚠️  Shutdown Timeout",
            border_style="red",
        )
    )
    console.print("\n")

    frames = sys._current_frames()

    for thread_id, frame in frames.items():
        # Get thread name
        thread_name = None
        is_daemon = False
        for thread in threading.enumerate():
            if thread.ident == thread_id:
                thread_name = thread.name
                is_daemon = thread.daemon
                break

        if is_daemon:
            continue

        if thread_name is None:
            thread_name = f"Unknown (ID: {thread_id})"

        # Format the traceback
        tb_lines = traceback.format_stack(frame)
        tb_text = "".join(tb_lines)

        # Create syntax highlighted traceback
        syntax = Syntax(tb_text, "python", theme="monokai", line_numbers=True)

        console.print(
            Panel(
                syntax,
                title=f"[bold cyan]Thread: {thread_name}[/bold cyan] (ID: {thread_id}) {'(Daemon)' if is_daemon else ''}",
                border_style="cyan",
                expand=False,
            )
        )
        console.print("\n")


def _monitor_shutdown_timeout():
    """Monitor shutdown and print thread tracebacks if it takes too long."""
    time.sleep(30)
    _print_thread_tracebacks()


def shutdown():
    # Start a daemon thread to monitor shutdown timeout
    monitor_thread = threading.Thread(
        target=_monitor_shutdown_timeout,
        daemon=True,
        name="ShutdownTimeoutMonitor",
    )
    monitor_thread.start()

    for event in _shutdown_events:
        event.set()

    threading.Thread(
        target=icemedia.sound_player.stop_all_sounds, daemon=True
    ).start()
    messagebus.post_message(
        "/system/notifications/shutdown", "Recieved SIGINT or SIGTERM."
    )
    messagebus.post_message("/system/shutdown", "Recieved SIGINT or SIGTERM.")
    workers.stop()
