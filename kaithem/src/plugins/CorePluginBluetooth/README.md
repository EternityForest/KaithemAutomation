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
| GET | `/bluetooth/api/devices/<address>/config` | -- |
| POST | `/bluetooth/api/devices/<address>/config` | partial config |
| DELETE | `/bluetooth/api/devices/<address>/config` | -- |

Mutating calls return `{"status": "ok", "snapshot": {...}}`.  The `config`
`POST` additionally returns the applied `config`.  Errors return
`{"error": "<dbus error name>", "message": "..."}`.

## Per-device settings

Settings live in `<vardir>/core.settings/bluetooth-<hostname>.json` so a
backup restored on a machine with a different set of paired devices does not
clobber that machine's devices.  Every snapshot device carries its `config`
object:

| Key | Type | Meaning |
| --- | --- | --- |
| `auto_connect` | bool | Reconnect the paired device whenever it is offline. |
| `alerts` | bool | Trip Kaithem alerts on low battery, weak signal, disconnect. |
| `name` | string or null | Local name; must be a Python identifier. |

Each device also has a `seen` flag.  Configured devices stay in every snapshot
even when BlueZ does not report them, as placeholders with `seen: false`, so
their settings can be inspected, edited, or deleted.  Such devices cannot be
paired, trusted, connected, or forgotten because BlueZ has no object path for
them.

`POST .../config` accepts any subset of those keys.  Setting `name` to `null`
or `""` clears it, and names must be unique (case-insensitively) across
devices.  Forgetting a device deletes its settings.

The supervisor thread ticks every 5 seconds and:

- connects paired devices with `auto_connect` that are offline and not
  blocked (30 second cooldown, 30 second connect timeout),
- raises a `warning` when battery is below 20%,
- raises a `warning` when a connected device's RSSI is below -68 dBm,
- raises an `error` when a configured device disconnects.

Alerts are named `Bluetooth <ADDRESS>: <title>` and are cleared or closed when
the condition goes away or the device is forgotten.

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
- `{"type": "config", "address": "...", "config": {...}}` when a device's
  stored settings change (from any client or server-side code).

Clients answer prompts with:

```json
{"type": "agent_response", "id": "...", "accepted": true, "value": "1234"}
```

`agent_request.kind` is one of `pin`, `passkey`, `confirm`, `authorize`,
`authorize_service`.  A prompt is rejected automatically after 90 seconds or
immediately if no WebSocket is connected.

## Programmatic use

```python
from kaithem.src.plugins.CorePluginBluetooth import manager, supervisor

manager.snapshot()                 # cached state, starts the D-Bus thread
manager.connect("AA:BB:CC:DD:EE:FF")
manager.disconnect("AA:BB:CC:DD:EE:FF")
manager.set_adapter_properties("hci1", {"Pairable": True})
manager.set_adapter_properties("hci1", {"Advertising": False})

supervisor.update_device_config(
    "AA:BB:CC:DD:EE:FF", {"auto_connect": True, "name": "headphones"}
)
```

Virtual controllers (`btvirt`) are created outside the plugin because that
requires root; point the console at any existing adapter by address or object
path.  Use `btvirt -l1 -L`, never the default dual-mode `-l` alone:
`-L` only marks an emulator as LE-only, it does not create one.  A BR/EDR
controller makes BlueZ register the audio profiles, so the virtual controller
shows up as a Bluetooth speaker in the system audio stack.  `make
dev-run-bluetooth-test` creates and tears down two LE-only controllers via
`scripts/virtual-bluetooth-setup.sh`; their addresses are assigned by btvirt
and published in `env.json`, because a vhci controller has no supported way to
set its address.  Setup writes a `kaithem-virtual-adapter` marker into each
controller's `/var/lib/bluetooth/<address>` directory, and setup and teardown
delete the marked settings of adapters that are gone, so cleanup never depends
on knowing an address in advance and does not require pinning one.

Use the plugin's `manager` singleton from server-side features so there is only
one D-Bus thread and one pairing agent.  Constructing a separate
`BluezManager` is possible, but it would register a second BlueZ agent.

`BluezManager` is thread-safe and blocks the calling thread.  `add_listener()`
receives the same events as the WebSocket; `respond_to_agent_request()` can be
used by a non-web listener to answer pairing prompts.

`BluetoothSupervisor` (in `supervisor.py`) owns settings, auto-connect, and
alerts.  It also has no Quart imports, so server-side code can use
`supervisor.update_device_config()`, `get_device_config()`, and
`remove_device()` directly.
