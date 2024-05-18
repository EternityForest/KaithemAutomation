import copy
from typing import Any

from kaithem.src import dialogs, modules_state

from . import WebChandlerConsole, core

entries: dict[tuple[str, str], WebChandlerConsole.WebConsole] = {}


def set_save_cb(c: WebChandlerConsole.WebConsole, module: str, resource: str):
    def save(data: dict[str, Any]):
        x = modules_state.ActiveModules[module][resource]

        x = copy.deepcopy(x)
        if not data == x.get("project", {}):
            x["project"] = data
            modules_state.rawInsertResource(module, resource, x)

    c.save_callback = save


class ConfigType(modules_state.ResourceType):
    def blurb(self, module, resource, object):
        return f"""
        <div class="tool-bar">
            <a href="/chandler/editor/{module}:{resource}">
            <span class="mdi mdi-pencil-box"></span>
            Editor</a>

            <a href="/chandler/commander/{module}:{resource}">
            <span class="mdi mdi-dance-ballroom"></span>
            Commander</a>

            <a href="/chandler/config/{module}:{resource}">
            <span class="mdi mdi-cog-outline"></span>
            Fixtures Config</a>
        </div>
        """

    def onload(self, module, resourcename, value):
        x = entries.pop((module, resourcename), None)
        entries[module, resourcename] = WebChandlerConsole.WebConsole(f"{module}:{resourcename}")
        set_save_cb(entries[module, resourcename], module, resourcename)
        core.boards[f"{module}:{resourcename}"] = entries[module, resourcename]

        if x:
            x.close()

        core.boards[f"{module}:{resourcename}"].setup(value.get("project", {}))

    def onmove(self, module, resource, toModule, toResource, resourceobj):
        x = entries.pop((module, resource), None)
        if x:
            entries[toModule, toResource] = x

        b = core.boards.pop(f"{module}:{resource}", None)

        if b:
            b = core.boards[f"{toModule}:{toResource}"] = b

        set_save_cb(entries[toModule, toResource], toModule, toResource)

    def onupdate(self, module, resource, obj):
        self.onload(module, resource, obj)

    def ondelete(self, module, name, value):
        entries[module, name].close()
        core.boards.pop(f"{module}:{name}", None)

        del entries[module, name]

    def oncreaterequest(self, module, name, kwargs):
        d = {"resource_type": self.type}
        return d

    def onupdaterequest(self, module, resource, resourceobj, kwargs):
        d = resourceobj
        kwargs.pop("name", None)
        kwargs.pop("Save", None)
        return d

    def createpage(self, module, path):
        d = dialogs.SimpleDialog("New Chandler Board")
        d.text_input("name", title="Resource Name")

        d.submit_button("Save")
        return d.render(self.get_create_target(module, path))

    def editpage(self, module, name, value):
        d = dialogs.SimpleDialog("Editing Config")
        d.text("Edit the board in the chandler UI")

        return d.render(self.get_update_target(module, name))

    def flush_unsaved(self, module, resource):
        entries[module, resource].check_autosave()
        return super().flush_unsaved(module, resource)


drt = ConfigType("chandler_board", mdi_icon="castle", priority=60, title="Chandler Board")
modules_state.additionalTypes["chandler_board"] = drt
