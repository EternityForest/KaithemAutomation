"""
This file defines various plugin service interfaces
"""

from kaithem.api.plugins import PluginInterface, register_plugin_interface


class TTSEngine:
    def synth(self, s: str, speed: float = 1, sid: int = -1, file: str = ""):
        raise NotImplementedError

    def speak(self, s: str, speed: float = 1, sid: int = 220, device: str = ""):
        raise NotImplementedError


class TTSAPI(PluginInterface):
    priority: int = 0
    service: str = "kaithem.core.tts"

    def get_model(self, model: str = "") -> TTSEngine | None:
        raise NotImplementedError


register_plugin_interface(TTSAPI)
