# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

import gc
import time
from urllib.parse import quote

from kaithem.api import tags as tagsapi
from kaithem.api.web import dialogs
from kaithem.src import modules_state

config_tags: dict[tuple[str, str], tagsapi.GenericTagPointClass] = {}

data_cache: dict[tuple[str, str], modules_state.ResourceDictType] = {}


class TagType(modules_state.ResourceType):
    def blurb(self, m, r, value):
        t = tagsapi.existing_tag(value["tag"])
        if t:
            return f"""
            <div>
                <a href="/tagpoints/{quote(value['tag'])}">{value['tag']}</a><br>
                Value: {str(t.value)[:64] }
            </div>
            """

        return ""

    def onload(self, module, resourcename, value):
        data_cache[module, resourcename] = value

        t = value["tag_type"]

        if t == "numeric":
            tg = tagsapi.NumericTag(value["tag"])
            for i in ["min", "max", "hi", "lo", "default"]:
                if value.get(i, ""):
                    setattr(tg, i, float(value[i]))

        elif t == "string":
            tg = tagsapi.NumericTag(value["tag"])
            if value.get("default", ""):
                tg.default = float(value["default"])
        else:
            raise ValueError(f"Bad tag type {t}")
        if value.get("interval", ""):
            tg.interval = float(value.get("interval", "0"))

        alias = str(value.get("alias", "")).strip()

        if alias:
            if (module, resourcename) in data_cache:
                old = data_cache[module, resourcename]
                old_alias = str(old.get("alias", "")).strip()
                if old_alias and old_alias != alias:
                    tg.remove_alias(alias)

            tg.add_alias(value["alias"])

        config_tags[module, resourcename] = tg

    def onmove(self, module, resource, toModule, toResource, resourceobj):
        x = config_tags.pop((module, resource), None)
        if x:
            config_tags[toModule, toResource] = x

        x2 = data_cache.pop((module, resource), None)
        if x2:
            data_cache[toModule, toResource] = x2

    def onupdate(self, module, resource, obj):
        self.onload(module, resource, obj)

    def ondelete(self, module, name, value):
        del config_tags[module, name]
        for i in range(5):
            gc.collect()
            time.sleep(0.05)

    def oncreaterequest(self, module: str, name: str, kwargs: dict):
        d: modules_state.ResourceDictType = {"resource_type": self.type}
        d.update(kwargs)
        for i in ["hi", "lo", "min", "max", "interval"]:
            if d.get(i, ""):
                d[i] = float(d[i])  # type: ignore
        d.pop("name", None)
        d.pop("Save", None)

        return d

    def onupdaterequest(self, module, resource, resourceobj, kwargs):
        d = resourceobj
        d.update(kwargs)

        for i in ["hi", "lo", "min", "max", "interval"]:
            if d.get(i, ""):
                d[i] = float(d[i])

        d.pop("name", None)
        d.pop("Save", None)
        return d

    def validate(self, d: dict):
        if d["tag_type"] != "numeric":
            for i in ["hi", "lo", "min", "max"]:
                if str(d[i]).strip():
                    raise ValueError(f"Option {i} is only valid for numeric types")

        for i in ["hi", "lo", "min", "max", "interval"]:
            if d.get(i, ""):
                float(d[i])

    def tag_dialog(self, value, name=False):
        d = dialogs.SimpleDialog("Editing Tagpoint Resource")

        d.text("""Here you can create a new tag or apply setttings to an existing tag.
                However, if the same setting is set in multiple places, it is undefined which one 'wins' """)
        if name:
            d.text_input("name", title="Resource Name")

        d.text_input(
            "tag", title="Tag Point Name", default=value.get("tag", ""), suggestions=[(i, i) for i in tagsapi.all_tags_raw().keys()]
        )
        d.selection("tag_type", title="Tag Type", options=["numeric", "string"], default=value.get("numeric", ""))

        d.text_input("default", default=value.get("default", ""), title="Default Value")
        d.text_input("interval", default=value.get("interval", ""))

        d.text("Adding an alias lets you access it by a more convenient, shorter name")
        d.text_input("alias", default=value.get("alias", ""))

        d.text("Options for numeric tags only")

        d.text_input("min", default=value.get("min", ""))
        d.text_input("max", default=value.get("max", ""))

        d.text_input("hi", default=value.get("hi", ""))
        d.text_input("lo", default=value.get("lo", ""))

        d.submit_button("Save")
        return d

    def createpage(self, module, path):
        d = self.tag_dialog({}, name=True)
        return d.render(self.get_create_target(module, path))

    def editpage(self, module, name, value):
        d = self.tag_dialog(value)
        return d.render(self.get_update_target(module, name))


drt = TagType("tagpoint", mdi_icon="tag-multiple", priority=10)
modules_state.additionalTypes["tagpoint"] = drt
