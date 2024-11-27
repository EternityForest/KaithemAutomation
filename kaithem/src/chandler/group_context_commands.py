from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import groups

import time as _time

from kaithem.src.kaithemobj import kaithem

from . import core
from .global_actions import cl_event, cl_trigger_shortcut_code

rootContext = kaithem.chandlerscript.ChandlerScriptContext()


# Dummies just for the introspection
# TODO use the context commands thingy so we don't repeat this
def gotoCommand(group: str = "=GROUP", cue: str = "", time="=event.time"):
    """Triggers a group to go to a cue in the next frame.
    Repeat commands with same timestamp are ignored. Leave time blank
    to use current time."""


def codeCommand(code: str = ""):
    "Activates any cues with the matching shortcut code in any group"


gotoCommand.completionTags = {  # type: ignore
    "group": "gotoGroupNamesCompleter",
    "cue": "gotoGroupCuesCompleter",
}


def setAlphaCommand(group: str = "=GROUP", alpha: float = 1):
    "Set the alpha value of a group"


def ifCueCommand(group: str, cue: str):
    "True if the group is running that cue"


def eventCommand(
    group: str = "=GROUP", ev: str = "DummyEvent", value: str = ""
):
    "Send an event to a group, or to all groups if group is __global__"


def setWebVarCommand(
    group: str = "=GROUP", key: str = "varFoo", value: str = ""
):
    "Set a slideshow variable. These can be used in the slideshow text as {{var_name}}"


def uiNotificationCommand(text: str):
    "Send a notification to the operator, on the web editor and console pages"


rootContext.commands["shortcut"] = codeCommand
rootContext.commands["goto"] = gotoCommand
rootContext.commands["set_alpha"] = setAlphaCommand
rootContext.commands["if_cue"] = ifCueCommand
rootContext.commands["send_event"] = eventCommand
rootContext.commands["set_slideshow_variable"] = setWebVarCommand
rootContext.commands["console_notification"] = uiNotificationCommand


def sendMqttMessage(topic: str, message: str):
    "JSON encodes message, and publishes it to the group's MQTT server"


rootContext.commands["send_mqtt"] = sendMqttMessage


def add_context_commands(context_group: groups.Group):
    cc = {}

    def gotoCommand(group: str = "=GROUP", cue: str = "", time="=event.time"):
        """Triggers a group to go to a cue in the next frame.
        Repeat commands with same timestamp are ignored. Leave time blank
        to use current time."""

        time = context_group.evalExpr(time) or _time.time()

        if not abs(float(time) - _time.time()) < 60 * 5:
            raise ValueError("Timestamp sanity check failed")

        # Ignore empty
        if not cue.strip():
            return True

        # Track layers of recursion
        newcause = "script.0"
        if kaithem.chandlerscript.context_info.event[0] in (
            "cue.enter",
            "cue.exit",
        ):
            cause = kaithem.chandlerscript.context_info.event[1][1]
            # Nasty hack, but i don't thing we need more layers and parsing might be slower.
            if cause == "script.0":
                newcause = "script.1"

            elif cause == "script.1":
                newcause = "script.2"

            elif cause == "script.2":
                raise RuntimeError(
                    "More than 3 layers of redirects in cue.enter or cue.exit"
                )

        def f():
            context_group.board.groups_by_name[group].goto_cue(
                cue, cause=newcause, cue_entered_time=float(time)
            )

        fn = context_group.board.groups_by_name[group].entered_cue_frame_number

        # If we just entered the cue, then defer to next frame
        # So goto_cue's wait doesn't block stuff
        if fn > core.completed_frame_number - 1:
            core.serialized_async_next_frame(f)
        else:
            core.serialized_async_with_core_lock(f)

        return True

    def codeCommand(code: str = ""):
        "Activates any cues with the matching shortcut code in any group. Triggers in the next frame."

        def f():
            cl_trigger_shortcut_code(code)

        core.serialized_async_next_frame(f)
        return True

    gotoCommand.completionTags = {  # type: ignore
        "group": "gotoGroupNamesCompleter",
        "cue": "gotoGroupCuesCompleter",
    }

    def setAlphaCommand(group: str = "=GROUP", alpha: float = 1):
        "Set the alpha value of a group"
        context_group.board.groups_by_name[group].setAlpha(float(alpha))
        return True

    def ifCueCommand(group: str, cue: str):
        "True if the group is running that cue"
        return (
            True
            if context_group.board.groups_by_name[group].active
            and context_group.board.groups_by_name[group].cue.name == cue
            else None
        )

    def eventCommand(
        group: str = "=GROUP", ev: str = "DummyEvent", value: str = ""
    ):
        "Send an event to a group, or to all groups if group is __global__. Triggers in the next frame."
        t = _time.time()
        if group == "__global__":

            def f():
                cl_event(ev, value, ts=t)

            core.serialized_async_with_core_lock(f)
        else:

            def f():
                context_group.board.groups_by_name[group].event(ev, value, ts=t)

            core.serialized_async_with_core_lock(f)

        return True

    def setWebVarCommand(
        group: str = "=GROUP", key: str = "varFoo", value: str = ""
    ):
        "Set a slideshow variable. These can be used in the slideshow text as {{var_name}}"
        if not key.startswith("var"):
            raise ValueError(
                "Custom slideshow variable names for slideshow must start with 'var' "
            )
        context_group.board.groups_by_name[
            group
        ].media_link.set_slideshow_variable(key, value)
        return True

    def uiNotificationCommand(text: str):
        "Send a notification to the operator, on the web editor and console pages"
        for board in core.iter_boards():
            if len(board.newDataFunctions) < 100:
                board.newDataFunctions.append(
                    lambda s: s.linkSend(["ui_alert", text])
                )

    cc["shortcut"] = codeCommand
    cc["goto"] = gotoCommand
    cc["set_alpha"] = setAlphaCommand
    cc["if_cue"] = ifCueCommand
    cc["send_event"] = eventCommand
    cc["set_slideshow_variable"] = setWebVarCommand
    cc["console_notification"] = uiNotificationCommand

    # cc["set_tag"].completionTags = {"tagName": "tagPointsCompleter"}

    def sendMqttMessage(topic: str, message: str):
        "JSON encodes message, and publishes it to the group's MQTT server"
        raise RuntimeError(
            "This was supposed to be overridden by a group specific version"
        )

    cc["send_mqtt"] = sendMqttMessage
    for i in cc:
        context_group.script_context.commands[i] = cc[i]

    context_group.command_refs = cc
