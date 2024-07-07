import json

import quart.ctx
from quart import request
from scullery import snake_compat

from .cue import cues
from .groups import groups
from .web import quart_app


@quart_app.app.route("/chandler/api/set-cue-properties/<cue_id>", methods=["PUT"])
async def set_cue_properties(cue_id: str):
    """Set all properties given in the form data.

    camelCase top level keys are converted to snake_case to that
    web code can use JS conventions.
    """

    kw = json.loads(await request.body)

    @quart.ctx.copy_current_request_context
    def f():
        for key in kw:
            val = kw[key]
            prop = snake_compat.camel_to_snake(key)
            # Generic setter for things that are just simple value sets.

            # Try to get the attr, to ensure that it actually exists.
            old = getattr(cues[cue_id], prop)

            setattr(cues[cue_id], prop, val)

            if not old == val:
                cue = cues[cue_id]
                group = cue.group()
                if group:
                    group.board.pushCueMeta(cue_id)

        return {"success": True}

    return await f()


@quart_app.app.route("/chandler/api/set-cue-properties/<group_id>", methods=["PUT"])
async def set_group_properties(group_id: str):
    """Set all properties given in the form data.

    camelCase top level keys are converted to snake_case to that
    web code can use JS conventions.
    """

    kw = json.loads(await request.body)

    @quart.ctx.copy_current_request_context
    def f():
        for key in kw:
            val = kw[key]
            prop = snake_compat.camel_to_snake(key)

            group = groups[group_id]
            # Generic setter for things that are just simple value sets.

            # Try to get the attr, to ensure that it actually exists.
            old = getattr(group, prop)

            setattr(group, prop, val)

            if not old == val:
                group.board.pushCueMeta(group_id)

        return {"success": True}

    return await f()
