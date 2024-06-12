from __future__ import annotations

import time
import traceback
from typing import TYPE_CHECKING, Any

import numpy
import numpy.typing

from . import blendmodes, universes

if TYPE_CHECKING:
    from .ChandlerConsole import ChandlerConsole
    from .scenes import Cue, Scene

from .fadecanvas import FadeCanvas


class SceneLightingManager:
    def __init__(self, scene: Scene):
        self.scene = scene
        self.canvas = FadeCanvas()

        self.should_rerender_onto_universes = False

        # Track this so we can repaint
        self.last_fade_position = 1

        # Lets us cache the lists of values as numpy arrays with 0 alpha for not present vals
        # which are faster that dicts for some operations
        self.state_vals: dict[str, numpy.typing.NDArray[Any]] = {}
        self.state_alphas: dict[str, numpy.typing.NDArray[Any]] = {}
        self.on_demand_universes: dict[str, universes.Universe] = {}

        self.cue: Cue | None = None

        # Place to stash a blend object for new blending mode
        # Hardcoded indicates that applyLayer reads the blend name and we
        # have hardcoded logic there
        self._blend: blendmodes.BlendMode = blendmodes.HardcodedBlendMode(self)
        self.blendClass: type[blendmodes.BlendMode] = blendmodes.HardcodedBlendMode
        self.blend_args: dict[str, float | int | bool | str] = scene.blend_args or {}

    def refresh(self):
        "Recalculate all the lighting stuff"
        if self.cue:
            self.next(self.cue)
            self.paint_canvas(self.last_fade_position)

    def recalc_cue_vals(self):
        """Call when you change a value in the cue"""
        assert self.cue
        self.update_state_from_cue_vals(self.cue, not self.cue.track)

    def next(self, cue: Cue):
        """Handle lighting related cue transition stuff"""

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

        # Recalc what universes are affected by this scene.
        # We don't clear the old universes, we do that when we're done fading in.
        for i in cue.values:
            i = universes.mapUniverse(i)

            if i and i.startswith("/"):
                self.on_demand_universes[i] = universes.get_on_demand_universe(i)

        self.update_state_from_cue_vals(cue, not cue.track)
        self.fade_in_completed = False

    def stop(self):
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

    def update_state_from_cue_vals(self, cuex: Cue, clearBefore=False):
        """Apply everything from the cue to the fade canvas"""
        # Loop over universes in the cue
        if clearBefore:
            # self.cue_cached_vals_as_arrays = {}
            for i in self.state_alphas:
                self.state_alphas[i] = numpy.zeros(self.state_alphas[i].shape)

        for i in cuex.values:
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

            if "__length__" in cuex.values[i]:
                s = cuex.values[i]["__length__"]
                assert s
                repeats = int(self.scene.evalExprFloat(s))
            else:
                repeats = 1

            if "__spacing__" in cuex.values[i]:
                s = cuex.values[i]["__spacing__"]
                assert s
                chCount = int(self.scene.evalExprFloat(s))

            uobj = universes.getUniverse(universe)

            if universe.startswith("/"):
                self.on_demand_universes[i] = universes.get_on_demand_universe(universe)
                uobj = self.on_demand_universes[i]

            if not uobj:
                continue

            if universe not in self.state_vals:
                size = len(uobj.values)
                self.state_vals[universe] = numpy.array([0.0] * size, dtype="f4")
                self.state_alphas[universe] = numpy.array([0.0] * size, dtype="f4")

            self.rerenderOnVarChange = False

            # TODO stronger type
            dest: dict[str | int, Any] = {}

            for j in cuex.values[i]:
                if isinstance(j, str) and j.startswith("__dest__."):
                    dest[j[9:]] = self.scene.evalExpr(cuex.values[i][j] if cuex.values[i][j] is not None else 0)

            for idx in range(repeats):
                for j in cuex.values[i]:
                    if isinstance(j, str) and j.startswith("__"):
                        continue

                    cuev = cuex.values[i][j]

                    evaled = self.scene.evalExpr(cuev if cuev is not None else 0)
                    # This should always be a float
                    evaled = float(evaled)

                    # Do the blend thing
                    if j in dest:
                        # Repeats is a count, idx is zero based, we want diveder to be 1 on the last index of the set
                        divider = idx / (max(repeats - 1, 1))
                        evaled = (evaled * (1 - divider)) + (dest[j] * divider)

                    x = universes.mapChannel(i.split("[")[0], j)
                    if x:
                        universe, channel = x[0], x[1]
                        try:
                            self.state_alphas[universe][channel + (idx * chCount)] = 1.0 if cuev is not None else 0
                            self.state_vals[universe][channel + (idx * chCount)] = evaled
                        except Exception:
                            print("err", traceback.format_exc())
                            self.scene.event(
                                "script.error",
                                self.scene.name + " cue " + cuex.name + " Val " + str((universe, channel)) + "\n" + traceback.format_exc(),
                            )

                    if isinstance(cuev, str) and cuev.startswith("="):
                        self.rerenderOnVarChange = True

    def paint_canvas(self, fade_position: float = 0.0):
        assert self.cue
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
        self.should_rerender_onto_universes = True

    def apply_backtracked_values(self, cobj: Cue) -> dict[str, Any]:
        # When jumping to a cue that isn't directly the next one, apply and "parent" cues.
        # We go backwards until we find a cue that has no parent. A cue has a parent if and only if it has either
        # an explicit parent or the previous cue in the numbered list either has the default next cue or explicitly
        # references this cue.

        # Returns a dict of backtracked variables for
        # the script context that should be set when entering
        # this cue, but that is nit supported yet

        cue = cobj.name

        vars: dict[str, Any] = {}

        if (
            self.scene.backtrack
            # Track whenever the cue we are going to is not the next one in the numbering sequence
            and not cue == (self.scene.getDefaultNext())
            and cobj.track
        ):
            to_apply = []
            seen = {}
            safety = 10000
            x = self.scene.getParent(cue)
            while x:
                # No l00ps
                if x in seen:
                    break

                # Don't backtrack past the current cue for no reason
                if x is self.cue:
                    break

                to_apply.append(self.scene.cues[x])
                seen[x] = True
                x = self.scene.getParent(x)
                safety -= 1
                if not safety:
                    break

            # Apply all the lighting changes we would have seen if we had gone through the list one at a time.
            for cuex in reversed(to_apply):
                self.update_state_from_cue_vals(cuex)

                # cuevars = self.cues[cue].values.get("__variables__", {})
                # for i in cuevars:
                #     try:
                #         vars[i] = (i, self.evalExpr(cuevars[i]))
                #     except Exception:
                #         print(traceback.format_exc())
                #         core.rl_log_exc("Error with cue variable " + i)

        return vars

    def setup_blend_args(self):
        # Fill in defaults
        for i in self._blend.blend_args:
            if i not in self.blend_args:
                self.blend_args[i] = self._blend.blend_args[i]

        # Set the val
        self._blend.blend_args.update(self.blend_args)

    def setBlend(self, blend: str):
        blend = str(blend)[:256]
        self.blend = blend
        if blend in blendmodes.blendmodes:
            if self.scene.is_active():
                self._blend = blendmodes.blendmodes[blend](self)
            self.blendClass = blendmodes.blendmodes[blend]
            self.setup_blend_args()
        else:
            self.blend_args = self.blend_args or {}
            self._blend = blendmodes.HardcodedBlendMode(self)
            self.blendClass = blendmodes.HardcodedBlendMode
        self.should_rerender_onto_universes = True

    def setBlendArg(self, key: str, val: float | bool | str):
        if not hasattr(self.blendClass, "parameters") or key not in self.blendClass.parameters:
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
        self.should_rerender_onto_universes = True


def _composite(background, values, alphas, alpha):
    "In place compositing of one universe as a numpy array on a background.  Returns background."
    background = background * (1 - (alphas * alpha)) + values * alphas * alpha
    return background


def composite_rendered_layer_onto_universe(universe, uvalues, scene, uobj):
    "May happen in place, or not, but always returns the new version"

    if universe not in scene.lighting_manager.canvas.v2:
        return uvalues

    vals = scene.lighting_manager.canvas.v2[universe]
    alphas = scene.lighting_manager.canvas.a2[universe]

    # The universe may need to know when it's current fade should end,
    # if it handles fading in a different way.
    # This will look really bad for complex things, to try and reduce them to a series of fades,
    # but we just do the best we can, and assume there's mostly only 1 scene at a time affecting things
    uobj.fadeEndTime = max(uobj.fadeEndTime, scene.cue.fade_in + scene.entered_cue)

    ualphas = uobj.alphas

    bm = scene.lighting_manager.blend

    if bm == "normal":
        # todo: is it bad to multiply by bool?
        unsetVals = ualphas == 0.0
        fade = numpy.maximum(scene.alpha, unsetVals & uobj.hueBlendMask)

        uvalues = _composite(uvalues, vals, alphas, fade)
        # Essetially calculate remaining light percent, then multiply layers and convert back to alpha
        ualphas = 1 - ((1 - (alphas * fade)) * (1 - (ualphas)))

    elif bm == "HTP":
        uvalues = numpy.maximum(uvalues, vals * (alphas * scene.alpha))
        ualphas = (alphas * scene.alpha) > 0

    elif bm == "inhibit":
        uvalues = numpy.minimum(uvalues, vals * (alphas * scene.alpha))
        ualphas = (alphas * scene.alpha) > 0

    elif bm == "gel" or bm == "multiply":
        if scene.alpha:
            # precompute constants
            c = 255 / scene.alpha
            uvalues = (uvalues * (1 - alphas * scene.alpha)) + (uvalues * vals) / c

            # COMPLETELY incorrect, but we don't use alpha for that much, and the real math
            # Is compliccated. #TODO
            ualphas = (alphas * scene.alpha) > 0

    elif scene.lighting_manager._blend:
        try:
            uvalues = scene.lighting_manager._blend.frame(universe, uvalues, vals, alphas, scene.alpha)
            # Also incorrect-ish, but treating modified vals as fully opaque is good enough.
            ualphas = (alphas * scene.alpha) > 0
        except Exception:
            print("Error in blend function")
            print(traceback.format_exc())
    uobj.alphas = ualphas
    return uvalues


def pre_render(board: ChandlerConsole, universes: dict[str, universes.Universe]):
    """
    Reset all universes to either the all 0s background or the cached layer, depending on if the cache layer is still valid
    This needs to happen before we start compositing on the layers.

    Here is also where we figure out what universes need to be fully rerendered
    """
    # Here we find out what universes can be reset to a cached layer and which need to be fully rerendered.
    changedUniverses = {}
    to_reset = {}

    # Important to reverse, that way scenes that need a full reset come after and don't get overwritten
    for i in reversed(board.active_scenes):
        for u in i.lighting_manager.canvas.v2:
            if u in universes:
                universe = universes[u]
                universe.all_static = True
                if i.lighting_manager.should_rerender_onto_universes or i.lighting_manager.blendClass.always_rerender:
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
    Returns dict of universes we know changes
    """
    universesSnapshot = u or universes.getUniverses()
    changedUniverses = {}
    # Getting list of universes is apparently slow, so we pass it as a param
    t = t or time.time()

    # Remember that scenes get rendered in ascending priority order here
    for i in board.active_scenes:
        if i.blend == "monitor":
            continue

        data = i.lighting_manager.canvas.v2

        # Loop over universes the scene affects
        for u in data:
            if u.startswith("__") and u.endswith("__"):
                continue

            if u not in universesSnapshot:
                continue

            universeObject = universesSnapshot[u]

            # If this is above the prerendered stuff we try to avoid doing every frame
            if (i.priority, i.started) > universeObject.top_layer:
                # If this layer we are about to render was found to be the highest layer that likely won't need rerendering,
                # Save the state just befor we apply that layer.
                if (universeObject.save_before_layer == (i.priority, i.started)) and not ((i.priority, i.started) == (0, 0)):
                    universeObject.save_prerendered(universeObject.top_layer[0], universeObject.top_layer[1])

                changedUniverses[u] = (i.priority, i.started)
                universeObject.values = composite_rendered_layer_onto_universe(u, universeObject.values, i, universeObject)
                universeObject.top_layer = (i.priority, i.started)

                # If this is the first nonstatic layer, meaning it's render function requested a rerender next frame
                # or if this is the last one, mark it as the one we should save just before
                if i.lighting_manager.should_rerender_onto_universes or (i is board.active_scenes[-1]):
                    if universeObject.all_static:
                        # Copy it and set to none as a flag that we already found it
                        universeObject.all_static = False
                        universeObject.save_before_layer = universeObject.top_layer
        i.lighting_manager.should_rerender_onto_universes = False

    return changedUniverses


def do_output(changedUniverses, universesSnapshot):
    """Trigger all universes to actually ouptu the frames.
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
