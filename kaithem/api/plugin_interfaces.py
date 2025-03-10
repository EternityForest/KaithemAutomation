"""
This file defines various plugin service interfaces
"""

from typing import Any

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

    def get_model(
        self, model: str = "", timeout: float = 5
    ) -> TTSEngine | None:
        """Gets the TTS model.  However, as this may require downloading files,
        it may return "None" if the model is not available right now.

        You will need to try again later.
        """
        raise NotImplementedError  # pragma: no cover

    def list_available_models(self) -> list[dict[str, Any]]:
        return []


register_plugin_interface(TTSAPI)
