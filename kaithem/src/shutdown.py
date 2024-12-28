import asyncio
import threading

import icemedia.sound_player
from scullery import messagebus

_shutdown_events: list[asyncio.Event] = []


def add_shutdown_event(event: asyncio.Event):
    _shutdown_events.append(event)


def shutdown():
    for event in _shutdown_events:
        event.set()

    threading.Thread(
        target=icemedia.sound_player.stop_all_sounds, daemon=True
    ).start()
    messagebus.post_message(
        "/system/notifications/shutdown", "Recieved SIGINT or SIGTERM."
    )
    messagebus.post_message("/system/shutdown", "Recieved SIGINT or SIGTERM.")
