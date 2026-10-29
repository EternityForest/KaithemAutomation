# kaithem.api.chandler

## Classes

| [`ShortcutCodeListener`](#kaithem.api.chandler.ShortcutCodeListener)   |                                             |
|------------------------------------------------------------------------|---------------------------------------------|
| [`StatelessFunction`](#kaithem.api.chandler.StatelessFunction)         | Base class for stateless command functions. |

## Functions

| [`add_command`](#kaithem.api.chandler.add_command)(name, f)            | Add a command which will be available in the                   |
|------------------------------------------------------------------------|----------------------------------------------------------------|
| [`trigger_event`](#kaithem.api.chandler.trigger_event)(event[, value]) | Trigger an event in all groups                                 |
| [`shortcut`](#kaithem.api.chandler.shortcut)(s)                        | Trigger a shortcut code.  All matching cues will be jumped to. |

## Module Contents

### *class* kaithem.api.chandler.ShortcutCodeListener(code: str, callback: collections.abc.Callable[[str, float, dict[str, Any]], None], description: str = '')

#### closed *= False*

#### code *= ''*

#### description *= ''*

#### close()

#### go(t: float | None = None, props: dict[str, Any] | None = None)

#### \_\_del_\_()

### *class* kaithem.api.chandler.StatelessFunction(ctx: [BaseChandlerScriptContext](../../src/scriptbindings/index.md#kaithem.src.scriptbindings.BaseChandlerScriptContext), \*args, \*\*kwargs)

Bases: `FunctionBlock`

Base class for stateless command functions.

Define command metadata as class attributes (doc, args).
The manifest property auto-builds CommandManifest from these attributes.

### kaithem.api.chandler.add_command(name: str, f: [kaithem.src.scriptbindings.StatelessFunction](../../src/scriptbindings/index.md#kaithem.src.scriptbindings.StatelessFunction))

Add a command which will be available in the
Logic Editor.  Params should be strings.  Defaults and
docstrings will be used.

### kaithem.api.chandler.trigger_event(event: str, value: Any = None)

Trigger an event in all groups

### kaithem.api.chandler.shortcut(s: str)

Trigger a shortcut code.  All matching cues will be jumped to.
