from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy

if TYPE_CHECKING:
    from .cue import EffectData

from .universes import fixtures, get_channel_meta, mapChannel


def get_plugin(name: str) -> LightingGeneratorPlugin:
    return LightingGeneratorPlugin()


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


type_codes = {
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
        self.input_map: dict[tuple[str, int | str], int] = {}
        self.output_map: list[tuple[str, str]] = []
        self.inputs = numpy.zeros(1, dtype=numpy.float32)

    def effect_data_to_layout(self, effect: EffectData):
        inputs: list[int] = []
        outputs: list[int] = []

        input_vals = []

        input_map = {}
        output_map = []

        n = 0
        for k in effect.get("keypoints", []):
            # if k["target"].startswith("@"):
            #     fix = fixtures.get(k["target"][1:])
            for i in k["values"]:
                if k["values"][i] is None:
                    continue
                input_map[(mapChannel(k["target"], i))] = n
                n += 1
                input_vals.append(k["values"][i])

                md = get_channel_meta(k["target"], i)
                tc = 0
                fixid = md.get("fixid", 0)
                if md.get("type", "") in type_codes:
                    tc = type_codes[md["type"]]
                inputs.append(fixid * 100 + tc)

                inputs.append(fixid)
                inputs.append(tc)

        for k in effect.get("auto", []):
            f = fixtures.get(k["fixture"])
            if f:
                fix = f()
                if fix:
                    for i in fix.channels:
                        if not i.get("name"):
                            continue
                        output_map.append(mapChannel(k["fixture"], i["name"]))

                        md = get_channel_meta(k["fixture"], i["name"])
                        tc = 0
                        fixid = md.get("fixid", 0)
                        if md.get("type", "") in type_codes:
                            tc = type_codes[md["type"]]
                        inputs.append(fixid * 100 + tc)

                        outputs.append(fixid)
                        outputs.append(tc)

        self.input_map = input_map
        self.output_map = output_map
        self.inputs = numpy.array(input_vals, dtype=numpy.float32)

        x = numpy.array(inputs, dtype=numpy.int32)
        y = numpy.array(outputs, dtype=numpy.int32)

        self.on_layout_change([x, y])

    def process_values(self, x: list[float]) -> list[float]:
        return x

    def on_config_change(self, obj: dict[str, Any]):
        pass

    def on_layout_change(self, layout: list[list[dict[str, Any]]]):
        pass
