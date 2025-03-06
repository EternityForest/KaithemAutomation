# Plugin Interfaces

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Plugin Interfaces

> Auto-generated documentation for [plugin_interfaces](../../../api/plugin_interfaces.py) module.

- [Plugin Interfaces](#plugin-interfaces)
  - [TTSAPI](#ttsapi)
    - [TTSAPI().get_model](#ttsapi()get_model)
  - [TTSEngine](#ttsengine)
    - [TTSEngine().speak](#ttsengine()speak)
    - [TTSEngine().synth](#ttsengine()synth)

## TTSAPI

[Show source in plugin_interfaces.py:23](../../../api/plugin_interfaces.py#L23)

#### Signature

```python
class TTSAPI(PluginInterface): ...
```

### TTSAPI().get_model

[Show source in plugin_interfaces.py:27](../../../api/plugin_interfaces.py#L27)

#### Signature

```python
def get_model(self, model: str = "") -> TTSEngine | None: ...
```



## TTSEngine

[Show source in plugin_interfaces.py:8](../../../api/plugin_interfaces.py#L8)

#### Signature

```python
class TTSEngine: ...
```

### TTSEngine().speak

[Show source in plugin_interfaces.py:12](../../../api/plugin_interfaces.py#L12)

#### Signature

```python
def speak(
    self, s: str, speed: float = 1, sid: int = 220, device: str = "", volume: float = 1
): ...
```

### TTSEngine().synth

[Show source in plugin_interfaces.py:9](../../../api/plugin_interfaces.py#L9)

#### Signature

```python
def synth(self, s: str, speed: float = 1, sid: int = -1, file: str = ""): ...
```