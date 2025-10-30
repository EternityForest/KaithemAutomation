# kaithem.api.plugin_interfaces

This file defines various plugin service interfaces

## Classes

| [`TTSEngine`](#kaithem.api.plugin_interfaces.TTSEngine)   |    |
|-----------------------------------------------------------|----|
| [`TTSAPI`](#kaithem.api.plugin_interfaces.TTSAPI)         |    |

## Module Contents

### *class* kaithem.api.plugin_interfaces.TTSEngine

#### *abstract* synth(s: str, speed: float = 1, sid: int = -1, file: str = '')

#### *abstract* speak(s: str, speed: float = 1, sid: int = 220, device: str = '', volume: float = 1)

### *class* kaithem.api.plugin_interfaces.TTSAPI

Bases: [`kaithem.api.plugins.PluginInterface`](../plugins/index.md#kaithem.api.plugins.PluginInterface)

#### priority *: int* *= 0*

#### service *: str* *= 'kaithem.core.tts'*

#### *abstract* get_model(model: str = '', timeout: float = 5) → [TTSEngine](#kaithem.api.plugin_interfaces.TTSEngine) | None

Gets the TTS model.  However, as this may require downloading files,
it may return "None" if the model is not available right now.

You will need to try again later.

#### list_available_models() → list[dict[str, Any]]
