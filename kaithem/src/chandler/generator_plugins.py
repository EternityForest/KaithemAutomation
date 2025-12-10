from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import numpy
import numpy.typing

if TYPE_CHECKING:
    from .cue import EffectData

import wasm_kegs
from kaithem.src import kegs

from .universes import get_channel_meta, mapChannel


def get_plugin(name: str, config: dict[str, Any]) -> LightingGeneratorPlugin:
    if not name or name == "direct":
        return LightingGeneratorPlugin()

    return WASMPlugin(name, config)


"""
A layout consists of two JSON lists.
The first is a list of input keypoints,
and the second is a list of output vals.

For each keypoint there must be:

{
"fixture": "fixture name",
"type": "red"
}


"""

# First 16 are reserved for colors that can be interpolated
type_codes: dict[str, int] = {
    "END": -1,
    "unknown": 0,
    "red": 1,
    "green": 2,
    "blue": 3,
    "white": 4,
    "neutral_white": 5,
    "warm_white": 6,
    "cool_white": 7,
    "amber": 8,
    "lime": 9,
    "uv": 10,
}


class LightingGeneratorPlugin:
    def __init__(self):
        # Maps entries in the arrays plugins take
        # to channel, value pairs
        self.channel_mapping: list[tuple[str, int]] = []

        self.reverse_mapping: dict[tuple[str, int], int] = {}

        self.input_data = numpy.ndarray((0,), dtype=numpy.float32)

        self.dynamic = False

    def process(self, t: float):
        return numpy.where(self.input_data == -1000_001, 0, self.input_data)

    def set_channel_metadata(
        self,
        ch_idx: int,
        fix_id: int,
        type_code: int,
        extra_data: dict[str, Any] = {},
    ):
        pass

    def set_input_value(self, ch_idx: int, value: float):
        self.input_data[ch_idx] = value

    def effect_data_to_layout(self, effect_data: EffectData):
        mapping = []
        input_data = []
        reverse_mapping = {}

        for i in effect_data["keypoints"]:
            array_start = 0
            array_step = 1
            array_end = 0

            if "[" in i["target"]:
                x = i["target"].split("[")[-1].replace("]", "")
                array_slice = x.split(",")
                array_start = int(array_slice[0])
                if len(array_slice) == 1:
                    array_end = array_start
                else:
                    array_end = int(array_slice[-1])

                if len(array_slice) > 2:
                    array_step = int(array_slice[2])

            fixture_id = 0

            for j in range(array_start, array_end + 1, array_step):
                fixture_id += 1
                for ch in i["values"]:
                    mapped_channel = mapChannel(i["target"], ch)

                    if mapped_channel is None:
                        continue

                    m = get_channel_meta(*mapped_channel).get("type", "unknown")
                    typecode = type_codes.get(m, 0)

                    self.set_channel_metadata(
                        len(mapping),
                        fixture_id,
                        typecode,
                        {},
                    )

                    mapping.append(mapped_channel)
                    reverse_mapping[mapped_channel] = len(mapping) - 1

                    input_data.append(i["values"][ch])

                    # We don't know so give every channel its
                    # own universe
                    if not i["target"].startswith("@"):
                        fixture_id += 1

        # Kinda like null terminator
        self.set_channel_metadata(len(mapping), -1, -1, {})

        self.channel_mapping = mapping
        self.reverse_mapping = reverse_mapping
        self.input_data = numpy.array(input_data, dtype=numpy.float32)


class Loader(wasm_kegs.PluginLoader):
    def process(self, start: int, size: int, t: float):
        pl = wasm_kegs.Payload(b"")
        pl.write_i64(start)
        pl.write_i64(size)
        pl.write_f32(t)
        # Array of floats
        x = self.call_plugin("process", pl.data)

        return numpy.frombuffer(x, dtype=numpy.float32)

    def set_channel_metadata(
        self,
        ch_idx: int,
        fix_id: int,
        type_code: int,
        extra_data: dict[str, Any] = {},
    ):
        pl = wasm_kegs.Payload(b"")
        pl.write_i64(ch_idx)
        pl.write_i64(fix_id)
        pl.write_i64(type_code)
        pl.write_bytes(json.dumps(extra_data).encode())
        self.call_plugin("set_channel_metadata", pl.data)

    def set_input_value(self, ch_idx: int, value: float):
        pl = wasm_kegs.Payload(b"")
        pl.write_i64(ch_idx)
        pl.write_f32(value)
        self.call_plugin("set_input_value", pl.data)


class WASMPlugin(LightingGeneratorPlugin):
    def __init__(self, plugin: str, config: dict[str, Any]):
        super().__init__()
        self.dynamic = False

        with kegs.package_store:
            self.plugin = Loader(plugin, config)

    def process(self, t: float):
        return self.plugin.process(0, len(self.input_data), t)

    def set_channel_metadata(
        self,
        ch_idx: int,
        fix_id: int,
        type_code: int,
        extra_data: dict[str, Any] = {},
    ):
        self.plugin.set_channel_metadata(ch_idx, fix_id, type_code, extra_data)
        return super().set_channel_metadata(
            ch_idx, fix_id, type_code, extra_data
        )

    def set_input_value(self, ch_idx: int, value: float):
        self.plugin.set_input_value(ch_idx, value)
        return super().set_input_value(ch_idx, value)
