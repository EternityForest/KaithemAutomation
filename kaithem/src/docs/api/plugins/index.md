# kaithem.api.plugins

## Attributes

| [`T`](#kaithem.api.plugins.T)   |    |
|---------------------------------|----|

## Classes

| [`PluginInterface`](#kaithem.api.plugins.PluginInterface)   |    |
|-------------------------------------------------------------|----|

## Functions

| [`register_plugin_interface`](#kaithem.api.plugins.register_plugin_interface)(cls)   | Register a class as a plugin interface                    |
|--------------------------------------------------------------------------------------|-----------------------------------------------------------|
| [`get_providers`](#kaithem.api.plugins.get_providers)(...)                           | Returns a list of modules that provide the named service, |

## Module Contents

### kaithem.api.plugins.T

### *class* kaithem.api.plugins.PluginInterface

Bases: [`kaithem.src.plugin_system.BasePluginInterface`](../../src/plugin_system/index.md#kaithem.src.plugin_system.BasePluginInterface)

#### priority *: int* *= -1*

#### service *: str* *= ''*

#### *classmethod* get_providers() → list[T]

Returns a list of objects that provide this class's service

### kaithem.api.plugins.register_plugin_interface(cls: type[[PluginInterface](#kaithem.api.plugins.PluginInterface)])

Register a class as a plugin interface

### kaithem.api.plugins.get_providers(service: str) → list[[kaithem.src.plugin_system.BasePluginInterface](../../src/plugin_system/index.md#kaithem.src.plugin_system.BasePluginInterface)]

Returns a list of modules that provide the named service,
as defined in the plugin_metadata.

Low level, instead use you should use the PluginInterface subclass's
get_providers()
