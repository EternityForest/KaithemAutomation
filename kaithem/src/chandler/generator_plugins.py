from __future__ import annotations

import copy
import json
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, TypedDict

import numpy
import numpy.typing

if TYPE_CHECKING:
    from .cue import EffectData

import wasm_kegs
from kaithem.src import kegs
from kaithem.src.kegs import package_store

from .universes import get_channel_meta, mapChannel, mapUniverse

lighting_generators = package_store.list_by_type(
    "kaithem.chandler.lighting-generator"
)


wasm_plugin_pool_lock = threading.RLock()
wasm_plugin_pool = []


def compile_set_channel_metadata(
    start_ch: int, metadata: list[tuple[int, int, dict[str, Any]]]
):
    pl = wasm_kegs.Payload(b"")

    pl.write_i64(start_ch)

    for fix_id, type_code, extra_data in metadata:
        pl.write_i64(fix_id)
        pl.write_i64(type_code)
        pl.write_bytes(json.dumps(extra_data).encode())

    return pl.data


def compile_set_input_values(start_ch: int, vals: list[float] = []):
    pl = wasm_kegs.Payload(b"")
    pl.write_i64(start_ch)

    for value in vals:
        pl.write_f32(value)

    return pl.data


def get_plugin(name: str, config: dict[str, Any]) -> WASMPlugin:
    if not name or name == "direct":
        raise RuntimeError("No plugin specified")

    with wasm_plugin_pool_lock:
        for p in list(wasm_plugin_pool):
            if p.plugin.name == name:
                wasm_plugin_pool.remove(p)
                return p

    p = WASMPlugin(name, config)
    p.generator_type = "name"
    return p


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
    "x": 11,
    "y": 12,
}


class CachedEffectLayout(TypedDict):
    channel_mapping: list[tuple[str, int]]
    reverse_mapping: dict[tuple[str, int], int]
    input_data_block: bytes
    precomputed_mappings: dict[
        str,
        tuple[
            numpy.typing.NDArray[numpy.int64],
            numpy.typing.NDArray[numpy.int64],
        ],
    ]
    compiled_metadata_block: bytes
    source: EffectData


lighting_generator_data_cache: OrderedDict[
    tuple[str, str], CachedEffectLayout
] = OrderedDict()


class WASMPlugin:
    def __init__(self, plugin: str = "", config: dict[str, Any] = {}):
        # Maps entries in the arrays plugins take
        # to channel, value pairs
        self.channel_mapping: list[tuple[str, int]] = []

        self.reverse_mapping: dict[tuple[str, int], int] = {}

        self.dynamic = False

        self.generator_type = "direct"

        self.precomputed_mappings: dict[
            str,
            tuple[
                numpy.typing.NDArray[numpy.int64],
                numpy.typing.NDArray[numpy.int64],
            ],
        ] = {}

        with kegs.package_store:
            self.plugin: Loader = Loader(plugin, config)

    def _effect_data_to_layout(
        self, cue: str, effectid: str, effect_data: EffectData
    ):
        try:
            if (cue, effectid) not in lighting_generator_data_cache:
                x = lighting_generator_data_cache[(cue, effectid)]
                if x["source"] == effect_data:
                    return x
        except KeyError:
            pass

        mapping: list[tuple[str, int]] = []
        input_data = []
        reverse_mapping = {}
        fixture_id = 0

        # What we pass to the plugin
        metadata_tuples: list[tuple[int, int, dict[str, Any]]] = []

        # For each universe we want to affect, a set of indexes
        # into the universe, then a set of indexes into the fixture
        output_mappings_by_universe: dict[str, tuple[list[int], list[int]]] = {}

        for i in effect_data["keypoints"]:
            array_start = 0
            array_step = 1
            array_end = 0
            i_target = i["target"]
            i_target_mapped = mapUniverse(i_target.split("[")[0])
            if i_target_mapped is None:
                continue

            if i_target_mapped not in output_mappings_by_universe:
                output_mappings_by_universe[i_target_mapped] = (
                    [],
                    [],
                )

            if "[" in i_target:
                x = i_target.split("[")[-1].replace("]", "")
                array_slice = x.split(":")
                array_start = int(array_slice[0])
                if len(array_slice) == 1:
                    array_end = array_start
                else:
                    array_end = int(array_slice[1])

                if len(array_slice) > 2:
                    array_step = int(array_slice[2])

            for j in range(array_start, array_end + 1, array_step):
                fixture_id += 1
                for ch in i["values"]:
                    val = i["values"][ch]

                    try:
                        val = float(val)  # type: ignore
                    except Exception:
                        continue

                    mapped_channel = mapChannel(
                        i_target.split("[")[0] + f"[{j}]", ch
                    )

                    if mapped_channel is None:
                        continue

                    m = get_channel_meta(*mapped_channel).get("type", "unknown")
                    typecode = type_codes.get(m, 0)

                    metadata_tuples.append(
                        (
                            fixture_id,
                            typecode,
                            {},
                        )
                    )

                    output_mappings_by_universe[mapped_channel[0]][0].append(
                        mapped_channel[1]
                    )
                    output_mappings_by_universe[mapped_channel[0]][1].append(
                        len(mapping)
                    )

                    mapping.append(mapped_channel)

                    reverse_mapping[mapped_channel] = len(mapping) - 1

                    input_data.append(i["values"][ch])

                    # We don't know so give every channel its
                    # own universe
                    if not i_target.startswith("@"):
                        fixture_id += 1

        # Kinda like null terminator
        metadata_tuples.append((-1, -1, {}))

        precomputed = {
            k: (
                numpy.array(
                    output_mappings_by_universe[k][0], dtype=numpy.int64
                ),
                numpy.array(
                    output_mappings_by_universe[k][1], dtype=numpy.int64
                ),
            )
            for k in output_mappings_by_universe
        }
        rv: CachedEffectLayout = {
            "channel_mapping": mapping,
            "input_data_block": compile_set_input_values(0, input_data),
            "reverse_mapping": reverse_mapping,
            "compiled_metadata_block": compile_set_channel_metadata(
                0, metadata_tuples
            ),
            "precomputed_mappings": precomputed,
            "source": copy.deepcopy(effect_data),
        }

        lighting_generator_data_cache[(cue, effectid)] = rv

        if len(lighting_generator_data_cache) > 100:
            lighting_generator_data_cache.popitem()

        return rv

    def effect_data_to_layout(
        self, cue: str, effectid: str, effect_data: EffectData
    ):
        d = self._effect_data_to_layout(cue, effectid, effect_data)

        self.channel_mapping = d["channel_mapping"]
        self.reverse_mapping = d["reverse_mapping"]
        self.precomputed_mappings = d["precomputed_mappings"]

        self.plugin.call_plugin(
            "set_channel_metadata", d["compiled_metadata_block"]
        )
        self.plugin.call_plugin("set_input_values", d["input_data_block"])

    def process(self, t: float):
        return self.plugin.process(0, len(self.channel_mapping), t)

    def set_channel_metadata(
        self, ch_idx: int, metadata: list[tuple[int, int, dict[str, Any]]]
    ):
        self.plugin.set_channel_metadata(ch_idx, metadata)

    def set_input_values(self, ch_idx: int, vals: list[float] = []):
        self.plugin.set_input_values(ch_idx, vals)

    def return_to_pool(self):
        self.plugin.return_to_pool()
        self.plugin = None  # type: ignore


class Loader(wasm_kegs.PluginLoader):
    plugin_type = "kaithem.chandler.lighting-generator"

    def process(self, start: int, size: int, t: float):
        pl = wasm_kegs.Payload(b"")
        pl.write_i64(start)
        pl.write_i64(size)
        pl.write_i64(int(t / 10**6))
        # Array of floats
        x = self.call_plugin("process", pl.data)

        return numpy.frombuffer(x, dtype=numpy.float32)

    def set_channel_metadata(
        self, start_ch: int, metadata: list[tuple[int, int, dict[str, Any]]]
    ):
        pl = compile_set_channel_metadata(start_ch, metadata)
        self.call_plugin("set_channel_metadata", pl)

    def set_input_values(self, start_ch: int, vals: list[float] = []):
        pl = compile_set_input_values(start_ch, vals)
        self.call_plugin("set_input_values", pl)

    def return_to_pool(self):
        with wasm_plugin_pool_lock:
            if len(wasm_plugin_pool) > 12:
                wasm_plugin_pool.pop(0)
            wasm_plugin_pool.append(self)
