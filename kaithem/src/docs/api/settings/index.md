# kaithem.api.settings

## Functions

| [`list_keys`](#kaithem.api.settings.list_keys)(→ list[str])                         | List all known setting keys                                         |
|-------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`get_val`](#kaithem.api.settings.get_val)(→ str)                                   | Returns the highest priority setting for the key                    |
| [`add_val`](#kaithem.api.settings.add_val)(key, value[, source, priority])          | Add a config option.   If value is empty string, remove it instead. |
| [`add_suggestion`](#kaithem.api.settings.add_suggestion)(key, value[, description]) | Add a suggestion for the given key                                  |
| [`clear_suggestions`](#kaithem.api.settings.clear_suggestions)(key)                 |                                                                     |
| [`set_description`](#kaithem.api.settings.set_description)(key, description)        |                                                                     |
| [`subscribe_to_changes`](#kaithem.api.settings.subscribe_to_changes)(key, callback) |                                                                     |

## Module Contents

### kaithem.api.settings.list_keys() → [list](../../src/pages/index.md#kaithem.src.pages.list)[[str](../../src/pages/index.md#kaithem.src.pages.str)]

List all known setting keys

### kaithem.api.settings.get_val(key: [str](../../src/pages/index.md#kaithem.src.pages.str)) → [str](../../src/pages/index.md#kaithem.src.pages.str)

Returns the highest priority setting for the key

### kaithem.api.settings.add_val(key: [str](../../src/pages/index.md#kaithem.src.pages.str), value: [str](../../src/pages/index.md#kaithem.src.pages.str), source: [str](../../src/pages/index.md#kaithem.src.pages.str) = '<code>', priority: [float](../../src/chandler/groups/index.md#kaithem.src.chandler.groups.float) | [int](../../src/chandler/groups/index.md#kaithem.src.chandler.groups.int) = 0)

Add a config option.   If value is empty string, remove it instead.

### kaithem.api.settings.add_suggestion(key: [str](../../src/pages/index.md#kaithem.src.pages.str), value: [str](../../src/pages/index.md#kaithem.src.pages.str), description: [str](../../src/pages/index.md#kaithem.src.pages.str) = '')

Add a suggestion for the given key

### kaithem.api.settings.clear_suggestions(key: [str](../../src/pages/index.md#kaithem.src.pages.str))

### kaithem.api.settings.set_description(key: [str](../../src/pages/index.md#kaithem.src.pages.str), description: [str](../../src/pages/index.md#kaithem.src.pages.str))

### kaithem.api.settings.subscribe_to_changes(key, callback)
