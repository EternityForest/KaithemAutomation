# SPDX-License-Identifier: GPL-3.0-or-later
"""
Python client for the Kaithem Widget API WebSocket.

Provides a simple interface to connect to Kaithem's widget websocket
and send/subscribe to channels.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable
from typing import Any

import aiohttp
import msgpack
import structlog

logger = structlog.get_logger(__name__)


class WidgetApiClient:
    """
    Python client for the Kaithem Widget API.

    Connects to a Kaithem server via WebSocket and provides methods
    to send data to and subscribe to channels.
    """

    def __init__(self, server: str, username: str, password: str):
        """
        Initialize the widget API client.

        Args:
            server: The server URL (e.g., "http://localhost:8010")
            username: Username for authentication
            password: Password for authentication
        """

        self.server = server.rstrip("/")
        self.username = username
        self.password = password

        self.connected = False

        # Convert http to ws
        self.ws_url = self.server.replace("http://", "ws://").replace(
            "https://", "wss://"
        )
        self.ws_url += "/widgets/ws"

        self._is_finished = False

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._subscriptions: dict[str, list[Callable[[Any], None]]] = {}
        self._running = False
        self._lock = threading.RLock()
        self._connect_task: asyncio.Task | None = None

        # Start connection in background
        self._start_connection()

    def _start_connection(self) -> None:
        """Start the websocket connection in a background thread."""

        if self._is_finished:
            return

        def run():
            asyncio.run(self._connect())

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    async def _connect(self) -> None:
        """Connect to the websocket and handle messages."""
        self._session = aiohttp.ClientSession()

        try:
            # First, authenticate to get a session cookie
            async with self._session.post(
                f"{self.server}/login/login",
                data={"username": self.username, "password": self.password},
            ) as resp:
                if resp.status != 200:
                    logger.error("Authentication failed", status=resp.status)
                    return

            # Now connect to websocket with the session cookies
            self._ws = await self._session.ws_connect(self.ws_url)
            self._running = True

            # Send subscription message for existing subscriptions
            if self._subscriptions:
                await self._ws.send_json(
                    {
                        "subsc": list(self._subscriptions.keys()),
                        "req": [],
                        "upd": [],
                    }
                )

            self.connected = True

            # Handle incoming messages
            async for msg in self._ws:
                if not self._running:
                    break

                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_message(data)
                    except Exception:
                        logger.exception("Failed to parse message")
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    # Binary messages are msgpack encoded
                    try:
                        data = msgpack.unpackb(msg.data, raw=False)
                        await self._handle_message(data)
                    except Exception:
                        logger.exception("Failed to parse msgpack message")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("WebSocket error", error=msg.data)
                    break

        except Exception:
            logger.exception("WebSocket connection failed")
        finally:
            self.connected = False
            self._running = False
            await self._close_ws()

            # Try to reconnect after a delay
            if self._session is None or self._session.closed:
                await asyncio.sleep(2)
                self._start_connection()

    async def _close_ws(self) -> None:
        """Close the websocket connection."""
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        self._ws = None
        self._session = None

    async def _handle_message(self, data: list) -> None:
        """Handle incoming messages from the websocket."""
        for item in data:
            if not isinstance(item, list) or len(item) < 1:
                continue

            channel = item[0]
            value = item[1] if len(item) > 1 else None

            with self._lock:
                if channel in self._subscriptions:
                    for callback in self._subscriptions[channel]:
                        try:
                            callback(value)
                        except Exception:
                            logger.exception("Callback error", channel=channel)

    def send(self, channel: str, data: Any) -> None:
        """
        Send data to a channel.

        Args:
            channel: The channel name to send to
            data: The data to send. If bytes, will be sent as binary msgpack.
        """
        if self._ws and not self._ws.closed:
            # Run async send in a thread
            def run():
                asyncio.run(self._send_async(channel, data))

            thread = threading.Thread(target=run, daemon=True)
            thread.start()

    async def _send_async(self, channel: str, data: Any) -> None:
        """Async method to send data."""
        if not self._ws or self._ws.closed:
            return

        # If data is bytes (like YJS updates), send as binary msgpack
        if isinstance(data, bytes):
            payload = {"upd": [[channel, data]]}
            packed = msgpack.packb(payload, use_bin_type=True)
            await self._ws.send_bytes(packed)
        else:
            await self._ws.send_json({"upd": [[channel, data]]})

    def subscribe(self, channel: str, callback: Callable[[Any], None]) -> None:
        """
        Subscribe to a channel with a callback.

        Args:
            channel: The channel name to subscribe to
            callback: Function to call when messages arrive on this channel
        """
        with self._lock:
            if channel not in self._subscriptions:
                self._subscriptions[channel] = []
                # Send subscription to server if connected
                if self._ws and not self._ws.closed:

                    def run():
                        asyncio.run(
                            self._ws.send_json(
                                {"subsc": [channel], "unsub": [], "upd": []}
                            )
                        )

                    thread = threading.Thread(target=run, daemon=True)
                    thread.start()

            self._subscriptions[channel].append(callback)

    def unsubscribe(
        self, channel: str, callback: Callable[[Any], None]
    ) -> None:
        """
        Unsubscribe from a channel.

        Args:
            channel: The channel name to unsubscribe from
            callback: The callback to remove
        """
        with self._lock:
            if channel in self._subscriptions:
                try:
                    self._subscriptions[channel].remove(callback)
                except ValueError:
                    pass

                if not self._subscriptions[channel]:
                    del self._subscriptions[channel]
                    # Send unsubscribe to server if connected
                    if self._ws and not self._ws.closed:

                        def run():
                            asyncio.run(
                                self._ws.send_json(
                                    {"unsub": [channel], "subsc": [], "upd": []}
                                )
                            )

                        thread = threading.Thread(target=run, daemon=True)
                        thread.start()

    def close(self) -> None:
        """Close the connection."""
        self._is_finished = True
        self._running = False

        def run():
            asyncio.run(self._close_ws())

        thread = threading.Thread(target=run, daemon=True)
        thread.join(timeout=5)
