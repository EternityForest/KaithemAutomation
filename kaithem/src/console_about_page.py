import logging
import os
import platform
import sys

import psutil
from rich.console import Console


def get_process_name_by_pid(pid):
    try:
        process = psutil.Process(pid)
        return process.name()
    except psutil.NoSuchProcess:
        return f"No process found with PID: {pid}"
    except psutil.AccessDenied:
        return f"Access denied to process with PID: {pid}"


logger = logging.getLogger(__name__)
pil_logger = logging.getLogger("PIL")
pil_logger.setLevel(logging.INFO)

imglogger = logging.getLogger("textual_image")
imglogger.setLevel(logging.ERROR)


def is_running_via_ssh():
    """
    Checks if the current Python script is running within an SSH session.
    """
    return "SSH_CONNECTION" in os.environ or "SSH_CLIENT" in os.environ


def is_interactive_terminal():
    """Checks if the script is running in an interactive terminal."""
    return sys.stdin.isatty() and os.isatty(sys.stdout.fileno())


quote = """Amidst the mists and fiercest frosts,
with stoutest wrists and loudest boasts,
He thrusts his fists against the posts,
And still insists he sees the ghosts."""


def do_splash_screen(version_only=False):
    try:
        import importlib.metadata

        from rich.panel import Panel
        from textual_image.renderable import Image

        console = Console()

        text = Panel(
            "Kaithem Automation",
            style="bold plum4 on cyan2",
            border_style="dark_cyan",
        )
        console.print(text)

        d = os.path.dirname(os.path.abspath(__file__))
        d = os.path.dirname(d)
        d = os.path.join(
            d, "data", "static", "img", "16x9", "kaithem-tavern.avif"
        )

        pkg_metadata = importlib.metadata.metadata("kaithem")
        meta = []

        include_meta = ["name", "version", "summary", "license_expression"]

        def add_kv(key, value):
            meta.append(f"[bold]{key}:[/bold] {value}\n")

        for key in include_meta:
            if key in pkg_metadata:
                value = pkg_metadata[key]
                add_kv(key, value)

        # No seriously private info here
        add_kv("Python", sys.version)
        add_kv("OS", sys.platform)
        add_kv("OS Release", platform.freedesktop_os_release()["PRETTY_NAME"])
        add_kv("Machine", platform.machine())
        add_kv("Platform Version", platform.version())
        add_kv("Platform Release", platform.release())
        add_kv("CPU", platform.processor() or "Unknown")
        add_kv("User ID", os.getuid())

        add_kv("Parent PID", os.getppid())
        add_kv("Parent Name", get_process_name_by_pid(os.getppid()))
        add_kv("PID", os.getpid())
        add_kv("Args", " ".join(sys.argv))
        add_kv("Repo", "https://github.com/EternityForest/KaithemAutomation")

        text = Panel("".join(meta))
        console.print(text)

        meta = []

        # Identifiable user info
        add_kv("Executable", sys.executable)
        add_kv("Network Name", platform.node())
        add_kv("User", os.getlogin())

        text = Panel("".join(meta))
        console.print(text)

        # Via SSH might be too taxing over bad wifi at 1AM when you need to debug something
        if is_interactive_terminal() and not is_running_via_ssh():
            console.print(
                Image(
                    d,
                    width=80,
                    height="auto",
                )
            )
        text = Panel(quote, style="italic white", expand=False)
        console.print(text)
        console.print("\n")

        loading = Panel(
            "Loading...",
            style="bold white on plum4",
        )

        if not version_only:
            console.print(loading)
    # Because this is an easter egg or non critical detail,
    # Don't let it crash the server
    except Exception:
        logger.exception("Splash screen failed")
