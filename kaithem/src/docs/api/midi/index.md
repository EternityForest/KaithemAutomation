# kaithem.api.midi

You can use normalize_midi_port_name to get name for the midi device
which can be used for things like subscribing to "/midi/portname".

## Attributes

| [`logger`](#kaithem.api.midi.logger)             |    |
|--------------------------------------------------|----|
| [`once`](#kaithem.api.midi.once)                 |    |
| [`inputs_cache`](#kaithem.api.midi.inputs_cache) |    |

## Functions

| [`normalize_midi_port_name`](#kaithem.api.midi.normalize_midi_port_name)(→ str)   | Given a name as would be returned by                   |
|-----------------------------------------------------------------------------------|--------------------------------------------------------|
| [`__list_midi_inputs`](#kaithem.api.midi.__list_midi_inputs)(→ list[str])         |                                                        |
| [`list_midi_inputs`](#kaithem.api.midi.list_midi_inputs)(→ list[str])             | These correspond to topics at /midi/portname you could |

## Module Contents

### kaithem.api.midi.logger

### kaithem.api.midi.normalize_midi_port_name(name: str) → str

Given a name as would be returned by
rtmidi's get_port_name, return a normalized name
as used in the internal message bus.

### kaithem.api.midi.once *: list[int]* *= [0]*

### kaithem.api.midi.inputs_cache *: tuple[float, list[str]]* *= (0.0, [])*

### kaithem.api.midi.\_\_list_midi_inputs() → list[str]

### kaithem.api.midi.list_midi_inputs(force_update: bool = False) → list[str]

These correspond to topics at /midi/portname you could
subscribe to.
