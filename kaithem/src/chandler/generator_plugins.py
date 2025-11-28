from __future__ import annotations

from typing import Any

from fadecanvas import LightingLayer


class LightingGeneratorPlugin:
    def __init__(self):
        pass

    def process_values(self, layer: LightingLayer) -> LightingLayer:
        return layer

    def on_config_change(self, key: str, val: Any):
        pass

    def on_keypoint_change(self, universe: str, added: bool):
        pass

    def on_auto_change(self, obj: dict[str, Any]):
        pass
