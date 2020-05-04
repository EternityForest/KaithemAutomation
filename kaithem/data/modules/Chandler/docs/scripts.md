---
allow-origins: ['*']
allow-xss: false
auto-reload: false
auto-reload-interval: 5.0
dont-show-in-index: false
mimetype: text/html
no-header: false
no-navheader: false
require-method: [GET, POST]
require-permissions: []
resource-timestamp: 1578097688435984
resource-type: page
template-engine: markdown

---
Scripts are no longer suggested, use the graphical logic editor instead.
    
A cue may have a script that defines a set of event responses while that
cue is active. Cue scripts follow the same general format as
Keybindings, with each line mapping an event to an action. Currently,
there are 2 builtin events that can be responded to, cue.enter, and
cue.exit, however you can set up bindings to arbitrary event names and
trigger them in code.

Special characters in general are reserved. Spaces delimit
arguments(except when escaped or between quotes), and backslashes
escape.

You can trigger an event by calling the .event(s) method of a Scene
object, where s is the name you want to trigger. kaithem.chandler.event(s)
will trigger an event for all active scenes.

Note that the set of commands and triggers is slightly different from
the in-browser Keybindings.

The cue.enter event fires when entering a cue, and the cue.exit event
fires when exiting.

Currently, only the goto \[scene\] \[cue\] and setalpha \[scene\]
\[alpha\] commands are supported. For example, the line "cue.enter:
setalpha scene4 0.8" sets the alpha of scene4 to 0.8 whenever that cue
begins.

If a binding does not contain a colon, it is assumed to be for
cue.enter. Example: "setalpha scene4 0.8"

Arguments are delimited by spaces, however quote marks and backslashes
override this behavior and work much as they do in a UNIX command line.
To use a literal quote of backslash you must escape it.

