# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import copy
import time

import structlog
from scullery import messagebus

from kaithem.src import dialogs, modules_state, settings_overrides

logger = structlog.get_logger()


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
        # Only exists for defensive and nuisance reasons
        # pragma: no cover
        except Exception:
            if entries is not None:
                raise

    def __del__(self):
        if not self.closed:
            self.close()


entries: dict[tuple[str, str], Entries] = {}


class ConfigType(modules_state.ResourceType):
    def on_load(self, module, resource, data):
        x = entries.pop((module, resource), None)
        x2 = Entries(
            (module, resource),
            data["data"],
            float(data.get("config_priority", 50)),
        )
        if x:
            x.close()
        entries[module, resource] = x2

    def on_move(self, module, resource, to_module, to_resource, data):
        x = entries.pop((module, resource), None)
        if x:
            entries[to_module, to_resource] = x

    def on_update(self, module, resource, data):
        self.on_load(module, resource, data)

    def on_unload(self, module, resource, data):
        try:
            entries[module, resource].close()
        except Exception:
            logger.exception("Failed to close resource properly")

    def on_create_request(self, module, resource, kwargs):
        kwargs = dict(kwargs)
        pr = kwargs.pop("config_priority", "50")
        d = {
            "resource_type": self.type,
            "data": {kwargs["key"]: ""},
        }
        d["config_priority"] = float(pr.strip())

        return d

    def on_update_request(self, module, resource, data, kwargs):
        d = modules_state.mutable_copy_resource(data)
        kwargs = dict(kwargs)
        kwargs.pop("name", None)
        kwargs.pop("Save", None)

        new_key = kwargs.pop("_newkey", None)
        pr = kwargs.pop("config_priority")

        for i in kwargs:
            for c in r"""~!@#$%^&*()+`-=[]\{}|;':"',<>? """:
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

        # While creating new keys, we can have an empty value
        if new_key:
            if new_key not in d["data"]:
                d["data"][new_key] = ""
                self.set_edit_page_redirect("__repeat__")

        d["config_priority"] = float(pr.strip())
        return d

    def create_page(self, module, path):
        d = dialogs.SimpleDialog("New Config Entries")
        d.text_input(
            "name",
            title="Resource Name",
        )
        d.text_input(
            "key",
            title="Config Key",
            suggestions=[(i, i) for i in settings_overrides.list_keys()],
        )

        d.text_input("config_priority", title="Config Priority", default="50")

        d.submit_button("Save")
        return d.render(self.get_create_target(module, path))

    def edit_page(self, module, resource, data):
        d = dialogs.SimpleDialog("Editing Config Entries")

        d.text("Empty the key field to delete an entry")

        for i in sorted(list(data["data"].keys())):
            options = settings_overrides.suggestions_by_key.get(i, [])
            d.text_input(
                i,
                title=i,
                default=data["data"][i],
                multiline=True if not options else False,
                suggestions=options,
            )

        d.text("")
        d.text_input(
            "config_priority",
            title="Config Priority",
            default=str(data.get("config-priority", "50")),
        )

        suggestions = [(i, i) for i in settings_overrides.list_keys()]
        d.text_input("_newkey", title="Add New Key?", suggestions=suggestions)

        d.submit_button("Save")
        return d.render(self.get_update_target(module, resource))

    def on_finished_loading(self, module: str | None):
        messagebus.post_message("/system/config_loaded_from_resources", None)
        settings_overrides.config_loaded_from_resources = True
        return super().on_finished_loading(module)


drt = ConfigType("config", mdi_icon="cog-outline")
modules_state.resource_types["config"] = drt
