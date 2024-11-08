import copy
from typing import Any

from kaithem.src import dialogs, modules_state

from . import WebChandlerConsole, core

entries: dict[tuple[str, str], WebChandlerConsole.WebConsole] = {}

# Ensure that no Chandler function tries to call a modules function
# And risks a deadlock.
modules_state.modulesLock.opens_before(core.cl_context)


def set_save_cb(c: WebChandlerConsole.WebConsole, module: str, resource: str):
    def save(data: dict[str, Any]):
        r = modules_state.ActiveModules[module][resource]
        x: dict = copy.deepcopy(r)  # type: ignore
        if not data == x.get("project", {}):
            x["project"] = data
            modules_state.rawInsertResource(module, resource, x)

    c.ml_save_callback = save


class ConfigType(modules_state.ResourceType):
    def blurb(self, module, resource, data):
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

    def on_load(self, module, resource, data):
        data = copy.deepcopy(data)
        x = entries.pop((module, resource), None)
        entries[module, resource] = WebChandlerConsole.WebConsole(
            f"{module}:{resource}"
        )

        with core.cl_context:
            core.boards[f"{module}:{resource}"] = entries[module, resource]

            if x:
                x.cl_close()

            core.boards[f"{module}:{resource}"].cl_setup(
                data.get("project", {})
            )

        set_save_cb(entries[module, resource], module, resource)

    def on_move(self, module, resource, to_module, to_resource, data):
        x = entries.pop((module, resource), None)
        if x:
            entries[to_module, to_resource] = x

        with core.cl_context:
            b = core.boards.pop(f"{module}:{resource}", None)

            if b:
                b = core.boards[f"{to_module}:{to_resource}"] = b

        set_save_cb(entries[to_module, to_resource], to_module, to_resource)

    def on_update(self, module, resource, data):
        self.on_load(module, resource, data)

    def on_delete(self, module, resource, data):
        with core.cl_context:
            entries[module, resource].cl_close()
            core.boards.pop(f"{module}:{resource}", None)

        del entries[module, resource]

    def on_create_request(self, module, resource, kwargs):
        d = {"resource_type": self.type}
        return d

    def on_update_request(self, module, resource, data, kwargs):
        d = data
        kwargs.pop("name", None)
        kwargs.pop("Save", None)
        return d

    def create_page(self, module, path):
        d = dialogs.SimpleDialog("New Chandler Board")
        d.text_input("name", title="Resource Name")

        d.submit_button("Save")
        return d.render(self.get_create_target(module, path))

    def edit_page(self, module, resource, data):
        d = dialogs.SimpleDialog("Editing Config")
        d.text("Edit the board in the chandler UI")

        return d.render(self.get_update_target(module, resource))

    def flush_unsaved(self, module, resource):
        entries[module, resource].cl_check_autosave()
        return super().flush_unsaved(module, resource)


drt = ConfigType(
    "chandler_board", mdi_icon="castle", priority=60, title="Chandler Board"
)
modules_state.additionalTypes["chandler_board"] = drt
