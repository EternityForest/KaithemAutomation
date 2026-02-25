# kaithem.api.chandler

## Functions

| [`add_command`](#kaithem.api.chandler.add_command)(name, f)            | Add a command which will be available in the                   |
|------------------------------------------------------------------------|----------------------------------------------------------------|
| [`trigger_event`](#kaithem.api.chandler.trigger_event)(event[, value]) | Trigger an event in all groups                                 |
| [`shortcut`](#kaithem.api.chandler.shortcut)(s)                        | Trigger a shortcut code.  All matching cues will be jumped to. |

## Module Contents

### kaithem.api.chandler.add_command(name: [str](../../src/pages/index.md#kaithem.src.pages.str), f: [kaithem.src.scriptbindings.StatelessFunction](../../src/scriptbindings/index.md#kaithem.src.scriptbindings.StatelessFunction))

Add a command which will be available in the
Logic Editor.  Params should be strings.  Defaults and
docstrings will be used.

### kaithem.api.chandler.trigger_event(event: [str](../../src/pages/index.md#kaithem.src.pages.str), value: Any = None)

Trigger an event in all groups

### kaithem.api.chandler.shortcut(s: [str](../../src/pages/index.md#kaithem.src.pages.str))

Trigger a shortcut code.  All matching cues will be jumped to.
