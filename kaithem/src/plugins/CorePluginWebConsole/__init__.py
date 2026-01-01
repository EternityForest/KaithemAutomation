# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import fcntl
import logging
import os
import pty
import select
import struct
import termios
import threading

import quart
from quart import websocket

import kaithem.api.apps_page
from kaithem.api.lifespan import at_shutdown
from kaithem.api.web import quart_app, require

logger = logging.getLogger(__name__)


active_loops: dict[int, asyncio.AbstractEventLoop] = {}
active_loops_lock = threading.Lock()


def stop_all_loops():
    with active_loops_lock:
        for loop in active_loops.values():
            loop.stop()
        active_loops.clear()


at_shutdown(stop_all_loops)


async def handle_terminal_websocket():
    """Handle WebSocket connection for terminal emulation."""
    # Require admin permission - this is critical for security
    require("system_admin")

    # Create a pseudo-terminal
    master_fd, slave_fd = pty.openpty()

    # Fork a shell process
    pid = os.fork()

    if pid == 0:
        # Child process - this becomes the shell
        os.close(master_fd)

        # Make the slave PTY the controlling terminal
        os.setsid()
        os.dup2(slave_fd, 0)  # stdin
        os.dup2(slave_fd, 1)  # stdout
        os.dup2(slave_fd, 2)  # stderr
        os.close(slave_fd)

        # Get the user's shell from environment or default to bash
        shell = os.environ.get("SHELL", "/bin/bash")

        # Execute the shell
        os.execvp(shell, [shell])

    # Parent process - handle the WebSocket
    os.close(slave_fd)

    async def read_from_pty():
        """Read from PTY and send to WebSocket."""
        loop = asyncio.get_event_loop()
        with active_loops_lock:
            active_loops[pid] = loop

        try:
            while True:
                # Use select to check if data is available
                readable, _, _ = await loop.run_in_executor(
                    None, select.select, [master_fd], [], [], 0.1
                )

                if readable:
                    try:
                        data = await loop.run_in_executor(
                            None, os.read, master_fd, 1024
                        )
                        if data:
                            await websocket.send(data)
                        else:
                            break
                    except OSError:
                        break
                else:
                    # Small sleep to prevent busy loop
                    await asyncio.sleep(0.01)
        finally:
            with active_loops_lock:
                del active_loops[pid]

    async def write_to_pty():
        """Receive from WebSocket and write to PTY."""
        loop = asyncio.get_event_loop()
        with active_loops_lock:
            active_loops[pid] = loop
        try:
            while True:
                data = await websocket.receive()

                if isinstance(data, str):
                    # Handle resize messages
                    if data.startswith("resize:"):
                        try:
                            _, cols, rows = data.split(":")
                            cols = int(cols)
                            rows = int(rows)

                            # Set the terminal size
                            size = struct.pack("HHHH", rows, cols, 0, 0)
                            await loop.run_in_executor(
                                None,
                                fcntl.ioctl,
                                master_fd,
                                termios.TIOCSWINSZ,
                                size,
                            )
                        except Exception:
                            logger.error(
                                "Error setting terminal size", exc_info=True
                            )
                    else:
                        # Regular string data
                        await loop.run_in_executor(
                            None, os.write, master_fd, data.encode("utf-8")
                        )
                elif isinstance(data, bytes):
                    # Binary data (for clipboard operations, etc.)
                    await loop.run_in_executor(None, os.write, master_fd, data)
        except asyncio.CancelledError:
            pass
        finally:
            with active_loops_lock:
                del active_loops[pid]

    # Run both read and write tasks concurrently
    try:
        await asyncio.gather(read_from_pty(), write_to_pty())
    finally:
        # Clean up
        try:
            os.close(master_fd)
        except OSError:
            pass

        # Kill the shell process
        try:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        except (OSError, ProcessLookupError):
            pass


@quart_app.websocket("/webconsole/terminal")
async def terminal_websocket():
    """WebSocket endpoint for terminal emulation."""
    await handle_terminal_websocket()


@quart_app.route("/webconsole")
async def webconsole_index():
    """Serve the web console terminal UI."""
    require("system_admin")

    # Get the WebSocket URL from query parameter, or default to the built-in terminal
    ws_url = quart.request.args.get("ws", "/webconsole/terminal")

    # Read the HTML template
    template_path = os.path.join(os.path.dirname(__file__), "terminal.html")
    with open(template_path) as f:
        template_content = f.read()

    return await quart.render_template_string(template_content, ws_url=ws_url)


app = kaithem.api.apps_page.App(
    "builtin-terminal",
    title="System Console",
    url="/webconsole",
)

kaithem.api.apps_page.add_app(app)
