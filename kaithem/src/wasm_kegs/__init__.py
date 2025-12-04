from __future__ import annotations

import os
import struct
import tomllib
import uuid
import weakref
from typing import Any, TypeVar

import extism

from . import packages

_plugins_by_instance_id: weakref.WeakValueDictionary[str, PluginLoader] = (
    weakref.WeakValueDictionary()
)


def get_running_instance(plugin: extism.CurrentPlugin) -> PluginLoader:
    """If this is being called from the plugin,
    we can find out what plugin instance

    """
    return plugin.host_context()  # type: ignore


@extism.host_fn("keg_get_static_resource")
def keg_get_static_resource(
    current_plugin: extism.CurrentPlugin, path: str
) -> bytes:
    plugin = get_running_instance(current_plugin)

    package_dir = os.path.dirname(os.path.dirname(plugin.plugin_folder))
    return open(os.path.join(package_dir, "static", path), "rb").read()


class Payload:
    def __init__(self, data: bytes):
        self.data = data

    def read_i64(self) -> int:
        x = int.from_bytes(self.data[:8], "little")
        self.data = self.data[8:]
        return x

    def write_i64(self, x: int):
        self.data += x.to_bytes(8, "little")

    def read_f32(self) -> float:
        x = struct.unpack("<f", self.data[:4])[0]
        self.data = self.data[4:]
        return x

    def write_f32(self, x: float):
        self.data += struct.pack("<f", x)

    def write_bytes(self, x: bytes):
        self.write_i64(len(x))
        self.data += x

    def read_bytes(self) -> bytes:
        sz = self.read_i64()
        x = self.data[:sz]
        self.data = self.data[sz:]
        return x

    def read_string(self) -> str:
        return self.read_bytes().decode()

    def write_string(self, x: str):
        self.write_bytes(x.encode())


_LoaderTypeVar = TypeVar("_LoaderTypeVar")


class PluginLoader:
    """Must subclass to get a specific plugin type."""

    wasi = False

    plugin_type = ""

    @classmethod
    def get_running_instance(
        cls: type[_LoaderTypeVar], current_plugin: extism.CurrentPlugin
    ) -> _LoaderTypeVar:
        """A host_fn can define the first param as current_plugin: extism.CurrentPlugin,
        to be passed this.

        Thia is  host_context() wrapper that checks the type.
        """
        x = current_plugin.host_context()  # type: ignore
        if not isinstance(x, cls):
            raise RuntimeError(
                f"Plugin type mismatch, got {type(x)} but expected {cls}"
            )
        return x

    def call_plugin(self, name: str, data: Any) -> bytes:
        """Helper to make sure we always call with the right context"""
        return self.extism_plugin.call(name, data, host_context=self)

    def __init__(self, plugin: str, config: dict[str, Any]):
        p = packages.PackageStore().find_plugin(plugin)
        packagedir = os.path.dirname(p)

        print(f"Loading plugin {plugin} from {p}")

        self.plugin_folder: str = p

        _package, plugin = packages.parse_plugin_name(plugin)

        with open(
            os.path.join(os.path.dirname(packagedir), "keg.toml"), "rb"
        ) as f:
            manifest = tomllib.load(f)

        pl = manifest["plugins"]
        pm = None
        for i in pl:
            if i["name"] == plugin:
                pm = i
                break

        if pm is None:
            raise RuntimeError(f"Plugin {plugin} not found in keg.toml")

        if not pm["type"] == self.plugin_type:
            raise RuntimeError("Plugin type mismatch")

        p = os.path.join(p, "plugin.wasm")

        if not os.path.exists(p):
            raise RuntimeError(f"Plugin {p} not found")

        self.instance_id: str = str(uuid.uuid4())

        self.extism_plugin = extism.Plugin(p, wasi=self.wasi)

        if self.extism_plugin.function_exists("plugin_init"):
            self.call_plugin("plugin_init", b"")

        _plugins_by_instance_id[self.instance_id] = self
