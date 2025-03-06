# Plugins

[Kaithemautomation Index](./README.md#kaithemautomation-index) / Plugins

> Auto-generated documentation for [plugins](../../../api/plugins.py) module.

- [Plugins](#plugins)
  - [PluginInterface](#plugininterface)
    - [PluginInterface.get_providers](#plugininterfaceget_providers)
  - [get_providers](#get_providers)
  - [register_plugin_interface](#register_plugin_interface)

## PluginInterface

[Show source in plugins.py:8](../../../api/plugins.py#L8)

#### Signature

```python
class PluginInterface(plugin_system.BasePluginInterface): ...
```

### PluginInterface.get_providers

[Show source in plugins.py:12](../../../api/plugins.py#L12)

Returns a list of objects that provide this class's service

#### Signature

```python
@classmethod
def get_providers(cls: type[T]) -> list[T]: ...
```

#### See also

- [T](#t)



## get_providers

[Show source in plugins.py:25](../../../api/plugins.py#L25)

Returns a list of modules that provide the named service,
as defined in the plugin_metadata.

Low level, instead use you should use the PluginInterface subclass's
get_providers()

#### Signature

```python
def get_providers(service: str) -> list[plugin_system.BasePluginInterface]: ...
```



## register_plugin_interface

[Show source in plugins.py:18](../../../api/plugins.py#L18)

Register a class as a plugin interface

#### Signature

```python
def register_plugin_interface(cls: type[PluginInterface]): ...
```

#### See also

- [PluginInterface](#plugininterface)