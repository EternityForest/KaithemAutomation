from __future__ import annotations

import time
import traceback
from typing import TYPE_CHECKING, Any

import numpy

from . import blendmodes, universes

if TYPE_CHECKING:
    from kaithem.src.chandler.cue import EffectData

    from .ChandlerConsole import ChandlerConsole
    from .groups import Cue, Group

from .core import iter_boards, render_loop_lock, serialized_async_with_core_lock
from .fadecanvas import LightingLayer


def refresh_all_group_lighting():
    def f():
        for b in iter_boards():
            for i in b.groups:
                b.groups[i].refresh_lighting()

    serialized_async_with_core_lock(f)


class GroupLightingManager:
    def __init__(self, group: Group):
        """Functions of this class other than rerender()
        should only be called under the group's lock!!!!!
        """

        self.group = group

        self.should_rerender_onto_universes = False

        # Track this so we can repaint
        self.fade_position = 1.0

        # Should the group rerender every time there is a var change
        # in a script var?
        self.needs_rerender_on_var_change = False

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

    def clean(self):
        for i in list(self.cached_values_raw):
            self.cached_values_raw[i].clean()

    def set_value(
        self, effect: str, universe: str, channel: int, value: float | None
    ):
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
            self.cached_values_raw[effect].values[u][c] = 0
            self.cached_values_raw[effect].alphas[u][c] = 0
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
            self.cached_values_raw[effect].alphas[u][c] = 1

        self.should_rerender_onto_universes = True

    def refresh(self):
        """
        Recalculate all the lighting stuff, mark any universes we affect
        as needing to be rerendered fully.
        """
        with self.group.lock:
            if self.cue:
                self.next(self.cue)

                # Set under lock to ensure it's in a place where it will be noticed
                # Not blown away at the end of the loop
                with render_loop_lock:
                    self.should_rerender_onto_universes = True

    def get_current_output(self) -> dict[str, LightingLayer]:
        if self.fade_position:
            return self.cached_values_raw

        op = {}

        for i in self.cached_values_raw:
            if i in self.fading_from:
                op[i] = self.fading_from[i].fade_in(
                    self.fading_from[i], self.fade_position
                )
            else:
                op[i] = LightingLayer().fade_in(
                    self.cached_values_raw[i], self.fade_position
                )
        return op

    def rerender(self):
        """We have new data, but don't need to rerender from scratch
        like we would if we stopped affecting a universe and now it needs to revert to background
        """

        # Make sure it's in a place where this will be noticed for at
        # least one rerender
        with render_loop_lock:
            self.should_rerender_onto_universes = True

    def recalc_cue_vals(self):
        """Call when you change a value in the cue"""
        assert self.cue
        self.update_state_from_cue_vals(self.cue, not self.cue.track)

    def next(self, cue: Cue):
        """Handle lighting related cue transition stuff"""
        with self.group.lock:
            self.fading_from = self.cached_values_raw
            self.cached_values_raw = {}

            reentering = self.cue is cue

            self.cue = cue

            if not reentering:
                if cue.track:
                    self.apply_backtracked_values(cue)

            # Recalc what universes are affected by this group.
            # We don't clear the old universes, we do that when we're done fading in.
            for effectname in cue.values:
                effect: EffectData = cue.values[effectname]

                for universe in effect["keypoints"]:
                    i = universes.mapUniverse(universe)

                    if i and i.startswith("/"):
                        self.on_demand_universes[i] = (
                            universes.get_on_demand_universe(i)
                        )

            self.update_state_from_cue_vals(cue, not cue.track)
            self.fade_in_completed = False

            self.rerender()

    def stop(self):
        with self.group.lock:
            self.fading_from = {}
            self.cached_values_raw = {}

            # Just using this to get rid of prev value
            self._blend = blendmodes.HardcodedBlendMode(self)

    def update_state_from_cue_vals(self, source_cue: Cue, clearBefore=False):
        """Apply everything from the cue to the fade canvas"""
        with self.group.lock:
            # Loop over universes in the cue
            if clearBefore:
                self.cached_values_raw = {}

            self.needs_rerender_on_var_change = False

            for effectname in source_cue.values:
                effect = source_cue.values[effectname]
                kp: dict[str, Any] = effect["keypoints"]  # type: ignore

                if effectname not in self.cached_values_raw:
                    self.cached_values_raw[effectname] = LightingLayer()

                effectlayer = self.cached_values_raw[effectname]

                for universe_raw_name in kp:
                    universe = universes.mapUniverse(universe_raw_name)
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

                        effectlayer.values[universe] = numpy.array(
                            [0.0] * size, dtype="f4"
                        )

                    for j in kp[universe_raw_name]:
                        if isinstance(j, str) and j.startswith("__"):
                            continue

                        cue_value = kp[universe_raw_name][j]

                        evaled = self.group.evalExpr(
                            cue_value if cue_value is not None else 0
                        )
                        # This should always be a float
                        evaled = float(evaled)

                        x = universes.mapChannel(
                            universe_raw_name.split("[")[0], j
                        )
                        if x:
                            universe, channel = x[0], x[1]
                            try:
                                effectlayer.values[universe][channel] = evaled
                                effectlayer.alphas[universe][channel] = (
                                    1.0 if cue_value is not None else 0
                                )
                            except Exception:
                                print("err", traceback.format_exc())
                                self.group.event(
                                    "script.error",
                                    self.group.name
                                    + " cue "
                                    + source_cue.name
                                    + " Val "
                                    + str((universe, channel))
                                    + "\n"
                                    + traceback.format_exc(),
                                )

                        if isinstance(
                            cue_value, str
                        ) and cue_value.strip().startswith("="):
                            self.needs_rerender_on_var_change = True

            for i in self.fading_from:
                if i not in self.cached_values_raw:
                    self.cached_values_raw[i] = LightingLayer()

    def fade_complete(self):
        """Called when the fade is complete, to clean up leftover stuff we don't need"""
        # We no longer affect universes from the previous cue we are fading from

        # We did the fade, now if this is not a tracking
        # cue, we are going to no longer affect anything
        # That isn't directly in the cue
        with self.group.lock:
            odu = {}

            for i in self.cached_values_raw:
                u = universes.mapUniverse(i)

                if u and u.startswith("/"):
                    odu[u] = universes.get_on_demand_universe(u)

            self.on_demand_universes = odu

            # One last rerender, this was some kind of bug workaround
            self.fade_in_completed = True
            self.rerender()

    def apply_backtracked_values(self, destination_cue: Cue) -> dict[str, Any]:
        # When jumping to a cue that isn't directly the next one, apply and "parent" cues.
        # We go backwards until we find a cue that has no parent. A cue has a parent if and only if it has either
        # an explicit parent or the previous cue in the numbered list either has the default next cue or explicitly
        # references this cue.

        # Returns a dict of backtracked variables for
        # the script context that should be set when entering
        # this cue, but that is nit supported yet

        with self.group.lock:
            assert self.cue

            new_cue = destination_cue.name

            vars: dict[str, Any] = {}

            if (
                self.group.backtrack
                # Track whenever the cue we are going to is not the next one in the numbering sequence
                and not new_cue == (self.group.getDefaultNext())
                and destination_cue.track
            ):
                to_apply = []
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

                    to_apply.append(self.group.cues[x])
                    seen[x] = True
                    x = self.group.getParent(x)
                    safety -= 1
                    if not safety:
                        break

                # Apply all the lighting changes we would have seen if we had gone through the list one at a time.
                for c in reversed(to_apply):
                    self.update_state_from_cue_vals(c)

            return vars

    def setup_blend_args(self):
        # Fill in defaults
        for i in self._blend.blend_args:
            if i not in self.blend_args:
                self.blend_args[i] = self._blend.blend_args[i]

        # Set the val
        self._blend.blend_args.update(self.blend_args)

    def setBlend(self, blend: str):
        with self.group.lock:
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
            self.rerender()

    def setBlendArg(self, key: str, val: float | bool | str):
        with self.group.lock:
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
            self.rerender()


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


def composite_layers_from_board(board: ChandlerConsole, t=None, u=None):
    """This is the primary rendering function.
    Returns dict of universes we know changes.

    Happens under the render loop lock
    """
    universesSnapshot = u or universes.getUniverses()
    # Getting list of universes is apparently slow, so we pass it as a param
    t = t or time.time()

    changed = {}

    needs_rerender = False

    group_outputs: dict[str, LightingLayer] = {}

    for i in board.active_groups:
        if i.lighting_manager.should_rerender_onto_universes:
            x = i.lighting_manager.get_current_output().get(
                "default", LightingLayer()
            )
            for j in x.values:
                changed[j] = True
            group_outputs[i.name] = x
            needs_rerender = True

    if not needs_rerender:
        return changed

    for u in universesSnapshot:
        universesSnapshot[u].reset()

    # Remember that groups get rendered in ascending priority order here
    for i in board.active_groups:
        if i.blend == "monitor":
            continue

        # It takes a while to add and remove self from the active list.
        if not i.active:
            continue

        # TODO this can change size during iteration

        # Loop over universes the group affects
        for u in group_outputs[i.name].values:
            if u.startswith("__") and u.endswith("__"):
                continue

            if u not in universesSnapshot:
                continue

            universeObject = universesSnapshot[u]

            universeObject.values = composite_rendered_layer_onto_universe(
                u, i, group_outputs[i.name], universeObject
            )

        i.lighting_manager.should_rerender_onto_universes = False

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
