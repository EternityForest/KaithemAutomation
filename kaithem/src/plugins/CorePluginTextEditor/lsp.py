# SPDX-License-Identifier: GPL-3.0-or-later
"""Language Server Protocol support for the text editor.

Runs language servers in lspcontainers images via rootless podman.
A fixed dict maps languages to image names.  Containers are named
``lsp-LANG-N`` using the smallest unused number, so the container's
on-disk metadata structures are reused across loads.

The websocket route in the text editor plugin proxies messages between
the browser editor and the LSP container over stdio.  Paths are remapped
between the host workspace root and the container's /workspace mount.
"""

import json
import os
import subprocess
import threading
from typing import Any

import structlog

from kaithem.api import lifespan
from kaithem.src import podman_util

logger = structlog.get_logger(__name__)

# Language -> lspcontainers image name
LANGUAGE_IMAGES: dict[str, str] = {
    "python": "lspcontainers/lspcontainers:python-lsp",
    "typescript": "lspcontainers/lspcontainers:typescript-language-server",
    "javascript": "lspcontainers/lspcontainers:typescript-language-server",
    "json": "lspcontainers/lspcontainers:json-lsp",
    "css": "lspcontainers/lspcontainers:css-lsp",
    "html": "lspcontainers/lspcontainers:html-lsp",
    "yaml": "lspcontainers/lspcontainers:yaml-lsp",
    "markdown": "lspcontainers/lspcontainers:markdown-lsp",
    "go": "lspcontainers/lspcontainers:go-lsp",
    "rust": "lspcontainers/lspcontainers:rust-analyzer",
    "lua": "lspcontainers/lspcontainers:lua-lsp",
    "bash": "lspcontainers/lspcontainers:bash-lsp",
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


def detect_workspace(path: str) -> str | None:
    """Look for marker files in increasingly outer dirs.

    Returns the path of the outermost directory that contains a marker
    file, or None if no workspace is detected.
    """
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        path = os.path.dirname(path)

    best = None
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


def _language_for_file(path: str) -> str | None:
    """Map a filename to a language key in LANGUAGE_IMAGES, or None."""
    ext = os.path.splitext(path)[1].lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".json": "json",
        ".css": "css",
        ".html": "html",
        ".htm": "html",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
        ".go": "go",
        ".rs": "rust",
        ".lua": "lua",
        ".sh": "bash",
    }.get(ext)


class LSPPeer:
    """One LSP server process for one language, one workspace.

    Communicates over stdio with the container.  The websocket proxy in
    the plugin forwards messages between the browser and this peer.
    """

    def __init__(self, language: str, workspace_root: str):
        self.language = language
        self.workspace_root = os.path.abspath(workspace_root)
        self.container_name = _find_container_name(language)
        self.lock = threading.RLock()
        self.proc: subprocess.Popen[bytes] | None = None
        self.msg_id = 0
        self.pending: dict[int, threading.Event] = {}
        self.results: dict[int, Any] = {}
        self.closed = False
        self.client_count = 0

        image = LANGUAGE_IMAGES[language]
        podman_util.run_container(
            image,
            name=self.container_name,
            bindings={self.workspace_root: "/workspace"},
            workdir="/workspace",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        self.proc = self._attach_stdio()
        self._reader = threading.Thread(
            target=self._read_loop, daemon=True, name=f"lsp-{language}"
        )
        self._reader.start()

        # Initialize the LSP session.
        self._initialize()

    def increment_client_count(self, delta: int) -> None:
        """Increment the number of connected clients for this session."""
        with self.lock:
            self.client_count += delta

    def _attach_stdio(self) -> subprocess.Popen[bytes]:
        # Attach to the container's stdio using podman exec.
        podman = podman_util._podman(
            "exec",
            "--interactive",
            podman_util._container_name(self.container_name),
        )
        proc = subprocess.Popen(
            podman,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        return proc

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
                msg = json.loads(body.decode("utf-8"))

                self._handle_message(msg)
            except Exception:
                logger.exception("Error reading LSP message")
                return

    def _handle_message(self, msg: dict[str, Any]) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            with self.lock:
                ev = self.pending.pop(msg["id"], None)
                if ev:
                    self.results[msg["id"]] = msg
                    ev.set()
            return
        # Notifications and server requests are forwarded to the client
        # via a callback set by the websocket proxy.
        cb = self._on_message
        if cb:
            try:
                cb(msg)
            except Exception:
                logger.exception("Error in LSP message callback")

    _on_message: Any = None

    def _send(self, msg: dict[str, Any]) -> None:
        assert self.proc and self.proc.stdin
        body = json.dumps(msg).encode("utf-8")
        with self.lock:
            self.proc.stdin.write(
                f"Content-Length: {len(body)}\r\n\r\n".encode() + body
            )
            self.proc.stdin.flush()

    def _initialize(self) -> None:
        self.msg_id += 1
        msg_id = self.msg_id
        ev = threading.Event()
        with self.lock:
            self.pending[msg_id] = ev

        self._send(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": "initialize",
                "params": {
                    "processId": None,
                    "rootUri": "file:///workspace",
                    "rootPath": "/workspace",
                    "capabilities": {
                        "textDocument": {
                            "completion": {
                                "completionItem": {
                                    "snippetSupport": True,
                                    "resolveSupport": {
                                        "properties": [
                                            "documentation",
                                            "detail",
                                        ]
                                    },
                                }
                            },
                            "hover": {
                                "contentFormat": ["markdown", "plaintext"]
                            },
                            "signatureHelp": {},
                        }
                    },
                    "workspaceFolders": [
                        {"uri": "file:///workspace", "name": "workspace"}
                    ],
                },
            }
        )

        ev.wait(timeout=30)
        with self.lock:
            self.results.pop(msg_id, None)

        self._send(
            {
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {},
            }
        )

    def _remap_path(self, path: str) -> str:
        """Map a host path to the container's /workspace path."""
        rel = os.path.relpath(path, self.workspace_root)
        return "file:///workspace/" + rel.replace(os.sep, "/")

    def _unmap_path(self, uri: str) -> str:
        """Map a container path back to the host workspace."""
        if uri.startswith("file:///workspace/"):
            rel = uri[len("file:///workspace/") :]
            return os.path.join(self.workspace_root, rel)
        return uri

    def remap_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Remap all paths in a message between host and container."""

        def walk(v: Any) -> Any:
            if isinstance(v, dict):
                return {
                    k: self._unmap_path(val)
                    if isinstance(val, str) and val.startswith("file:///")
                    else walk(val)
                    for k, val in v.items()
                }
            if isinstance(v, list):
                return [walk(i) for i in v]
            return v

        return walk(msg)

    def send_client_message(self, msg: dict[str, Any]) -> None:
        """Forward a message from the browser to the LSP server."""

        # Remap any URIs from host paths to container paths.
        def walk(v: Any) -> Any:
            if isinstance(v, dict):
                return {
                    k: self._remap_path(val)
                    if isinstance(val, str) and val.startswith("file:///")
                    else walk(val)
                    for k, val in v.items()
                }
            if isinstance(v, list):
                return [walk(i) for i in v]
            return v

        self._send(walk(msg))

    def release_session(self) -> None:
        """Release this session, decrementing the client count.

        If the client count reaches zero, the session is closed and the
        container is stopped.
        """
        with self.lock:
            self.client_count -= 1
            if self.client_count <= 0:
                self.close()

    def close(self) -> None:
        self.closed = True
        try:
            if self.proc:
                self.proc.terminate()
                self.proc.wait(timeout=5)
        except Exception:
            pass
        podman_util.stop_container(self.container_name)


def _find_container_name(language: str) -> str:
    """Find the smallest unused number for lsp-LANG-N."""
    prefix = f"lsp-{language}-"
    r = podman_util._podman_run(
        "ps",
        "-a",
        "--format",
        "{{.Names}}",
    )
    if r.returncode != 0:
        return "1"
    used = set()
    for line in r.stdout.decode().splitlines():
        line = line.strip()
        if line.startswith(prefix):
            try:
                used.add(int(line[len(prefix) :]))
            except ValueError:
                pass
    i = 1
    while i in used:
        i += 1
    return str(i)


# Active LSP sessions by (language, workspace_root)
_sessions: dict[tuple[str, str], LSPPeer] = {}
_sessions_lock = threading.RLock()


def get_lsp_peer(language: str, workspace_root: str) -> LSPPeer | None:
    """Get or create an LSP session for a language and workspace.

    Returns None if the language has no image configured.
    """
    if language not in LANGUAGE_IMAGES:
        return None
    key = (language, os.path.abspath(workspace_root))
    with _sessions_lock:
        if key in _sessions:
            return _sessions[key]
        try:
            peer = LSPPeer(language, workspace_root)
        except Exception:
            logger.exception("Failed to start LSP server for %s", language)
            return None
        _sessions[key] = peer
        peer.increment_client_count(1)
        return peer


def shutdown_all() -> None:
    with _sessions_lock:
        peers = list(_sessions.values())
        _sessions.clear()
    for peer in peers:
        peer.close()


def shutdown_all_containers() -> None:
    """Stop all lsp containers at exit."""
    shutdown_all()
    r = podman_util._podman_run(
        "ps",
        "-a",
        "--filter",
        "name=lsp-",
        "--format",
        "{{.Names}}",
    )
    if r.returncode == 0:
        for line in r.stdout.decode().splitlines():
            line = line.strip()
            if line.startswith("lsp-"):
                podman_util._podman_run("rm", "-f", line)


lifespan.at_shutdown(shutdown_all_containers)
