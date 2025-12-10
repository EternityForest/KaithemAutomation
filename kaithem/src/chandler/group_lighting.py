from __future__ import annotations

import copy
import re
import time
import traceback
from typing import TYPE_CHECKING

import numpy

from kaithem.src.chandler.cue import EffectData

from . import blendmodes, generator_plugins, universes

if TYPE_CHECKING:
    from .ChandlerConsole import ChandlerConsole
    from .groups import Cue, Group

from .core import iter_boards, render_loop_lock, serialized_async_with_core_lock
from .fadecanvas import LightingLayer

SPECIAL_VALUE_AUTO = -501


def parse_interval(s: str) -> list[int]:
    """Given a string that contains [0], [1:10], [1:10:2], etc, return a list of
    integers that satisfy the interval, inclusive of the endpoints.
    """
    in_brackets = re.findall(r"\[(.*?)\]", s)
    if not in_brackets:
        return [0]
    args = in_brackets[0].split(":")
    if len(args) == 1:
        return [int(in_brackets[0])]
    elif len(args) == 2:
        return list(range(int(args[0]), int(args[1]) + 1))
    else:
        return list(range(int(args[0]), int(args[1]) + 1, int(args[2])))


def refresh_all_group_lighting():
    def f():
        for b in iter_boards():
            for i in b.groups:
                b.groups[i].refresh_lighting()

    serialized_async_with_core_lock(f)


class GroupLightingManager:
    def __init__(self, group: Group):
        """Mutable state of this class protected by the render loop lock"""

        self.group = group

        self.cue_start_time: float = time.time()

        self.should_repaint_onto_universes: dict[str, bool] = {}

        # Track this so we can repaint
        self.fade_position = 1.0

        self.should_recalc_values_before_render = False
        self.on_demand_universes: dict[str, universes.Universe] = {}

        self.cue: Cue | None = None

        # Place to stash a blend object for new blending mode
        # Hardcoded indicates that applyLayer reads the blend name and we
        # have hardcoded logic there
        self._blend: blendmodes.BlendMode = blendmodes.HardcodedBlendMode(self)
        self.blendClass: type[blendmodes.BlendMode] = (
            blendmodes.HardcodedBlendMode
        )
        self.blend_args: dict[str, float | int | bool | str] = (
            group.blend_args or {}
        )

        self.fading_from: dict[str, LightingLayer] = {}
        """These are inputs to generartor effects"""

        self.cached_values_raw: dict[str, LightingLayer] = {}
        """Current values from the group, after applying backtrack but before
            generators run.
            Every effect has its own inputs
        """

        # Generator per-effect
        self.generators = {}

    def clean(self):
        with render_loop_lock:
            for i in list(self.cached_values_raw):
                self.cached_values_raw[i].clean()

    def refresh_generator_layout(self, effect: str):
        with render_loop_lock:
            if self.cue:
                ed: EffectData | None = self.cue.get_effect_by_id(effect)
                if ed:
                    self.generators[effect] = generator_plugins.get_plugin(
                        ed.get("type", ""), {}
                    )

                else:
                    ed = {
                        "keypoints": [],
                        "type": "direct",
                        "id": effect,
                    }

                self.generators[effect].effect_data_to_layout(ed)

    def set_value(
        self, effect: str, universe: str, channel: int, value: float | None
    ):
        with render_loop_lock:
            if effect not in self.cached_values_raw:
                self.cached_values_raw[effect] = LightingLayer()
            mapped = universes.mapChannel(universe, channel)
            if not mapped:
                return
            u, c = mapped
            if not u or not c:
                return

            universeObj = universes.getUniverse(u)
            if not universeObj:
                return

            if value is None:
                if (
                    effect in self.cached_values_raw
                    and u in self.cached_values_raw[effect].values
                ):
                    self.cached_values_raw[effect].values[u][c] = 0
                    self.cached_values_raw[effect].alphas[u][c] = 0
                    self.refresh_generator_layout(effect)
            else:
                if u not in self.cached_values_raw[effect].values:
                    self.cached_values_raw[effect].values[u] = numpy.zeros(
                        len(universeObj.values)
                    )
                    self.cached_values_raw[effect].alphas[u] = numpy.zeros(
                        len(universeObj.values)
                    )

                    if u.startswith("/"):
                        self.on_demand_universes[u] = (
                            universes.get_on_demand_universe(u)
                        )
                self.cached_values_raw[effect].values[u][c] = value
                was_present = self.cached_values_raw[effect].alphas[u][c] > 0
                self.cached_values_raw[effect].alphas[u][c] = 1
                if not was_present:
                    self.refresh_generator_layout(effect)
                else:
                    idx = self.generators[effect].reverse_mapping.get((u, c))
                    if idx is not None:
                        self.generators[effect].input_data[idx] = value
                        self.generators[effect].set_input_value(idx, value)

            self.should_repaint_onto_universes[u] = True

    def refresh(self):
        """
        Recalculate all the lighting stuff, mark any universes we affect
        as needing to be rerendered fully.
        """
        self.next(self.cue)
        self.mark_need_repaint_onto_universes()

    # Only call this under the render lock
    def get_current_output(
        self, universes_cache: dict[str, universes.Universe]
    ) -> dict[str, LightingLayer]:
        fp = self.fade_position

        op = {}

        for i in self.cached_values_raw:
            v = self.cached_values_raw[i]

            if i in self.generators:
                for processed, mapping in zip(
                    self.generators[i].process(
                        time.time() - self.cue_start_time
                    ),
                    self.generators[i].channel_mapping,
                ):
                    if mapping:
                        if mapping[0] in v.values:
                            if mapping[1] < len(v.values[mapping[0]]):
                                v.values[mapping[0]][mapping[1]] = processed
                                v.alphas[mapping[0]][mapping[1]] = 1

            if i in self.fading_from:
                op[i] = self.fading_from[i].fade_in(v, fp, universes_cache)
            else:
                op[i] = LightingLayer().fade_in(v, fp, universes_cache)
        return op

    def mark_need_repaint_onto_universes(self, universe: str | None = None):
        # Make sure it's in a place where this will be noticed for at
        # least one rerender
        with render_loop_lock:
            if universe:
                self.should_repaint_onto_universes[universe] = True
                return

            for i in self.cached_values_raw:
                for j in self.cached_values_raw[i].values:
                    self.should_repaint_onto_universes[j] = True

            for i in self.fading_from:
                for j in self.fading_from[i].values:
                    self.should_repaint_onto_universes[j] = True

    def next(self, cue: Cue | None, fade_in: bool = False):
        """Handle lighting related cue transition stuff"""
        with self.group.lock:
            if not cue:
                return

            self.cue_start_time = time.time()

            if fade_in:
                self.fade_position = 0

            if cue.track and self.group.backtrack:
                backtracked = self.collect_backtracked_values(cue)
            else:
                backtracked = []

            with render_loop_lock:
                self.fading_from = {}
                # Because just assigning would make them the same obj and it would be all
                # corrupt
                for i in self.cached_values_raw:
                    self.fading_from[i] = LightingLayer(
                        self.cached_values_raw[i]
                    )
                if not cue.track:
                    self.cached_values_raw = {}

                reentering = self.cue is cue
                self.cue = cue

                if not reentering:
                    self.apply_backtracked_values(backtracked)

                # Recalc what universes are affected by this group.
                # We don't clear the old universes, we do that when we're done fading in.
                for effect in cue.lighting_effects:
                    for universe in effect["keypoints"]:
                        i = universes.mapUniverse(universe["target"])

                        if i and i.startswith("/"):
                            self.on_demand_universes[i] = (
                                universes.get_on_demand_universe(i)
                            )

                self.update_state_from_cue_vals(
                    cue.name,
                    copy.deepcopy(cue.lighting_effects),
                    clearBefore=not cue.track,
                )

                self.fade_in_completed = False

                self.mark_need_repaint_onto_universes()

    def stop(self):
        with render_loop_lock:
            for i in self.cached_values_raw:
                for j in self.cached_values_raw[i].values:
                    universes.request_rerender[j] = True

            self.fading_from = {}
            self.cached_values_raw = {}

            # Just using this to get rid of prev value
            self._blend = blendmodes.HardcodedBlendMode(self)

    def update_state_from_cue_vals(
        self,
        cuename: str,
        effect_data: list[EffectData],
        use_dynamic=True,
        clearBefore=False,
    ):
        """Apply everything from the cue to the fade canvas"""

        with render_loop_lock:
            # Loop over universes in the cue
            if clearBefore:
                # Rerender everything we no longer affect
                self.mark_need_repaint_onto_universes()
                self.cached_values_raw = {}
                self.generators = {}

            for effect in effect_data:
                if not (use_dynamic or effect["type"] == "direct"):
                    continue
                if effect["id"] not in self.cached_values_raw:
                    self.cached_values_raw[effect["id"]] = LightingLayer()

                effectlayer = self.cached_values_raw[effect["id"]]

                for kp in effect["keypoints"]:
                    use_suffix = "[" in kp["target"]
                    # If user does something like @fixture[0:10],
                    # then that means we're referring to an array of fixtures.
                    for spread_num in parse_interval(kp["target"]):
                        universe = universes.mapUniverse(
                            kp["target"]
                            + (f"[{spread_num}]" if use_suffix else "")
                        )
                        if not universe:
                            continue

                        universe_object = universes.getUniverse(universe)

                        if universe.startswith("/"):
                            self.on_demand_universes[universe] = (
                                universes.get_on_demand_universe(universe)
                            )
                            universe_object = self.on_demand_universes[universe]

                        if not universe_object:
                            continue

                        if universe not in self.cached_values_raw:
                            size = len(universe_object.values)
                            effectlayer.values[universe] = numpy.array(
                                [0.0] * size, dtype="f4"
                            )

                            effectlayer.alphas[universe] = numpy.array(
                                [0.0] * size, dtype="f4"
                            )

                        for j in kp["values"]:
                            if isinstance(j, str) and j.startswith("__"):
                                continue

                            cue_value = kp["values"][j]

                            x = universes.mapChannel(
                                kp["target"].split("[")[0], j
                            )
                            if x:
                                universe, channel = x[0], x[1]
                                try:
                                    effectlayer.values[universe][channel] = (
                                        cue_value
                                    )
                                    effectlayer.alphas[universe][channel] = (
                                        1.0 if cue_value is not None else 0
                                    )
                                except Exception:
                                    print("err", traceback.format_exc())

                                    self.group.event_background(
                                        "script.error",
                                        self.group.name
                                        + " cue "
                                        + cuename
                                        + " Val "
                                        + str((universe, channel))
                                        + "\n"
                                        + traceback.format_exc(),
                                    )
                self.refresh_generator_layout(effect["id"])

            for i in self.fading_from:
                if i not in self.cached_values_raw:
                    self.cached_values_raw[i] = LightingLayer()

    def fade_complete_cleanup(self):
        """Called when the fade is complete,
        to clean up leftover stuff we don't need"""
        # We no longer affect universes from the previous cue we are fading from

        # We did the fade, now if this is not a tracking
        # cue, we are going to no longer affect anything
        # That isn't directly in the cue
        with render_loop_lock:
            odu = {}

            for i in self.cached_values_raw:
                for j in self.cached_values_raw[i].values:
                    u = universes.mapUniverse(j)
                    if u and u.startswith("/"):
                        odu[u] = universes.get_on_demand_universe(j)

            self.on_demand_universes = odu
            self.fade_in_completed = True

    def collect_backtracked_values(
        self, destination_cue: Cue
    ) -> list[tuple[str, list[EffectData]]]:
        # When jumping to a cue that isn't directly the next one, apply and "parent" cues.
        # We go backwards until we find a cue that has no parent. A cue has a parent if and only if it has either
        # an explicit parent or the previous cue in the numbered list either has the default next cue or explicitly
        # references this cue.

        # Returns a dict of backtracked variables for
        # the script context that should be set when entering
        # this cue, but that is nit supported yet

        # Todo this holds group lock way too long
        to_apply = []
        with self.group.lock:
            if not self.cue:
                return to_apply

            new_cue = destination_cue.name

            if (
                self.group.backtrack
                # Track whenever the cue we are going to is not the next one in the numbering sequence
                and not new_cue == (self.group.getDefaultNext())
                and destination_cue.track
            ):
                seen = {}
                safety = 10000
                x = self.group.getParent(new_cue)
                while x:
                    # No l00ps
                    if x in seen:
                        break

                    # Don't backtrack past the current cue for no reason
                    if x == self.cue.name:
                        break

                    to_apply.append(
                        (
                            (self.group.cues[x].name),
                            copy.deepcopy(self.group.cues[x].lighting_effects),
                        )
                    )
                    seen[x] = True
                    x = self.group.getParent(x)
                    safety -= 1
                    if not safety:
                        break
        return to_apply

    def apply_backtracked_values(
        self, to_apply: list[tuple[str, list[EffectData]]]
    ):
        with render_loop_lock:
            # Apply all the lighting changes we would have seen if we had gone through the list one at a time.
            for c in reversed(to_apply):
                self.update_state_from_cue_vals(c[0], c[1], use_dynamic=False)

    def setup_blend_args(self):
        # Fill in defaults
        with render_loop_lock:
            for i in self._blend.blend_args:
                if i not in self.blend_args:
                    self.blend_args[i] = self._blend.blend_args[i]

            # Set the val
            self._blend.blend_args.update(self.blend_args)

    def setBlend(self, blend: str):
        with self.group.lock:
            with render_loop_lock:
                blend = str(blend)[:256]
                self.blend = blend
                if blend in blendmodes.blendmodes:
                    if self.group.is_active():
                        self._blend = blendmodes.blendmodes[blend](self)
                    self.blendClass = blendmodes.blendmodes[blend]
                    self.setup_blend_args()
                else:
                    self.blend_args = self.blend_args or {}
                    self._blend = blendmodes.HardcodedBlendMode(self)
                    self.blendClass = blendmodes.HardcodedBlendMode
                self.mark_need_repaint_onto_universes()

    def setBlendArg(self, key: str, val: float | bool | str):
        with self.group.lock:
            with render_loop_lock:
                if (
                    not hasattr(self.blendClass, "parameters")
                    or key not in self.blendClass.parameters
                ):
                    raise KeyError("No such param")

                if val is None:
                    del self.blend_args[key]
                else:
                    try:
                        val = float(val)
                    except Exception:
                        pass
                    self.blend_args[key] = val
                    self._blend.blend_args[key] = val
                self.mark_need_repaint_onto_universes()


def _composite(background, values, alphas, alpha):
    "In place compositing of one universe as a numpy array on a background.  Returns background."
    background = background * (1 - (alphas * alpha)) + values * alphas * alpha
    return background


def composite_rendered_layer_onto_universe(
    universe: str,
    group: Group,
    nl: LightingLayer,
    universe_object: universes.Universe,
):
    "May happen in place, or not, but always returns the new version"

    universe_values = universe_object.values

    if universe not in nl.values:
        return universe_values

    vals = nl.values[universe]
    alphas = nl.alphas[universe]

    # The universe may need to know when it's current fade should end,
    # if it handles fading in a different way.
    # This will look really bad for complex things, to try and reduce them to a series of fades,
    # but we just do the best we can, and assume there's mostly only 1 group at a time affecting things
    universe_object.fadeEndTime = max(
        universe_object.fadeEndTime, group.cue.fade_in + group.entered_cue
    )

    universe_alphas = universe_object.alphas

    bm = group.lighting_manager.blend

    if bm == "normal":
        # todo: is it bad to multiply by bool?
        unsetVals = universe_alphas == 0.0
        fade = numpy.maximum(
            group.alpha, unsetVals & universe_object.hueBlendMask
        )

        universe_values = _composite(universe_values, vals, alphas, fade)
        # Essentially calculate remaining light percent, then multiply layers and convert back to alpha
        universe_alphas = 1 - ((1 - (alphas * fade)) * (1 - (universe_alphas)))

    elif bm == "HTP":
        universe_values = numpy.maximum(
            universe_values, vals * (alphas * group.alpha)
        )
        universe_alphas = (alphas * group.alpha) > 0

    elif bm == "inhibit":
        universe_values = numpy.minimum(
            universe_values, vals * (alphas * group.alpha)
        )
        universe_alphas = (alphas * group.alpha) > 0

    elif bm == "gel" or bm == "multiply":
        if group.alpha:
            # precompute constants
            c = 255 / group.alpha
            universe_values = (universe_values * (1 - alphas * group.alpha)) + (
                universe_values * vals
            ) / c

            # COMPLETELY incorrect, but we don't use alpha for that much, and the real math
            # Is complicated. #TODO
            universe_alphas = (alphas * group.alpha) > 0

    elif group.lighting_manager._blend:
        try:
            universe_values = group.lighting_manager._blend.frame(
                universe, universe_values, vals, alphas, group.alpha
            )
            # Also incorrect-ish, but treating modified vals as fully opaque is good enough.
            universe_alphas = (alphas * group.alpha) > 0
        except Exception:
            print("Error in blend function")
            print(traceback.format_exc())
    universe_object.alphas = universe_alphas
    return universe_values


def composite_layers_from_board(
    board: ChandlerConsole, t=None, u=None, repaint=False
):
    """This is the primary rendering function.
    Returns dict of universes we know changes.

    Happens under the render loop lock
    """
    universesSnapshot = u or universes.getUniverses()
    # Getting list of universes is apparently slow, so we pass it as a param
    t = t or time.time()

    changed = {}

    needs_rerender = False

    for i in board.active_groups:
        if repaint:
            i.lighting_manager.mark_need_repaint_onto_universes()

        if i.lighting_manager.should_repaint_onto_universes:
            for j in i.lighting_manager.should_repaint_onto_universes:
                changed[j] = True
            needs_rerender = True

    if universes.request_rerender:
        for j in universes.request_rerender:
            changed[j] = True
        needs_rerender = True

    if not needs_rerender:
        return changed

    for u in universesSnapshot:
        if u in changed or u in universes.request_rerender:
            universesSnapshot[u].reset()

    universes.request_rerender.clear()

    # Remember that groups get rendered in ascending priority order here
    for i in board.active_groups:
        if i.blend == "monitor":
            continue

        # It takes a while to add and remove self from the active list.
        if not i.active:
            continue

        # TODO this can change size during iteration

        if i.lighting_manager.fade_in_completed:
            i.lighting_manager.should_repaint_onto_universes = {}

        x = i.lighting_manager.get_current_output(universesSnapshot).get(
            "default", LightingLayer()
        )

        # Loop over universes the group affects
        for u in x.values:
            # Leave universes with no changes in them alone
            if u not in changed:
                continue

            if u.startswith("__") and u.endswith("__"):
                continue

            if u not in universesSnapshot:
                continue

            universeObject = universesSnapshot[u]

            universeObject.values = composite_rendered_layer_onto_universe(
                u, i, x, universeObject
            )

    return changed


def do_output(changed, universesSnapshot):
    """Trigger all universes to actually output the frames.
    Need a snapshot list of universes because getting
    it is expensive according to profiler
    """
    for i in changed:
        try:
            if i in universesSnapshot:
                x = universesSnapshot[i]
                x.preFrame()
                x.onFrame()
        except Exception:
            raise
