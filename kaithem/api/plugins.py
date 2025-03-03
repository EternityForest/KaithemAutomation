from typing import TypeVar

from kaithem.src import plugin_system

T = TypeVar("T", bound=plugin_system.BasePluginInterface)


class PluginInterface(plugin_system.BasePluginInterface):
    priority: int = -1
    service: str = ""

    @classmethod
    def get_providers(cls: type[T]) -> list[T]:
        """Returns a list of objects that provide this class's service"""
        return get_providers(cls.service)


def register_plugin_interface(cls: type[PluginInterface]):
    """Register a class as a plugin interface"""
    if not cls.service:
        raise ValueError("PluginInterface must have a service name")
    plugin_system.interfaces[cls.service] = cls


def get_providers(
    service: str,
) -> list[plugin_system.BasePluginInterface]:
    """
    Returns a list of modules that provide the named service,
    as defined in the plugin_metadata.

    Low level, instead use you should use the PluginInterface subclass's
    get_providers()
    """
    return plugin_system.get_providers(service)
