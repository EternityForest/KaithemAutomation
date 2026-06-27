import os
import sys
import threading
import traceback

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

_logger = structlog.get_logger(__name__)


def watchdog(evt: threading.Event, fail_msg: str = ""):
    def f():
        if not evt.wait(30):
            print_thread_tracebacks(fail_msg)

        if not evt.wait(30):
            print_thread_tracebacks(fail_msg)
            os._exit(1)

    threading.Thread(
        target=f, daemon=True, name="nostartstoplog.watchdog"
    ).start()


def print_thread_tracebacks(reason: str = ""):
    """Print formatted tracebacks of all threads to
    help debug shutdown hangs."""
    console = Console()

    console.print("\n")
    console.print(
        Panel(
            f"""
            [red]⚠️  {reason}[/red]
            [yellow]Printing thread tracebacks for debugging...[/yellow]""",
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
                title=f"[bold cyan]Thread: {thread_name}[/bold cyan] (ID: {thread_id}) {'(Daemon)' if is_daemon else ''}",  # noqa: E501
                border_style="cyan",
                expand=False,
            )
        )
        console.print("\n")
