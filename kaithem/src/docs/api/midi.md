# Midi

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Midi

> Auto-generated documentation for [midi](../../../api/midi.py) module.

- [Midi](#midi)
  - [_list_midi_inputs](#_list_midi_inputs)
  - [list_midi_inputs](#list_midi_inputs)
  - [normalize_midi_port_name](#normalize_midi_port_name)

## _list_midi_inputs

[Show source in midi.py:30](../../../api/midi.py#L30)

These correspond to topics at /midi/portname you could
subscribe to.

#### Signature

```python
def _list_midi_inputs() -> list[str]: ...
```



## list_midi_inputs

[Show source in midi.py:70](../../../api/midi.py#L70)

#### Signature

```python
def list_midi_inputs(force_update: bool = False) -> list[str]: ...
```



## normalize_midi_port_name

[Show source in midi.py:18](../../../api/midi.py#L18)

Given a name as would be returned by
rtmidi's get_port_name, return a normalized name
as used in the internal message bus.

#### Signature

```python
def normalize_midi_port_name(name: str) -> str: ...
```