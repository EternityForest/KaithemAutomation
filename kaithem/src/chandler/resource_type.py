import copy
from kaithem.src import modules_state
from kaithem.src import dialogs
from . import WebChandlerConsole
from . import core

entries: dict[tuple[str, str], WebChandlerConsole.WebConsole] = {}


def set_save_cb(c: WebChandlerConsole.WebConsole, module: str, resource: str):
    def save(data: dict):
        x = modules_state.ActiveModules[module][resource]

        x = copy.deepcopy(x)

        x["project"] = data

        modules_state.rawInsertResource(module, resource, x)

    c.save_callback = save

class ConfigType(modules_state.ResourceType):

    def blurb(self, module, resource, object):
        return f"""
        <div class="tool-bar">
            <a href="f"/chandler/editor/{module}:{resource}">
            Editor</a>

            <a href="f"/chandler/commander/{module}:{resource}">
            Commander</a>

            <a href="f"/chandler/editor/config{module}:{resource}">
            Fixtures Config</a>
        </div>
        """

    def onload(self, module, resourcename, value):
        x = entries.pop((module, resourcename), None)
        entries[module, resourcename] = WebChandlerConsole.WebConsole()
        set_save_cb(entries[module, resourcename], module, resourcename)
        core.boards[f"{module}:{resourcename}"] = entries[module, resourcename]

        if x:
            x.close()

        core.boards[f"{module}:{resourcename}"].setup(value.get('project',{}))

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
        d = dialogs.SimpleDialog("New Config Entries")
        d.text_input("name", title="Resource Name")

        d.submit_button("Save")
        return d.render(self.get_create_target(module, path))

    def editpage(self, module, name, value):
        d = dialogs.SimpleDialog("Editing Config Entries")
        d.text("Edit the board in the chandler UI")

        return d.render(self.get_update_target(module, name))


drt = ConfigType("chandler_board", mdi_icon="castle")
modules_state.additionalTypes["chandler_board"] = drt
