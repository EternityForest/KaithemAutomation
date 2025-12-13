import json
import uuid

import quart.ctx
import structlog
from jsonschema import Draft202012Validator
from quart import request
from scullery import snake_compat

from kaithem.api.web import quart_app, require

from .core import boards, cl_context
from .cue import EffectData, cue_schema, cues
from .generator_plugins import lighting_generators
from .groups import group_schema, groups

logger = structlog.get_logger(__name__)


@quart_app.route("/chandler/plugin-info")
def chandler_list_plugins():
    require("chandler_operator")

    x = {
        "kaithem.chandler.lighting-generator": lighting_generators,
    }

    return quart.Response(json.dumps(x), mimetype="application/json")


@quart_app.route("/chandler/api/go-to-cue-by-cue-id/<cue_id>", methods=["PUT"])
async def api_go_to_cue_by_cue_id(cue_id: str):
    require("system_admin")
    c = cues[cue_id]
    g = c.group()
    assert g
    g.goto_cue(c.name)
    return {"success": True}


@quart_app.route(
    "/chandler/api/go-to-cue-by-name/<group>/<cue_name>", methods=["PUT"]
)
async def api_go_to_cue_by_name(group: str, cue_name: str):
    require("system_admin")
    g = groups[group]
    g.goto_cue(cue_name)
    return {"success": True}


@quart_app.route("/chandler/api/group-go/<group_id>", methods=["PUT"])
async def group_go(group_id: str):
    require("system_admin")
    x = groups[group_id]
    x.go()
    return {"success": True}


@quart_app.route(
    "/chandler/api/refresh-group-cue-providers/<group_id>", methods=["PUT"]
)
async def refresh_group_cue_providers(group_id: str):
    require("system_admin")
    x = groups[group_id]
    x.refresh_cue_providers()
    return {"success": True}


@quart_app.route("/chandler/api/group-stop/<group_id>", methods=["PUT"])
async def group_stop(group_id: str):
    require("system_admin")
    x = groups[group_id]
    x.stop()
    return {"success": True}


@quart_app.route(
    "/chandler/api/delete-group/<board>/<group_id>", methods=["PUT"]
)
async def delete_chandler_group(board: str, group_id: str):
    require("system_admin")
    x = groups[group_id]
    x.stop()
    board_obj = boards[board]
    board_obj.cl_del_group(group_id)

    return {"success": True}


@quart_app.route("/chandler/api/import-file/<board>", methods=["PUT", "POST"])
async def import_setup(board: str):
    require("system_admin")

    form = await quart.request.form

    body = (await quart.request.files)["file"].read()

    @quart.ctx.copy_current_request_context
    def f():
        with cl_context:
            b = boards[board]

            b.cl_import_from_resource_file(
                body,
                fixture_types="fixture_types" in form,
                universes="universes" in form,
                fixture_assignments="fixture_assignments" in form,
                fixture_presets="fixture_presets" in form,
            )

        return quart.redirect(f"/chandler/config/{board}")

    return await f()


@quart_app.route("/chandler/api/all-cues/<board>")
async def all_cues(board: str):
    require("chandler_operator")

    @quart.ctx.copy_current_request_context
    def f():
        with cl_context:
            d = {}
            b = boards[board]

            for i in b.groups:
                for j in b.groups[i].cues:
                    c = b.groups[i].cues[j]
                    d[c.id] = c.get_ui_data()

        return json.dumps(d)

    return await f()


@quart_app.route("/chandler/api/set-cue-properties/<cue_id>", methods=["PUT"])
async def set_cue_properties(cue_id: str):
    """Set all properties given in the form data.

    camelCase top level keys are converted to snake_case to that
    web code can use JS conventions.
    """
    require("system_admin")

    kw = json.loads(await request.body)

    @quart.ctx.copy_current_request_context
    def f():
        for key in kw:
            val = kw[key]
            prop = snake_compat.camel_to_snake(key)

            # there are runtime only properties not in the schema
            # TODO maybe they should be in the schema too?
            if prop in cue_schema["properties"]:
                prop_schema = cue_schema["properties"][prop]
                # Todo do we really want to automatically do this?
                if prop_schema.get("type") == "string":
                    val = str(val)
                elif prop_schema.get("type") == "number":
                    val = float(val)
                elif prop_schema.get("type") == "integer":
                    val = int(val)
                elif prop_schema.get("type") == "boolean":
                    val = bool(val)

                validator = Draft202012Validator(prop_schema)
                if not validator.is_valid(val):
                    raise ValueError(f"Invalid value for cue {prop}: {val}")

            # Try to get the attr, to ensure that it actually exists.
            old = getattr(cues[cue_id], prop)

            setattr(cues[cue_id], prop, val)

            if not old == val:
                cue = cues[cue_id]
                group = cue.group()
                if group:
                    group.board.pushCueMeta(cue_id)

            if not getattr(cues[cue_id], prop) == val:
                pass
                # logger.warning(
                #     f"""User set property {prop} on cue {cue_id} to {val} but it was set to {getattr(cues[cue_id], prop)}"""
                # )

        return {"success": True}

    return await f()


@quart_app.route(
    "/chandler/api/set-cue-value/<cue_id>/<effect>/<universe>/<channel>",
    methods=["PUT"],
)
async def set_cue_value_rest(
    cue_id: str, effect: str, universe: str, channel: str
):
    require("system_admin")
    v = json.loads(quart.request.args["value"])

    cue = cues[cue_id]
    group = cue.group()
    if group:
        board = group.board
        group.board.pushCueMeta(cue_id)
    else:
        raise RuntimeError("Cue has no group")

    if isinstance(v, str):
        try:
            v = float(v)
        except ValueError:
            pass

    cue.set_value_immediate(effect, universe, channel, v)

    if v is None:
        # Count of values in the metadata changed
        board.pushCueData(cue_id)

    return {"success": True}


@quart_app.route(
    "/chandler/api/set-cue-keypoint-position/<cue_id>/<effect>/<universe>",
    methods=["PUT"],
)
async def set_cue_keypoint_position(cue_id: str, effect: str, universe: str):
    require("system_admin")
    cue = cues[cue_id]
    group = cue.group()
    if group:
        board = group.board
    else:
        raise RuntimeError("Cue has no group")

    if "position" in quart.request.args:
        v = json.loads(quart.request.args["position"])
        if v is not None:
            fx = cue.get_effect_by_id(effect)
            if fx:
                kp = cue.get_fixture_keypoint(effect, universe)
                if kp:
                    fx["keypoints"].remove(kp)
                    fx["keypoints"].insert(v, kp)

    board.pushCueData(cue_id)

    return {"success": True}


@quart_app.route(
    "/chandler/api/set-cue-keypoint-meta/<cue_id>/<effect>/<universe>/<channel>",
    methods=["PUT"],
)
async def set_cue_keypoint_meta(
    cue_id: str, effect: str, universe: str, key: str
):
    require("system_admin")
    cue = cues[cue_id]
    group = cue.group()
    if group:
        board = group.board
    else:
        raise RuntimeError("Cue has no group")

    if "value" in quart.request.args:
        v = json.loads(quart.request.args["value"])

        g = cue.getGroup()

        if g:
            g.set_cue_keypoint_key(cue_id, effect, universe, key, v)

    board.pushCueData(cue_id)

    return {"success": True}


@quart_app.route(
    "/chandler/api/set-cue-effect-meta/<cue_id>/<effect>",
    methods=["PUT"],
)
async def set_cue_effect_rest(cue_id: str, effect: str):
    require("system_admin")
    v = json.loads(quart.request.args["value"])

    cue = cues[cue_id]
    group = cue.group()
    if group:
        board = group.board
        group.board.pushCueMeta(cue_id)
    else:
        raise RuntimeError("Cue has no group")

    if not v:
        fx = cue.get_effect_by_id(effect)
        if fx:
            cue.lighting_effects.remove(fx)
            group.lighting_manager.refresh()
    else:
        with cl_context:
            x = cue.get_effect_by_id(effect)

            if not x:
                y: EffectData = {
                    "type": "direct",
                    "id": str(uuid.uuid4()),
                    "keypoints": [],
                    "config": {},
                }
                cue.lighting_effects.append(y)
                x = y

            x.update(v)
            group.lighting_manager.refresh()

    board.pushCueData(cue_id)

    return {"success": True}


@quart_app.route(
    "/chandler/api/set-group-properties/<group_id>", methods=["PUT"]
)
async def set_group_properties(group_id: str):
    """Set all properties given in the form data.

    camelCase top level keys are converted to snake_case to that
    web code can use JS conventions.
    """
    require("system_admin")

    kw = json.loads(await request.body)

    @quart.ctx.copy_current_request_context
    def f():
        for key in kw:
            val = kw[key]
            prop = snake_compat.camel_to_snake(key)

            if prop in group_schema["properties"]:
                prop_schema = group_schema["properties"][prop]
                # Todo do we really want to automatically do this?
                if prop_schema.get("type") == "string":
                    val = str(val).strip()
                elif prop_schema.get("type") == "number":
                    val = float(val)
                elif prop_schema.get("type") == "integer":
                    val = int(val)
                elif prop_schema.get("type") == "boolean":
                    val = bool(val)

                validator = Draft202012Validator(prop_schema)
                if not validator.is_valid(val):
                    raise ValueError(f"Invalid value for cue {prop}: {val}")

            group = groups[group_id]
            # Generic setter for things that are just simple value sets.

            # Try to get the attr, to ensure that it actually exists.
            old = getattr(group, prop)

            setattr(group, prop, val)

            if not old == val:
                group.board.push_group_meta(group_id)

        return {"success": True}

    return await f()
