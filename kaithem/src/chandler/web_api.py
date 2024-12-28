import datetime
import json

import quart.ctx
import quart.utils
import structlog
import yaml
from jsonschema import Draft202012Validator
from quart import request
from scullery import snake_compat

from kaithem.api.web import require, user

from .core import boards, cl_context
from .cue import cue_schema, cues
from .groups import checkPermissionsForGroupData, group_schema, groups
from .web import quart_app

logger = structlog.get_logger(__name__)


@quart_app.app.route("/chandler/api/delete-group/<board>/<group_id>")
async def delete_chandler_group(board: str, group_id: str):
    require("system_admin")
    x = groups[group_id]
    checkPermissionsForGroupData(x.toDict(), user())
    x.stop()
    board_obj = boards[board]
    board_obj.cl_del_group(group_id)

    return {"success": True}


@quart_app.app.route("/chandler/api/download/<type>/<board>")
async def download_chandler_file(type: str, board: str):
    require("chandler_operator")

    @quart.ctx.copy_current_request_context
    def f():
        with cl_context:
            b = boards[board]
            if type == "setup-file":
                f = b.cl_get_setup_file()
            if type == "library-file":
                f = b.cl_get_library_file()
            else:
                raise RuntimeError(f"Unknown type: {type}")

        return yaml.dump(f)

    r = await quart.utils.run_sync(f)()
    isodate = datetime.datetime.now().isoformat()

    return quart.Response(
        r,
        mimetype="text/yaml",
        headers={
            "Content-Disposition": f"attachment; filename={board}-setup-{isodate}.yaml"
        },
    )


@quart_app.app.route("/chandler/api/import-file/<board>", methods=["POST"])
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

        return quart.redirect(
            f"/chandler/config/c6d0887e-af6b-11ef-af85-5fc2044b2ae0/{board}"
        )

    return await f()


@quart_app.app.route("/chandler/api/all-cues/<board>")
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


@quart_app.app.route(
    "/chandler/api/set-cue-properties/<cue_id>", methods=["PUT"]
)
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


@quart_app.app.route(
    "/chandler/api/set-cue-value/<cue_id>/<universe>/<channel>",
    methods=["POST"],
)
async def set_cue_value_rest(cue_id: str, universe: str, channel: str | int):
    require("system_admin")
    v = json.loads(quart.request.args["value"])

    cue = cues[cue_id]
    group = cue.group()
    if group:
        board = group.board
        group.board.pushCueMeta(cue_id)
    else:
        raise RuntimeError("Cue has no group")

    # If it looks like an int, it should be an int.
    if isinstance(channel, str):
        try:
            channel = int(channel)
        except ValueError:
            pass

    if isinstance(v, str):
        try:
            v = float(v)
        except ValueError:
            pass

    cue.set_value_immediate(universe, channel, v)

    if v is None:
        # Count of values in the metadata changed
        board.pushCueMeta(cue_id)

    return {"success": True}


@quart_app.app.route(
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
