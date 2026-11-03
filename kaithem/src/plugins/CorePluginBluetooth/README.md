# CorePluginBluetooth

Linux-only BlueZ console.  The plugin is split in two layers:

- `bluez.py` -- a pure D-Bus wrapper (`BluezManager`).  No Quart import, so
  server-side automation can call it directly.
- `__init__.py` -- REST, WebSocket, page route, apps-page entry.

## REST

All endpoints require `system_admin` and return `403` JSON for API callers
without it.

| Method | Path | Body |
| --- | --- | --- |
| GET | `/bluetooth/api/snapshot` | -- |
| POST | `/bluetooth/api/refresh` | -- |
| POST | `/bluetooth/api/discovering` | `{"discovering": bool}` |
| POST | `/bluetooth/api/adapters/<address-or-path>/properties` | see below |
| POST | `/bluetooth/api/devices/<address>/pair` | -- |
| POST | `/bluetooth/api/devices/<address>/connect` | -- |
| POST | `/bluetooth/api/devices/<address>/disconnect` | -- |
| POST | `/bluetooth/api/devices/<address>/trust` | `{"trusted": bool}` |
| POST | `/bluetooth/api/devices/<address>/forget` | -- |

Mutating calls return `{"status": "ok", "snapshot": {...}}`.  Errors return
`{"error": "<dbus error name>", "message": "..."}`.

### Adapter properties

`POST /bluetooth/api/adapters/<address-or-path>/properties` writes writable
BlueZ `Adapter1` properties (and LE advertising) on any controller:

| Key | Type | Notes |
| --- | --- | --- |
| `Powered` | bool | Applied first, before other properties. |
| `Discoverable` | bool | |
| `Pairable` | bool | |
| `Alias` | string | User-facing name; BlueZ `Name` is read-only. |
| `DiscoverableTimeout` | int | Seconds. |
| `PairableTimeout` | int | Seconds. |
| `Advertising` | bool | Pseudo-property using `LEAdvertisingManager1`. |

Example: make the virtual controller connectable.

```json
{"Powered": true, "Discoverable": true, "Pairable": true, "Advertising": true}
```

`Advertising` registers a minimal `org.bluez.LEAdvertisement1` object with
`Type="peripheral"` and `Includes=["local-name"]`.  Adapters without an
`LEAdvertisingManager1` reject it.  The snapshot reports `le_advertising`,
`advertising`, `active_instances`, and `supported_instances` per adapter.

## WebSocket

`/bluetooth/ws` (admin only) sends:

- `{"type": "snapshot", "snapshot": {...}}` on connect and on live changes.
- `{"type": "agent_request", "request": {...}}` when pairing needs user input.
- `{"type": "agent_display", "request": {...}}` for PIN/passkey display only.
- `{"type": "agent_resolved", "id": "...", "accepted": bool}`.

Clients answer prompts with:

```json
{"type": "agent_response", "id": "...", "accepted": true, "value": "1234"}
```

`agent_request.kind` is one of `pin`, `passkey`, `confirm`, `authorize`,
`authorize_service`.  A prompt is rejected automatically after 90 seconds or
immediately if no WebSocket is connected.

## Programmatic use

```python
from kaithem.src.plugins.CorePluginBluetooth import manager

manager.snapshot()                 # cached state, starts the D-Bus thread
manager.connect("AA:BB:CC:DD:EE:FF")
manager.disconnect("AA:BB:CC:DD:EE:FF")
manager.set_adapter_properties("hci1", {"Pairable": True})
manager.set_adapter_properties("hci1", {"Advertising": False})
```

Virtual controllers (`btvirt`) are created outside the plugin because that
requires root; point the console at any existing adapter by address or object
path.
```

Use the plugin's `manager` singleton from server-side features so there is only
one D-Bus thread and one pairing agent.  Constructing a separate
`BluezManager` is possible, but it would register a second BlueZ agent.

`BluezManager` is thread-safe and blocks the calling thread.  `add_listener()`
receives the same events as the WebSocket; `respond_to_agent_request()` can be
used by a non-web listener to answer pairing prompts.
