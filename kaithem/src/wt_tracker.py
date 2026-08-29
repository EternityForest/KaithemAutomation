import json

# Example using Starlette ASGI framework
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket

# In-memory swarms storage: { info_hash: set(websocket_connections) }
swarms = {}


async def tracker_endpoint(websocket: WebSocket):
    await websocket.accept()
    info_hash = None

    try:
        async for data in websocket.iter_text():
            message = json.loads(data)
            action = message.get("action")
            event = message.get("event")

            if event == "stopped":
                if info_hash and info_hash in swarms:
                    swarms[info_hash].discard(websocket)
                    if not swarms[info_hash]:
                        del swarms[info_hash]

            if action == "announce":
                info_hash = message.get("info_hash")
                if info_hash not in swarms:
                    swarms[info_hash] = set()
                swarms[info_hash].add(websocket)

                # Respond back with peer list/success
                await websocket.send_text(
                    json.dumps(
                        {
                            "action": "announce",
                            "info_hash": info_hash,
                            "interval": 120,
                            "complete": 0,
                            "incomplete": len(swarms[info_hash]),
                            "peers": [],  # Add peer mapping logic here
                        }
                    )
                )

            elif action == "offer":
                # Forward WebRTC offer to target peer
                peer_id = message.get("to")
                if peer_id in swarms[info_hash]:
                    await swarms[info_hash][peer_id].send_text(data)

    except Exception:
        pass
    finally:
        if info_hash and info_hash in swarms:
            swarms[info_hash].discard(websocket)
            if not swarms[info_hash]:
                del swarms[info_hash]


routes = [WebSocketRoute("/", endpoint=tracker_endpoint)]

app = Starlette(routes=routes)
