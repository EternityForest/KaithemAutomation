import logging
import os
import sys

from rich.console import Console

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


def do_splash_screen():
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
        meta = ""

        include_meta = ["name", "version", "summary", "license_expression"]

        for key in include_meta:
            if key in pkg_metadata:
                value = pkg_metadata[key]
                meta += f"{key}: {value}\n"

        meta += f"Python: {sys.version}\n"
        meta += f"OS: {sys.platform}\n"
        meta += f"User: {os.getlogin()}\n"
        meta += f"PID: {os.getpid()}\n"
        meta += f"Args: {sys.argv}\n"

        text = Panel(meta)
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

        console.print(loading)
    # Because this is an easter egg or non critical detail,
    # Don't let it crash the server
    except Exception:
        logger.exception("Splash screen failed")
