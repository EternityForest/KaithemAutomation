from __future__ import annotations

import time
import traceback
from typing import TYPE_CHECKING, Any

import numpy
import numpy.typing

from . import blendmodes, universes

if TYPE_CHECKING:
    from .ChandlerConsole import ChandlerConsole
    from .groups import Cue, Group

from .core import iter_boards, render_loop_lock, serialized_async_with_core_lock
from .fadecanvas import FadeCanvas


def refresh_all_group_lighting():
    def f():
        for b in iter_boards():
            for i in b.groups:
                b.groups[i].refresh_lighting()

    serialized_async_with_core_lock(f)


class GroupLightingManager:
    def __init__(self, group: Group):
        """Functions of this class other than rerender() should only be called under the group's lock"""
        self.group = group

        # Canvas data can be read by the render loop at any time so must only
        # by changed with the render loop lock
        self.canvas = FadeCanvas()

        self.should_rerender_onto_universes = False

        # Track this so we can repaint
        self.last_fade_position = 1

        # Lets us cache the lists of values as numpy arrays with 0 alpha for not present vals
        # which are faster that dicts for some operations

        # These must only be mutated under the group's lock
        self.state_vals: dict[str, numpy.typing.NDArray[Any]] = {}
        self.state_alphas: dict[str, numpy.typing.NDArray[Any]] = {}
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

    def refresh(self):
        """
        Recalculate all the lighting stuff, mark any universes we affect
        as needing to be rerendered fully.
        """
        with self.group.lock:
            with render_loop_lock:
                try:
                    for i in self.state_vals:
                        universes.rerenderUniverse(i)
                except Exception:
                    print(traceback.format_exc())
            if self.cue:
                self.next(self.cue)
                self.paint_canvas(self.last_fade_position)

                # Set under lock to ensure it's in a place where it will be noticed
                # Not blown away at the end of the loop
                with render_loop_lock:
                    self.should_rerender_onto_universes = True

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
            self.canvas.save_current_as_background()

            # There might be universes we affect that we don't anymore,
            # We need to mark to rerender those because otherwise the system might think absolutely nothing has changed.
            # A full rerender on every cue change isn't the most efficient, but it shouldn't be too bad
            # since most frames don't have a cue change in them
            try:
                for i in self.state_vals:
                    universes.rerenderUniverse(i)
            except Exception:
                print(traceback.format_exc())

            reentering = self.cue is cue

            self.cue = cue

            if not reentering:
                if cue.track:
                    self.apply_backtracked_values(cue)

            # Recalc what universes are affected by this group.
            # We don't clear the old universes, we do that when we're done fading in.
            for i in cue.values:
                i = universes.mapUniverse(i)

                if i and i.startswith("/"):
                    self.on_demand_universes[i] = (
                        universes.get_on_demand_universe(i)
                    )

            self.update_state_from_cue_vals(cue, not cue.track)
            self.fade_in_completed = False

            self.rerender()

    def stop(self):
        with self.group.lock:
            # Tell them to rerender
            try:
                for i in self.state_vals:
                    universes.rerenderUniverse(i)
            except Exception:
                print(traceback.format_exc())

            self.state_vals = {}
            self.state_alphas = {}
            self.canvas.clean([])
            self.on_demand_universes = {}

            # Just using this to get rid of prev value
            self._blend = blendmodes.HardcodedBlendMode(self)

    def update_state_from_cue_vals(self, source_cue: Cue, clearBefore=False):
        """Apply everything from the cue to the fade canvas"""
        with self.group.lock:
            # Loop over universes in the cue
            if clearBefore:
                # self.cue_cached_vals_as_arrays = {}
                for i in self.state_alphas:
                    self.state_alphas[i] = numpy.zeros(
                        self.state_alphas[i].shape
                    )

            for i in source_cue.values:
                universe = universes.mapUniverse(i)
                if not universe:
                    continue

                fixture = None
                try:
                    if i[1:] in universes.fixtures:
                        f = universes.fixtures[i[1:]]()
                        if f:
                            fixture = f
                except KeyError:
                    print(traceback.format_exc())

                chCount = 0

                if fixture:
                    chCount = len(fixture.channels)

                if "__length__" in source_cue.values[i]:
                    s = source_cue.values[i]["__length__"]
                    assert s
                    repeats = int(self.group.evalExprFloat(s))
                else:
                    repeats = 1

                if "__spacing__" in source_cue.values[i]:
                    s = source_cue.values[i]["__spacing__"]
                    assert s
                    chCount = int(self.group.evalExprFloat(s))

                universe_object = universes.getUniverse(universe)

                if universe.startswith("/"):
                    self.on_demand_universes[i] = (
                        universes.get_on_demand_universe(universe)
                    )
                    universe_object = self.on_demand_universes[i]

                if not universe_object:
                    continue

                if universe not in self.state_vals:
                    size = len(universe_object.values)
                    self.state_vals[universe] = numpy.array(
                        [0.0] * size, dtype="f4"
                    )
                    self.state_alphas[universe] = numpy.array(
                        [0.0] * size, dtype="f4"
                    )

                self.rerenderOnVarChange = False

                # TODO stronger type
                dest: dict[str | int, Any] = {}

                for j in source_cue.values[i]:
                    if isinstance(j, str) and j.startswith("__dest__."):
                        dest[j[9:]] = self.group.evalExpr(
                            source_cue.values[i][j]
                            if source_cue.values[i][j] is not None
                            else 0
                        )

                for idx in range(repeats):
                    for j in source_cue.values[i]:
                        if isinstance(j, str) and j.startswith("__"):
                            continue

                        cue_values = source_cue.values[i][j]

                        evaled = self.group.evalExpr(
                            cue_values if cue_values is not None else 0
                        )
                        # This should always be a float
                        evaled = float(evaled)

                        # Do the blend thing
                        if j in dest:
                            # Repeats is a count, idx is zero based, we want diveder to be 1 on the last index of the set
                            divider = idx / (max(repeats - 1, 1))
                            evaled = (evaled * (1 - divider)) + (
                                dest[j] * divider
                            )

                        x = universes.mapChannel(i.split("[")[0], j)
                        if x:
                            universe, channel = x[0], x[1]
                            try:
                                self.state_alphas[universe][
                                    channel + (idx * chCount)
                                ] = 1.0 if cue_values is not None else 0
                                self.state_vals[universe][
                                    channel + (idx * chCount)
                                ] = evaled
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
                            cue_values, str
                        ) and cue_values.startswith("="):
                            self.rerenderOnVarChange = True

    def paint_canvas(self, fade_position: float = 0.0):
        assert self.cue
        # Group lock for state vals
        # Render loop lock for canvas
        with self.group.lock:
            with render_loop_lock:
                self.last_fade_position = fade_position

                self.canvas.paint(
                    fade_position,
                    vals=self.state_vals,
                    alphas=self.state_alphas,
                )

    def fade_complete(self):
        """Called when the fade is complete, to clean up leftover stuff we don't need"""
        # We no longer affect universes from the previous cue we are fading from

        # We did the fade, now if this is not a tracking
        # cue, we are going to no longer affect anything
        # That isn't directly in the cue
        with self.group.lock:
            if self.cue and not self.cue.track:
                current_affected = {}
                for i in self.cue.values:
                    m = universes.mapUniverse(i)
                    current_affected[m] = True

                to_delete = []
                for i in self.state_alphas:
                    if i not in current_affected:
                        to_delete.append(i)

                # These arrays should never be out of sync, this is just defensive
                for i in to_delete:
                    if i in self.state_alphas:
                        del self.state_alphas[i]
                    if i in self.state_vals:
                        del self.state_vals[i]

            # Clean up on demand universes

            odu = {}

            for i in self.state_vals:
                u = universes.mapUniverse(i)

                if u and u.startswith("/"):
                    odu[u] = universes.get_on_demand_universe(u)

            self.on_demand_universes = odu

            # Remove unused stuff from the canvas
            # State vals has all the tracked stuff already
            self.canvas.clean(self.state_vals)

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
    universe: str, group: Group, universe_object: universes.Universe
):
    "May happen in place, or not, but always returns the new version"

    universe_values = universe_object.values

    if universe not in group.lighting_manager.canvas.v2:
        return universe_values

    vals = group.lighting_manager.canvas.v2[universe]
    alphas = group.lighting_manager.canvas.a2[universe]

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


def mark_and_reset_changed_universes(
    board: ChandlerConsole, universes: dict[str, universes.Universe]
) -> dict[str, tuple[int, int]]:
    """
    Reset all universes to either the all 0s background or the cached layer, depending on if the cache layer is still valid
    This needs to happen before we start compositing on the layers.

    Here is also where we figure out what universes need to be fully rerendered
    """
    # Here we find out what universes can be reset to a cached layer and which need to be fully rerendered.
    changedUniverses = {}
    to_reset = {}

    # Important to reverse, that way groups that need a full reset come after and don't get overwritten
    for i in reversed(board.active_groups):
        for u in i.lighting_manager.canvas.v2:
            if u in universes:
                universe = universes[u]
                universe.all_static = True
                if (
                    i.lighting_manager.should_rerender_onto_universes
                    or i.lighting_manager.blendClass.always_rerender
                ):
                    changedUniverses[u] = (0, 0)

                    # We are below the cached layer, we need to fully reset
                    if (i.priority, i.started) <= universe.prerendered_layer:
                        to_reset[u] = 1
                    else:
                        # We are stacking on another layer or changing the top layer. We don't need
                        # To rerender the entire stack, we just start from the prerendered_layer
                        # Set the universe to the state it was in just after the prerendered layer was rendered.
                        # Since the values are mutable, we need to set this back every frame

                        # Don't overwrite a request to reset the entire thing
                        if not to_reset.get(u, 0) == 1:
                            to_reset[u] = 2
    for u in universes:
        if universes[u].full_rerender:
            to_reset[u] = 1

        universes[u].fadeEndTime = 0
        universes[u].interpolationTime = 0

    for u in to_reset:
        if (to_reset[u] == 1) or not universes[u].prerendered_layer[1]:
            universes[u].reset()
            changedUniverses[u] = (0, 0)
        else:
            universes[u].reset_to_cache()
            changedUniverses[u] = (0, 0)
    return changedUniverses


def composite_layers_from_board(board: ChandlerConsole, t=None, u=None):
    """This is the primary rendering function.
    Returns dict of universes we know changes.

    Happens under the render loop lock
    """
    universesSnapshot = u or universes.getUniverses()
    changedUniverses = {}
    # Getting list of universes is apparently slow, so we pass it as a param
    t = t or time.time()

    # Remember that groups get rendered in ascending priority order here
    for i in board.active_groups:
        if i.blend == "monitor":
            continue

        # It takes a while to add and remove self from the active list.
        if not i.active:
            continue

        # TODO this can change size during iteration
        data = i.lighting_manager.canvas.v2

        # Loop over universes the group affects
        for u in data:
            if u.startswith("__") and u.endswith("__"):
                continue

            if u not in universesSnapshot:
                continue

            universeObject = universesSnapshot[u]

            # If this is above the prerendered stuff we try to avoid doing every frame
            if (i.priority, i.started) > universeObject.top_layer:
                # If this layer we are about to render was found to be the highest layer that likely won't need rerendering,
                # Save the state just before we apply that layer.
                if (
                    universeObject.save_before_layer == (i.priority, i.started)
                ) and not ((i.priority, i.started) == (0, 0)):
                    universeObject.save_prerendered(
                        universeObject.top_layer[0], universeObject.top_layer[1]
                    )

                changedUniverses[u] = (i.priority, i.started)
                universeObject.values = composite_rendered_layer_onto_universe(
                    u, i, universeObject
                )
                universeObject.top_layer = (i.priority, i.started)

                # If this is the first nonstatic layer, meaning it's render function requested a rerender next frame
                # or if this is the last one, mark it as the one we should save just before
                if i.lighting_manager.should_rerender_onto_universes or (
                    i is board.active_groups[-1]
                ):
                    if universeObject.all_static:
                        # Copy it and set to none as a flag that we already found it
                        universeObject.all_static = False
                        universeObject.save_before_layer = (
                            universeObject.top_layer
                        )
        i.lighting_manager.should_rerender_onto_universes = False

    return changedUniverses


def do_output(changedUniverses, universesSnapshot):
    """Trigger all universes to actually output the frames.
    Need a snapshot list of universes because getting
    it is expensive according to profiler
    """
    for i in changedUniverses:
        try:
            if i in universesSnapshot:
                x = universesSnapshot[i]
                x.preFrame()
                x.onFrame()
        except Exception:
            raise

    for un in universesSnapshot:
        universesSnapshot[un].full_rerender = False
