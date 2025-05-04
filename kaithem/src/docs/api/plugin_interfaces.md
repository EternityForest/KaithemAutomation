# Plugin Interfaces

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Plugin Interfaces

> Auto-generated documentation for [plugin_interfaces](../../../api/plugin_interfaces.py) module.

- [Plugin Interfaces](#plugin-interfaces)
  - [TTSAPI](#ttsapi)
    - [TTSAPI().get_model](#ttsapi()get_model)
    - [TTSAPI().list_available_models](#ttsapi()list_available_models)
  - [TTSEngine](#ttsengine)
    - [TTSEngine().speak](#ttsengine()speak)
    - [TTSEngine().synth](#ttsengine()synth)

## TTSAPI

[Show source in plugin_interfaces.py:25](../../../api/plugin_interfaces.py#L25)

#### Signature

```python
class TTSAPI(PluginInterface): ...
```

### TTSAPI().get_model

[Show source in plugin_interfaces.py:29](../../../api/plugin_interfaces.py#L29)

Gets the TTS model.  However, as this may require downloading files,
it may return "None" if the model is not available right now.

You will need to try again later.

#### Signature

```python
def get_model(self, model: str = "", timeout: float = 5) -> TTSEngine | None: ...
```

### TTSAPI().list_available_models

[Show source in plugin_interfaces.py:39](../../../api/plugin_interfaces.py#L39)

#### Signature

```python
def list_available_models(self) -> list[dict[str, Any]]: ...
```



## TTSEngine

[Show source in plugin_interfaces.py:10](../../../api/plugin_interfaces.py#L10)

#### Signature

```python
class TTSEngine: ...
```

### TTSEngine().speak

[Show source in plugin_interfaces.py:14](../../../api/plugin_interfaces.py#L14)

#### Signature

```python
def speak(
    self, s: str, speed: float = 1, sid: int = 220, device: str = "", volume: float = 1
): ...
```

### TTSEngine().synth

[Show source in plugin_interfaces.py:11](../../../api/plugin_interfaces.py#L11)

#### Signature

```python
def synth(self, s: str, speed: float = 1, sid: int = -1, file: str = ""): ...
```