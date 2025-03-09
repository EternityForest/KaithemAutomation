"""
This file defines various plugin service interfaces
"""

from kaithem.api.plugins import PluginInterface, register_plugin_interface


class TTSEngine:
    def synth(self, s: str, speed: float = 1, sid: int = -1, file: str = ""):
        raise NotImplementedError  # pragma: no cover

    def speak(
        self,
        s: str,
        speed: float = 1,
        sid: int = 220,
        device: str = "",
        volume: float = 1,
    ):
        raise NotImplementedError  # pragma: no cover


class TTSAPI(PluginInterface):
    priority: int = 0
    service: str = "kaithem.core.tts"

    def get_model(self, model: str = "") -> TTSEngine | None:
        raise NotImplementedError  # pragma: no cover


register_plugin_interface(TTSAPI)
