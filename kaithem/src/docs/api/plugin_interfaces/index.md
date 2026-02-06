# kaithem.api.plugin_interfaces

This file defines various plugin service interfaces

## Classes

| [`TTSEngine`](#kaithem.api.plugin_interfaces.TTSEngine)   |    |
|-----------------------------------------------------------|----|
| [`TTSAPI`](#kaithem.api.plugin_interfaces.TTSAPI)         |    |

## Module Contents

### *class* kaithem.api.plugin_interfaces.TTSEngine

#### *abstractmethod* synth(s: [str](../../src/pages/index.md#kaithem.src.pages.str), speed: [float](../../src/chandler/groups/index.md#kaithem.src.chandler.groups.float) = 1, sid: [int](../../src/chandler/groups/index.md#kaithem.src.chandler.groups.int) = -1, file: [str](../../src/pages/index.md#kaithem.src.pages.str) = '')

#### *abstractmethod* speak(s: [str](../../src/pages/index.md#kaithem.src.pages.str), speed: [float](../../src/chandler/groups/index.md#kaithem.src.chandler.groups.float) = 1, sid: [int](../../src/chandler/groups/index.md#kaithem.src.chandler.groups.int) = 220, device: [str](../../src/pages/index.md#kaithem.src.pages.str) = '', volume: [float](../../src/chandler/groups/index.md#kaithem.src.chandler.groups.float) = 1)

### *class* kaithem.api.plugin_interfaces.TTSAPI

Bases: [`kaithem.api.plugins.PluginInterface`](../plugins/index.md#kaithem.api.plugins.PluginInterface)

#### priority *: [int](../../src/chandler/groups/index.md#kaithem.src.chandler.groups.int)* *= 0*

#### service *: [str](../../src/pages/index.md#kaithem.src.pages.str)* *= 'kaithem.core.tts'*

#### *abstractmethod* get_model(model: [str](../../src/pages/index.md#kaithem.src.pages.str) = '', timeout: [float](../../src/chandler/groups/index.md#kaithem.src.chandler.groups.float) = 5) → [TTSEngine](#kaithem.api.plugin_interfaces.TTSEngine) | None

Gets the TTS model.  However, as this may require downloading files,
it may return "None" if the model is not available right now.

You will need to try again later.

#### list_available_models() → [list](../../src/pages/index.md#kaithem.src.pages.list)[dict[[str](../../src/pages/index.md#kaithem.src.pages.str), Any]]
