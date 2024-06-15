from kaithem.src.kaithemobj import kaithem

from . import core
from .global_actions import event, shortcutCode

rootContext = kaithem.chandlerscript.ChandlerScriptContext()


# Dummies just for the introspection
# TODO use the context commands thingy so we don't repeat this
def gotoCommand(group: str = "=GROUP", cue: str = ""):
    "Triggers a group to go to a cue.  Ends handling of any further bindings on the current event"


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


def eventCommand(group: str = "=GROUP", ev: str = "DummyEvent", value: str = ""):
    "Send an event to a group, or to all groups if group is __global__"


def setWebVarCommand(group: str = "=GROUP", key: str = "varFoo", value: str = ""):
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


def add_context_commands(context_group):
    cc = {}

    def gotoCommand(group: str = "=GROUP", cue: str = ""):
        "Triggers a group to go to a cue.  Ends handling of any further bindings on the current event"

        # Ignore empty
        if not cue.strip():
            return True

        # Track layers of recursion
        newcause = "script.0"
        if kaithem.chandlerscript.context_info.event[0] in ("cue.enter", "cue.exit"):
            cause = kaithem.chandlerscript.context_info.event[1][1]
            # Nasty hack, but i don't thing we need more layers and parsing might be slower.
            if cause == "script.0":
                newcause = "script.1"

            elif cause == "script.1":
                newcause = "script.2"

            elif cause == "script.2":
                raise RuntimeError("More than 3 layers of redirects in cue.enter or cue.exit")

        # We don't want to handle other bindings after a goto, leaving a group stops execution.
        context_group.board.groups_by_name[group].script_context.stopAfterThisHandler()
        context_group.board.groups_by_name[group].goto_cue(cue, cause=newcause)
        return True

    def codeCommand(code: str = ""):
        "Activates any cues with the matching shortcut code in any group"
        shortcutCode(code)
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
            True if context_group.board.groups_by_name[group].active and context_group.board.groups_by_name[group].cue.name == cue else None
        )

    def eventCommand(group: str = "=GROUP", ev: str = "DummyEvent", value: str = ""):
        "Send an event to a group, or to all groups if group is __global__"
        if group == "__global__":
            event(ev, value)
        else:
            context_group.board.groups_by_name[group].event(ev, value)
        return True

    def setWebVarCommand(group: str = "=GROUP", key: str = "varFoo", value: str = ""):
        "Set a slideshow variable. These can be used in the slideshow text as {{var_name}}"
        if not key.startswith("var"):
            raise ValueError("Custom slideshow variable names for slideshow must start with 'var' ")
        context_group.board.groups_by_name[group].media_link.set_slideshow_variable(key, value)
        return True

    def uiNotificationCommand(text: str):
        "Send a notification to the operator, on the web editor and console pages"
        for board in core.iter_boards():
            if len(board.newDataFunctions) < 100:
                board.newDataFunctions.append(lambda s: s.linkSend(["ui_alert", text]))

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
        raise RuntimeError("This was supposed to be overridden by a group specific version")

    cc["send_mqtt"] = sendMqttMessage
    for i in cc:
        context_group.script_context.commands[i] = cc[i]

    context_group.command_refs = cc
