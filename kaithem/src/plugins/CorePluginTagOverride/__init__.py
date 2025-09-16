# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later

import copy
import gc
import json
import time
from typing import Any
from urllib.parse import quote

import structlog

from kaithem.api import tags as tagsapi
from kaithem.api.web import dialogs
from kaithem.src import alerts, modules_state

logger = structlog.get_logger()

config_claims: dict[tuple[str, str], tagsapi.ClaimClass] = {}
config_alerts: dict[tuple[str, str], alerts.Alert] = {}

data_cache: dict[tuple[str, str], modules_state.ResourceDictType] = {}


class TagOverride(modules_state.ResourceType):
    def blurb(self, module, resource, data):
        t = tagsapi.existing_tag(data["tag"])
        if t:
            return f"""
            <div>
                <a href="/tagpoints/{quote(data['tag'])}">{data['tag']}</a><br>
                Overriding to value: {str(data["value"])[:64] }<br>
                Current value: {str(t.value)[:64] }<br>
                {data.get("notes", "")}
            </div>
            """

        return ""

    def on_load(self, module, resource, data):
        data_cache[module, resource] = data

        t = data["tag_type"]

        name = f"{module}:{resource}"

        if t == "numeric":
            tg = tagsapi.NumericTag(data["tag"])
            claim = tg.claim(
                value=float(data["value"]),
                name=name,
                priority=float(data["priority"]),
            )

        elif t == "string":
            tg = tagsapi.StringTag(data["tag"])
            claim = tg.claim(
                value=str(data["value"]),
                name=name,
                priority=float(data["priority"]),
            )
        elif t == "object":
            tg = tagsapi.ObjectTag(data["tag"])
            claim = tg.claim(
                value=data["value"],
                name=name,
                priority=float(data["priority"]),
            )
        else:
            raise ValueError(f"Bad tag type {t}")

        config_claims[module, resource] = claim

        config_alerts[module, resource] = alerts.Alert(
            str("Tag Override:" + data["tag"]),
            priority="warning",
            auto_ack=True,
        )

        config_alerts[module, resource].trip()

    def on_move(self, module, resource, to_module, to_resource, data):
        x = config_claims.pop((module, resource), None)
        if x:
            config_claims[to_module, to_resource] = x

        x2 = data_cache.pop((module, resource), None)
        if x2:
            data_cache[to_module, to_resource] = x2

    def on_update(self, module, resource, data):
        self.on_load(module, resource, data)

    def on_unload(self, module, resource, data):
        try:
            if (module, resource) in config_claims:
                config_claims[module, resource].release()
                del config_claims[module, resource]
        except KeyError:
            logger.error(
                "Failed to delete claim", module=module, resource=resource
            )

        try:
            if (module, resource) in config_alerts:
                config_alerts[module, resource].trip()
                config_alerts[module, resource].close()
                del config_alerts[module, resource]
        except KeyError:
            logger.error(
                "Failed to delete alert", module=module, resource=resource
            )

        for i in range(5):
            gc.collect()
            time.sleep(0.05)

    def on_create_request(self, module: str, resource: str, kwargs: dict):
        d: modules_state.ResourceDictType = {"resource": {"type": self.type}}
        d.update(kwargs)

        val = d.get("value", "")

        try:
            val = json.loads(val)
        except ValueError:
            pass

        d["value"] = val

        d.pop("name", None)
        d.pop("Save", None)

        return d

    def on_update_request(
        self, module, resource, data: modules_state.ResourceDictType, kwargs
    ):
        d: dict[str, Any] = copy.deepcopy(data)  # type: ignore

        d.update(kwargs)

        val = d.get("value", "")

        d["priority"] = float(d.get("priority", 51))

        try:
            val = json.loads(val)
        except ValueError:
            pass

        d["value"] = val

        d.pop("name", None)
        d.pop("Save", None)
        return d

    def validate(self, data):
        val: str = data.get("value", "")

        if data["tag_type"] == "numeric":
            float(val)
        elif data["tag_type"] == "object":
            json.loads(val)
        elif data["tag_type"] == "string":
            pass
        else:
            raise ValueError("Bad tag type: " + data["tag_type"])

    def tag_dialog(self, value, name=False):
        d = dialogs.SimpleDialog("Editing Tagpoint Override")

        d.text("""Here you can create an override claim to force a specific value on a tag point, even
               if something else wants to set it to something else.""")
        if name:
            d.text_input("name", title="Resource Name")

        tagname = value.get("tag", "")

        t = "numeric"

        try:
            tg = tagsapi.existing_tag(tagname)
            if tg:
                t = tg.type
        except Exception:
            pass  # pragma: no cover

        d.text_input(
            "tag",
            title="Tag Point Name",
            default=tagname,
            suggestions=[(i, i) for i in tagsapi.all_tags_raw().keys()],
        )
        d.selection(
            "tag_type",
            title="Tag Type",
            options=["numeric", "string", "object"],
            default=value.get(t, ""),
        )

        d.text_input(
            "priority", default=value.get("priority", 51), title="Priority"
        )

        d.text_input(
            "value", default=value.get("value", ""), title="Override Value"
        )

        d.checkbox(
            "alert",
            title="Alert warning while this override is active",
            default=value.get("alert", True),
        )

        d.text_input(
            "notes",
            title="Notes",
            default=value.get("notes", ""),
        )

        d.submit_button("Save")
        return d

    def create_page(self, module, path):
        d = self.tag_dialog({}, name=True)
        return d.render(self.get_create_target(module, path))

    def edit_page(self, module, resource, data):
        d = self.tag_dialog(data)
        return d.render(self.get_update_target(module, resource))


drt = TagOverride(
    "tag_override",
    mdi_icon="lock-open-alert-outline",
    priority=11,
    title="Tag Override",
)
modules_state.resource_types["tag_override"] = drt
