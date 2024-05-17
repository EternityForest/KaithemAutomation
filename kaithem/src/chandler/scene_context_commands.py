from kaithem.src.kaithemobj import kaithem

from . import core
from .global_actions import event, shortcutCode


def add_context_commands(context_scene):
    cc = {}

    def gotoCommand(scene: str = "=SCENE", cue: str = ""):
        "Triggers a scene to go to a cue.  Ends handling of any further bindings on the current event"

        # Ignore empty
        if not cue.strip():
            return True

        # Track layers of recursion
        newcause = "script.0"
        if kaithem.chandlerscript.context_info.event[0] in ("cue.enter", "cue.exit"):
            cause = kaithem.chandlerscript.context_info.event[1][1]
            # Nast hack, but i don't thing we need more layers and parsing might be slower.
            if cause == "script.0":
                newcause = "script.1"

            elif cause == "script.1":
                newcause = "script.2"

            elif cause == "script.2":
                raise RuntimeError("More than 3 layers of redirects in cue.enter or cue.exit")

        # We don't want to handle other bindings after a goto, leaving a scene stops execution.
        context_scene.board.scenes_by_name[scene].script_context.stopAfterThisHandler()
        context_scene.board.scenes_by_name[scene].goto_cue(cue, cause=newcause)
        return True

    def codeCommand(code: str = ""):
        "Activates any cues with the matching shortcut code in any scene"
        shortcutCode(code)
        return True

    gotoCommand.completionTags = {  # type: ignore
        "scene": "gotoSceneNamesCompleter",
        "cue": "gotoSceneCuesCompleter",
    }

    def setAlphaCommand(scene: str = "=SCENE", alpha: float = 1):
        "Set the alpha value of a scene"
        context_scene.board.scenes_by_name[scene].setAlpha(float(alpha))
        return True

    def ifCueCommand(scene: str, cue: str):
        "True if the scene is running that cue"
        return (
            True if context_scene.board.scenes_by_name[scene].active and context_scene.board.scenes_by_name[scene].cue.name == cue else None
        )

    def eventCommand(scene: str = "=SCENE", ev: str = "DummyEvent", value: str = ""):
        "Send an event to a scene, or to all scenes if scene is __global__"
        if scene == "__global__":
            event(ev, value)
        else:
            context_scene.board.scenes_by_name[scene].event(ev, value)
        return True

    def setWebVarCommand(scene: str = "=SCENE", key: str = "varFoo", value: str = ""):
        "Set a slideshow variable. These can be used in the slideshow text as {{var_name}}"
        if not key.startswith("var"):
            raise ValueError("Custom slideshow variable names for slideshow must start with 'var' ")
        context_scene.board.scenes_by_name[scene].set_slideshow_variable(key, value)
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
        "JSON encodes message, and publishes it to the scene's MQTT server"
        raise RuntimeError("This was supposed to be overridden by a scene specific version")

    cc["send_mqtt"] = sendMqttMessage
    for i in cc:
        context_scene.script_context.commands[i] = cc[i]

    context_scene.command_refs = cc
