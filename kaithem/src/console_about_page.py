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
    return sys.stdin.isatty() or "PS1" in os.environ


quote = """Amidst the mists and fiercest frosts,
with stoutest wrists and loudest boasts,
He thrusts his fists against the posts,
And still insists he sees the ghosts."""


def do_splash_image(console: Console, width=80):
    from textual_image.renderable import Image

    d = os.path.dirname(os.path.abspath(__file__))
    d = os.path.dirname(d)
    d = os.path.join(d, "data", "static", "img", "16x9", "kaithem-tavern.avif")

    console.print(
        Image(
            d,
            width=width,
            height="auto",
        )
    )


def do_splash_screen(version_only=False):
    try:
        import importlib.metadata

        from rich.panel import Panel

        console = Console()

        w = min(console.width, 90)

        text = Panel(
            "🌊 Kaithem Automation",
            style="bold plum4 on cyan2",
            border_style="none",
        )
        console.print(text)

        pkg_metadata = importlib.metadata.metadata("kaithem")
        meta = []

        include_meta = {
            "name": "App Name",
            "version": "App Version",
            "summary": "App Summary",
            "license_expression": "App License",
        }

        def add_kv(key, value):
            meta.append(f"[bold]{key}:[/bold] {value}\n")

        for key in include_meta:
            if key in pkg_metadata:
                value = pkg_metadata[key]
                add_kv(include_meta[key], value)

        # No seriously private info here
        add_kv("Python", sys.version)
        add_kv("Repo", "https://github.com/EternityForest/KaithemAutomation")

        add_kv("User ID", os.getuid())

        add_kv("Parent PID", os.getppid())
        add_kv("Parent Name", get_process_name_by_pid(os.getppid()))
        add_kv("PID", os.getpid())

        add_kv("Args", " ".join(sys.argv))

        add_kv("OS", sys.platform)
        add_kv("OS Release", platform.freedesktop_os_release()["PRETTY_NAME"])
        add_kv("Machine", platform.machine())
        add_kv("Platform Version", platform.version())
        add_kv("Platform Release", platform.release())
        add_kv("Init System", get_process_name_by_pid(1))

        add_kv("CPU", platform.processor() or "Unknown")

        add_kv("Total RAM", f"{psutil.virtual_memory().total / 1024**3:.2f} GB")
        add_kv("Memory Usage", f"{psutil.virtual_memory().percent}%")
        add_kv(
            "Disk Total",
            f"{psutil.disk_usage(os.path.expanduser('~')).total / 1024**3:.2f} GB",
        )
        add_kv(
            "Disk Free",
            f"{psutil.disk_usage(os.path.expanduser('~')).free / 1024**3:.2f} GB",
        )
        add_kv(
            "Temperature",
            f"{psutil.sensors_temperatures()['coretemp'][0].current:.2f} °C",
        )
        text = Panel("".join(meta), title="System Info", width=w)
        console.print(text)

        meta = []

        # Identifiable user info
        add_kv("Executable", sys.executable)
        add_kv("Network Name", platform.node())
        add_kv("User", os.getlogin())

        text = Panel("".join(meta), title="User Info", width=w)
        console.print(text)

        # Via SSH might be too taxing over bad wifi at 1AM when you need to debug something
        if is_interactive_terminal() and not is_running_via_ssh():
            try:
                do_splash_image(console, width=w - 1)
            except Exception:
                logger.exception("Splash image failed")

        text = Panel(quote, style="italic white", expand=False, width=w)
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
