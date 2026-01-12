from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import groups

import time as _time

from scullery import workers

from kaithem.api import plugin_interfaces

from .. import scriptbindings
from . import core
from .global_actions import cl_event, cl_trigger_shortcut_code

rootContext = scriptbindings.ChandlerScriptContext()


class CueLogicStatelessFunction(scriptbindings.StatelessFunction):
    def get_parent_group(self) -> groups.Group:
        x: groups.DebugScriptContext = super().get_script_context()  # type: ignore
        y = x.parent_group()
        assert y
        return y


class GotoCommand(CueLogicStatelessFunction):
    doc = (
        "Triggers a group to go to a cue in the next frame. Repeat "
        "commands with same timestamp are ignored. Leave time blank "
        "to use current time."
    )
    args = [
        {"name": "group", "type": "GroupName", "default": "=GROUP"},
        {"name": "cue", "type": "CueName", "default": ""},
        {"name": "time", "type": "str", "default": "=event.time"},
    ]

    def call(self, group: str = "=GROUP", cue: str = "", time: float = 0):
        context_group = self.get_parent_group()
        entered_time = context_group.evalExpr(time) or _time.time()

        if not abs(float(entered_time) - _time.time()) < 60 * 5:
            raise ValueError("Timestamp sanity check failed")

        # Ignore empty
        if not cue.strip():
            return True

        # Track layers of recursion
        newcause = "script.0"
        if scriptbindings.context_info.event[0] in (
            "cue.enter",
            "cue.exit",
        ):
            cause = scriptbindings.context_info.event[1][1]
            # Nasty hack, but i don't thing we need more layers and
            # parsing might be slower.
            if cause == "script.0":
                newcause = "script.1"

            elif cause == "script.1":
                newcause = "script.2"

            elif cause == "script.2":
                newcause = "script.3"

            elif cause == "script.3":
                raise RuntimeError(
                    "Too many layers of triggers in cue.enter or cue.exit"
                )

        def f():
            context_group.board.groups_by_name[group].goto_cue(
                cue, cause=newcause, cue_entered_time=float(entered_time)
            )

        fn = context_group.board.groups_by_name[group].entered_cue_frame_number

        # If we just entered the cue, then defer to next frame
        # So goto_cue's wait doesn't block stuff
        if fn > core.completed_frame_number - 1:
            core.serialized_async_next_frame(f)
        else:
            core.serialized_async_with_core_lock(f)

        return True


class ShortcutCommand(CueLogicStatelessFunction):
    doc = (
        "Activates any cues with the matching shortcut code in any "
        "group. Triggers in the next frame."
    )
    args = [{"name": "code", "type": "str", "default": ""}]

    def call(self, code: str = ""):
        def f():
            cl_trigger_shortcut_code(code)

        core.serialized_async_next_frame(f)
        return True


class SetAlphaCommand(CueLogicStatelessFunction):
    doc = "Set the alpha value of a group. Action may not be immediate."
    args = [
        {"name": "group", "type": "str", "default": "=GROUP"},
        {"name": "alpha", "type": "float", "default": "1"},
    ]

    def call(self, group: str = "=GROUP", alpha: float = 1):
        context_group = self.get_parent_group()

        def f():
            context_group.board.groups_by_name[group].setAlpha(float(alpha))

        core.serialized_async_with_core_lock(f)
        return True


class IfCueCommand(CueLogicStatelessFunction):
    doc = "True if the group is running that cue"
    args = [
        {"name": "group", "type": "str", "default": ""},
        {"name": "cue", "type": "str", "default": ""},
    ]

    def call(self, group: str = "", cue: str = ""):
        context_group = self.get_parent_group()
        # not async so we can't use any locks for fear of deadlocks

        for i in range(5):
            try:
                return (
                    True
                    if context_group.board.groups_by_name[group].active
                    and context_group.board.groups_by_name[group].cue.name
                    == cue
                    else None
                )
            except Exception:
                pass

        return (
            True
            if context_group.board.groups_by_name[group].active
            and context_group.board.groups_by_name[group].cue.name == cue
            else None
        )


class EventCommand(CueLogicStatelessFunction):
    doc = (
        "Send an event to a group, or to all groups if group is "
        "__global__. Triggers in the next frame."
    )
    args = [
        {"name": "group", "type": "str", "default": "=GROUP"},
        {"name": "ev", "type": "str", "default": "DummyEvent"},
        {"name": "value", "type": "str", "default": ""},
    ]

    def call(
        self, group: str = "=GROUP", ev: str = "DummyEvent", value: str = ""
    ):
        context_group = self.get_parent_group()
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


class SetSlideshowVariableCommand(CueLogicStatelessFunction):
    doc = (
        "Set a slideshow variable. These can be used in the slideshow "
        "text as {{var_name}}"
    )
    args = [
        {"name": "group", "type": "str", "default": "=GROUP"},
        {"name": "key", "type": "str", "default": "varFoo"},
        {"name": "value", "type": "str", "default": ""},
    ]

    def call(self, group: str = "=GROUP", key: str = "varFoo", value: str = ""):
        context_group = self.get_parent_group()
        if not key.startswith("var"):
            raise ValueError(
                "Custom slideshow variable names for slideshow must "
                "start with 'var'"
            )
        context_group.board.groups_by_name[
            group
        ].media_link.set_slideshow_variable(key, value)
        return True


class ConsoleNotificationCommand(CueLogicStatelessFunction):
    doc = (
        "Send a notification to the operator, on the web editor and "
        "console pages"
    )
    args = [{"name": "text", "type": "str", "default": ""}]

    def call(self, text: str = ""):
        for board in core.iter_boards():
            if len(board.newDataFunctions) < 100:
                board.newDataFunctions.append(
                    lambda s: s.linkSend(["ui_alert", text])
                )


class SpeakCommand(CueLogicStatelessFunction):
    doc = (
        "BETA. Use the default text to speech model. Speaker is the "
        "number for multi-voice models."
    )
    args = [
        {"name": "text", "type": "str", "default": "Hello World!"},
        {"name": "speaker", "type": "str", "default": "0"},
        {"name": "speed", "type": "str", "default": "1"},
    ]

    def call(
        self, text: str = "Hello World!", speaker: str = "0", speed: str = "1"
    ):
        context_group = self.get_parent_group()

        def f():
            p = plugin_interfaces.TTSAPI.get_providers()[0]

            m = p.get_model()
            if m:
                m.speak(
                    str(text)[:1024],
                    speed=float(speed),
                    sid=int(speaker),
                    device=context_group.sound_output,
                    volume=context_group.cueVolume,
                )

        workers.do(f)


class SendMqttCommand(CueLogicStatelessFunction):
    doc = "JSON encodes message, and publishes it to the group's MQTT server"
    args = [
        {"name": "topic", "type": "str", "default": ""},
        {"name": "message", "type": "str", "default": ""},
    ]

    def call(self, topic: str = "", message: str = ""):
        raise RuntimeError(
            "This was supposed to be overridden by a group specific version"
        )


# Register global command instances
_goto_cmd = GotoCommand
_shortcut_cmd = ShortcutCommand
_set_alpha_cmd = SetAlphaCommand
_if_cue_cmd = IfCueCommand
_event_cmd = EventCommand
_set_slideshow_var_cmd = SetSlideshowVariableCommand
_console_notification_cmd = ConsoleNotificationCommand
_speak_cmd = SpeakCommand
_send_mqtt_cmd = SendMqttCommand

rootContext.commands["goto"] = _goto_cmd
rootContext.commands["shortcut"] = _shortcut_cmd
rootContext.commands["set_alpha"] = _set_alpha_cmd
rootContext.commands["if_cue"] = _if_cue_cmd
rootContext.commands["send_event"] = _event_cmd
rootContext.commands["set_slideshow_variable"] = _set_slideshow_var_cmd
rootContext.commands["console_notification"] = _console_notification_cmd
rootContext.commands["speak"] = _speak_cmd
rootContext.commands["send_mqtt"] = _send_mqtt_cmd


def add_context_commands(context_group: groups.Group):
    cc = {
        "goto": _goto_cmd,
        "shortcut": _shortcut_cmd,
        "set_alpha": _set_alpha_cmd,
        "if_cue": _if_cue_cmd,
        "send_event": _event_cmd,
        "set_slideshow_variable": _set_slideshow_var_cmd,
        "console_notification": _console_notification_cmd,
        "speak": _speak_cmd,
        "send_mqtt": _send_mqtt_cmd,
    }

    for i in cc:
        context_group.script_context.commands[i] = cc[i]

    context_group.command_refs = cc
