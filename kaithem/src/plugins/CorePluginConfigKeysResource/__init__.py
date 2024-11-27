# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import copy
import time

from kaithem.src import dialogs, modules_state, settings_overrides


class Entries:
    def __init__(
        self, source: tuple[str, str], data, priority: float = 50
    ) -> None:
        self.data = copy.copy(data)
        self.source = source
        self.priority = priority

        self.ts = time.time()
        self.closed = False

        for i in self.data:
            settings_overrides.add_val(
                i,
                self.data[i],
                str(self.source) + str(id(self)),
                priority=priority,
            )

    def close(self):
        self.closed = True
        for i in self.data:
            # Handle nonetype while shutting down
            if settings_overrides:
                settings_overrides.add_val(
                    i,
                    "",
                    str(self.source) + str(id(self)),
                    priority=self.priority,
                )
        try:
            # Handle nuisance error at shutdown
            if entries is not None:
                del entries[self.source]
        except KeyError:
            pass
        except Exception:
            if entries is not None:
                raise

    def __del__(self):
        if not self.closed:
            self.close()


entries: dict[tuple[str, str], Entries] = {}


class ConfigType(modules_state.ResourceType):
    def on_load(self, module, resourcename, value):
        x = entries.pop((module, resourcename), None)
        x2 = Entries(
            (module, resourcename),
            value["data"],
            float(value.get("config_priority", 50)),
        )
        if x:
            x.close()
        entries[module, resourcename] = x2

    def on_move(self, module, resource, to_module, to_resource, resourceobj):
        x = entries.pop((module, resource), None)
        if x:
            entries[to_module, to_resource] = x

    def on_update(self, module, resource, obj):
        self.on_load(module, resource, obj)

    def on_delete(self, module, name, value):
        del entries[module, name]

    def on_create_request(self, module, name, kwargs):
        kwargs = dict(kwargs)
        pr = kwargs.pop("config_priority", "50")
        d = {
            "resource_type": self.type,
            "data": {kwargs["key"]: kwargs["value"]},
        }
        d["config_priority"] = float(pr.strip())

        return d

    def on_update_request(self, module, resource, resourceobj, kwargs):
        d = resourceobj
        kwargs = dict(kwargs)
        kwargs.pop("name", None)
        kwargs.pop("Save", None)

        n = kwargs.pop("_newkey", None)
        v = kwargs.pop("_newv", None)
        pr = kwargs.pop("config_priority")

        if n and v:
            d["data"][n] = v.strip()

        for i in kwargs:
            for c in r"""~!@#$%^&*()+`-=[]\{}|;':"',<>?""":
                if c in i:
                    raise ValueError(
                        f"Special char {c} is forbidden in keys: " + i
                    )

            if kwargs[i] and kwargs[i][0] == "=":
                raise ValueError("Values starting with = are reserved.")

        d["data"].update(kwargs)
        d["data"] = {
            i.strip(): d["data"][i].strip()
            for i in d["data"]
            if d["data"][i].strip()
        }

        d["config_priority"] = float(pr.strip())
        return d

    def create_page(self, module, path):
        d = dialogs.SimpleDialog("New Config Entries")
        d.text_input(
            "name",
            title="Resource Name",
            suggestions=[(i, i) for i in settings_overrides.list_keys()],
        )
        d.text_input("key", title="Config Key")
        d.text_input("value", title="Config Value", multiline=True)
        d.text_input("config_priority", title="Config Priority", default="50")

        d.submit_button("Save")
        return d.render(self.get_create_target(module, path))

    def edit_page(self, module, name, value):
        d = dialogs.SimpleDialog("Editing Config Entries")

        d.text("Empty the key field to delete an entry")

        suggestions = [(i, i) for i in settings_overrides.list_keys()]

        for i in sorted(list(value["data"].keys())):
            d.text_input(i, title=i, default=value["data"][i], multiline=True)
        d.text("")
        d.text_input(
            "config_priority",
            title="Config Priority",
            default=str(value.get("config-priority", "50")),
        )

        d.text_input("_newkey", title="Add New Key?", suggestions=suggestions)
        d.text_input("_newv", title="Value For New Key?", multiline=True)

        d.submit_button("Save")
        return d.render(self.get_update_target(module, name))


drt = ConfigType("config", mdi_icon="cog-outline")
modules_state.additionalTypes["config"] = drt
