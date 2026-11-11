# SPDX-License-Identifier: GPL-3.0-or-later
"""Language Server Protocol support for the text editor.

Runs language servers in lspcontainers images via rootless podman.
A fixed dict maps languages to image names.  Containers are named
``lsp-LANG-N`` using the smallest unused number, so the container's
on-disk metadata structures are reused across loads.

Each browser connection that wants LSP gets its own dedicated
``LanguageServer`` (one container per connection).  The plugin's LSP
websocket route pipes raw JSON-RPC messages straight between the browser
and the container's stdio: the browser (via ace-linters) speaks the
protocol and owns the ``initialize`` handshake, so the backend must not
inject or interpret any messages of its own.

The workspace is always mounted at ``/workspace`` inside the container,
so the client addresses files with ``file:///workspace/<path>`` URIs and
no backend path remapping is needed.
"""

import os
import subprocess
import threading

import structlog

from kaithem.api import lifespan
from kaithem.src import podman_util

logger = structlog.get_logger(__name__)

# Language -> lspcontainers image name
LANGUAGE_IMAGES: dict[str, str] = {
    "python": "lspcontainers/pyright-langserver:1.1.377",
    "typescript": "lspcontainers/typescript-language-server:4.3.4",  # noqa: E501
    "javascript": "lspcontainers/typescript-language-server:4.3.4",  # noqa: E501
    "html": "lspcontainers/html-language-server:1.4.0",
}

# Marker files that signal a workspace root, in increasing order of
# preference per level.
MARKER_FILES = [
    "package.json",
    "pyproject.toml",
    "setup.py",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "tsconfig.json",
]

WORKSPACE_MARKER = "lsp-workspace.json"


def detect_workspace(path: str) -> str:
    """Look for marker files in increasingly outer dirs.

    Returns the path of the outermost directory that contains a marker
    file, or the starting directory if no workspace is detected.
    """
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        path = os.path.dirname(path)

    best = path
    cur = path
    while True:
        for marker in MARKER_FILES:
            if os.path.isfile(os.path.join(cur, marker)):
                best = cur
                break
        if os.path.isfile(os.path.join(cur, WORKSPACE_MARKER)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return best


class LanguageServer:
    """One LSP server process for one language, one workspace.

    Communicates over stdio with the container.  Messages are passed
    through transparently: the caller feeds raw JSON-RPC message bodies
    from the browser via ``send_raw`` and receives the server's raw
    JSON-RPC message bodies (without Content-Length framing) via the sink
    callback set with ``set_sink``.  No ``initialize`` is sent here; the
    browser client owns the whole handshake.
    """

    def __init__(self, language: str, workspace_root: str):
        self.language = language
        self.workspace_root = os.path.abspath(workspace_root)
        self.container_name = _find_container_name(language)
        self.lock = threading.RLock()
        self.proc: subprocess.Popen[bytes] | None = None
        self.closed = False
        self._sink = None

        image = LANGUAGE_IMAGES[language]
        # ``run_container`` starts ``podman run --interactive`` and returns the
        # Popen whose stdin/stdout are wired straight to the container's stdio,
        # so the language server's LSP stream is on that pipe.
        self.proc = podman_util.run_container(
            image,
            name=self.container_name,
            bindings={self.workspace_root: "/workspace"},
            workdir="/workspace",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        assert self.proc is not None
        self._reader = threading.Thread(
            target=self._read_loop, daemon=True, name=f"lsp-{language}"
        )
        self._reader.start()

    def set_sink(self, sink) -> None:
        """Set the callback invoked with each raw JSON-RPC body from the server.

        Called from the reader thread.  The sink is expected to be
        thread-safe (e.g. it hops onto the websocket's event loop).
        """
        self._sink = sink

    def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        f = self.proc.stdout
        while not self.closed:
            try:
                # Read headers
                headers = {}
                while True:
                    line = f.readline()
                    if not line:
                        return
                    line = line.decode("utf-8").strip()
                    if not line:
                        break
                    k, _, v = line.partition(":")
                    headers[k.strip().lower()] = v.strip()

                length = int(headers.get("content-length", 0))
                if length <= 0:
                    return
                body = f.read(length)
                if len(body) < length:
                    return
                text = body.decode("utf-8")
            except Exception:
                logger.exception("Error reading LSP message")
                return

            sink = self._sink
            if sink is not None:
                try:
                    sink(text)
                except Exception:
                    logger.exception("Error in LSP message sink")

    def send_raw(self, text: str | bytes) -> None:
        """Send a raw JSON-RPC message body to the server, adding framing."""
        body = text.encode("utf-8") if isinstance(text, str) else text
        with self.lock:
            if self.closed or not self.proc or not self.proc.stdin:
                return
            try:
                self.proc.stdin.write(
                    f"Content-Length: {len(body)}\r\n\r\n".encode() + body
                )
                self.proc.stdin.flush()
            except Exception:
                logger.exception("Error writing LSP message")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        # Removing the container also makes the attached ``podman run``
        # client (self.proc) exit.
        podman_util.stop_container(self.container_name)


def _find_container_name(language: str) -> str:
    """Find the smallest unused number for lsp-LANG-N."""
    prefix = f"lsp-{language}-"
    # ``run_container`` prefixes every container name with CONTAINER_PREFIX,
    # so the name we look for on disk is prefixed too.
    full_prefix = podman_util.CONTAINER_PREFIX + prefix
    try:
        # ``_podman_quick_run`` waits for the process and returns its stdout,
        # which ``_podman_run`` (a bare Popen) would not have collected yet.
        out = podman_util._podman_quick_run(
            "ps", "-a", "--format", "{{.Names}}"
        )
    except Exception:
        return f"{prefix}1"
    used = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(full_prefix):
            try:
                used.add(int(line[len(full_prefix) :]))
            except ValueError:
                pass
    i = 1
    while i in used:
        i += 1
    return f"{prefix}{i}"


# Active language servers, tracked so they can be shut off at exit.
_servers: set[LanguageServer] = set()
_servers_lock = threading.RLock()
# Serialises name allocation and container start so two connections for the
# same language cannot race and pick the same lsp-LANG-N name.
_start_lock = threading.RLock()


def start_language_server(language: str, workspace_root: str) -> LanguageServer:
    """Start a dedicated language server and track it for shutdown."""
    with _start_lock:
        server = LanguageServer(language, workspace_root)
        with _servers_lock:
            _servers.add(server)
    return server


def stop_language_server(server: LanguageServer) -> None:
    """Stop a language server and forget about it."""
    with _servers_lock:
        _servers.discard(server)
    server.close()


def shutdown_all() -> None:
    with _servers_lock:
        servers = list(_servers)
        _servers.clear()
    for server in servers:
        server.close()


def shutdown_all_containers() -> None:
    """Stop all lsp containers at exit."""
    shutdown_all()
    prefix = podman_util.CONTAINER_PREFIX + "lsp-"
    try:
        out = podman_util._podman_quick_run(
            "ps", "-a", "--filter", f"name={prefix}", "--format", "{{.Names}}"
        )
    except Exception:
        return
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            try:
                podman_util._podman_quick_run("rm", "-f", line)
            except Exception:
                pass


lifespan.at_shutdown(shutdown_all_containers)
