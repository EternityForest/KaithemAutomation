from __future__ import annotations

import threading
import time
import uuid
from typing import Any

import quart

from kaithem.api.web.dialogs import SimpleDialog

lock = threading.Lock()

actions: dict[str, ModuleAction] = {}

action_types: dict[str, Any] = {}


class ModuleAction:
    title = "Module Action"

    def __init__(self, id: str, context: dict) -> None:
        self.id = id
        self.context = context
        self.last_interaction = time.time()

    def step(self, **kwargs) -> str | None:
        self.last_interaction = time.time()

    def close(self):
        with lock:
            actions.pop(self.id, None)
        return quart.redirect(f"/modules/module/{self.context['module']}/")

    def get_step_target(self):
        return f"/action_step/{self.id}"


def get_action(t: str, context={}):
    id = str(uuid.uuid4())

    with lock:
        if len(actions) > 2:
            for i in list(actions.keys()):
                if actions[i].last_interaction < time.time() - (5 * 60):
                    del actions[i]

        actions[id] = action_types[t](id, context)

        return actions[id]


def addConfigResource(module: str, resource: str, k: str, v: str):
    from kaithem.src import modules, modules_state

    if resource in modules_state.ActiveModules[module]:
        raise RuntimeError("Exists!")

    d = {"resource_type": "config", "data": {k: v}}
    d["config_priority"] = 50.0
    modules.createResource(module, resource, d)


class AddNavBarItemAction(ModuleAction):
    title = "Add a link to the nav bar"

    def step(self, **kwargs):
        if "title" not in kwargs:
            s = SimpleDialog("Add link to nav bar")
            s.text_input("url", title="URL")
            s.text(
                "List of usable icons: https://pictogrammers.com/library/mdi/"
            )
            s.text_input("icon", title="MDI Icon", default="circle-box")
            s.text_input("title")
            s.submit_button("Create")
            return s.render(self.get_step_target())

        else:
            r = kwargs["title"].lower().replace(" ", "_")
            r += "_navbar"

            v = (
                ("mdi-" + kwargs["icon"]).replace("mdi-mdi-", "mdi-")
                + " "
                + kwargs["title"]
                + " : "
                + kwargs["url"]
            )
            k = "/core/navbar_links/" + r

            addConfigResource(self.context["module"], r, k, v)

        super().step(**kwargs)
        self.close()


def add_action(cls):
    action_types[str(cls)] = cls


add_action(AddNavBarItemAction)
