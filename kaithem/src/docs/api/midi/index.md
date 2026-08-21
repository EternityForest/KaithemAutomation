# kaithem.api.midi

Public MIDI API.

All MIDI in/out is handled via a JACK client (works under pipewire-jack).
The plugin [`kaithem.src.plugins.CorePluginMidiToTags`](../../src/plugins/CorePluginMidiToTags/index.md#module-kaithem.src.plugins.CorePluginMidiToTags) owns the actual
JACK client that listens on MIDI inputs and fans events out to the
internal message bus and tag points.

This module is intentionally just a thin abstraction layer so callers
(the about page, WebChandlerConsole, etc.) don’t have to know how MIDI
is wired under the hood.

## Attributes

| [`logger`](#kaithem.api.midi.logger)             |    |
|--------------------------------------------------|----|
| [`inputs_cache`](#kaithem.api.midi.inputs_cache) |    |

## Functions

| [`normalize_midi_port_name`](#kaithem.api.midi.normalize_midi_port_name)(→ str)   | Given a raw JACK MIDI port name (e.g. `"My Keyboard:midi_out"`),   |
|-----------------------------------------------------------------------------------|--------------------------------------------------------------------|
| [`__list_midi_inputs`](#kaithem.api.midi.__list_midi_inputs)(→ list[str])         | Return a list of normalized MIDI input port names currently        |
| [`list_midi_inputs`](#kaithem.api.midi.list_midi_inputs)(→ list[str])             | These correspond to topics at /midi/portname you could             |

## Module Contents

### kaithem.api.midi.logger

### kaithem.api.midi.normalize_midi_port_name(name: [str](../../src/pages/index.md#kaithem.src.pages.str)) → [str](../../src/pages/index.md#kaithem.src.pages.str)

Given a raw JACK MIDI port name (e.g. `"My Keyboard:midi_out"`),
return a normalized name as used in the internal message bus.

### kaithem.api.midi.inputs_cache *: tuple[[float](../../src/chandler/groups/index.md#kaithem.src.chandler.groups.float), [list](../../src/pages/index.md#kaithem.src.pages.list)[[str](../../src/pages/index.md#kaithem.src.pages.str)]]* *= (0.0, [])*

### kaithem.api.midi.\_\_list_midi_inputs() → [list](../../src/pages/index.md#kaithem.src.pages.list)[[str](../../src/pages/index.md#kaithem.src.pages.str)]

Return a list of normalized MIDI input port names currently
visible to JACK (which under pipewire corresponds to all MIDI
sources the system can see).

### kaithem.api.midi.list_midi_inputs(force_update: bool = False) → [list](../../src/pages/index.md#kaithem.src.pages.list)[[str](../../src/pages/index.md#kaithem.src.pages.str)]

These correspond to topics at /midi/portname you could
subscribe to.
