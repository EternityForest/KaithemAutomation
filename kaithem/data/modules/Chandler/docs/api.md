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
resource-timestamp: 1571773558480328
resource-type: page
template-engine: markdown

---
Chandler Help
-------------

## API 

### Scenes and Cue API

To create a scene, simply use kaithem.chandler.Scene(name,\*a,\*\*kw). If
there are duplicates, all references by name will point to the new
scene, but the old scene will still be usable. Scenes stop existing if
you don't keep a reference to them.


To access an existing scene programmatically, use the kaithem.chandler.scenes[name]
dict.

#### Cues
Every scene has a dict of cues called cues, that contains "cue objects"

Add a cue to a scene simply by calling scene.addCue, as in: cue =
scene.addCue(name,\*\*kwargs), and remove it with scene.rmCue(name)

You may pass onEnter and onExit options to Cue, which must be functions
of one argument, which will be the exact time the cue entered or exited,
in seconds, using a timebase that is not guaranteed to be the same as
time.time(). They will be called when the cue enters or exits,
respectively.

cue.setLength(l), setFadein(l), and setNext(cuename) can be used.
setNext(None) returns a cue to the default of having the next numbered
cue as the next one

##### Values
To set a value, use cue.setValue(universe, channel, value), for example
setValue("DMX", 45, 235).

To make a channel stop affecting a value, use cue.clearValue(universe,
channel)


#### Stop/go
To activate and stop scenes, use scene.go() and scene.stop().

Or, use setAlpha with a nonzero value to go.

#### Sync
For network synchronization of two scenes, to cause cue transitions to
match, use scene.setSyncKey(key), where key is a 32 byte binary string
that must be the same on all scenes you want to sync

You can set the port and address with setSyncAddress and setSyncAddress,
but the default multicast address and port should be fine.

#### Cues
To go to a new cue, use scene.gotoCue(cuename)

kaithem.chandler.shortcutCode(code) has the same effect as manually typing
that shortcut code in the web GUI

### General API

#### Scripting

You can add a command Chandler using
kaithem.chandler.commands, which is a weak value dict of command
names.

The first word in a script binding is the command name, the rest
will be split by spaces(double quotes and backslashes work as they do on
a Linux command line) and passed as positional arguments to the
function.





### Sending Data to Hardware

To use the lighting subsystem, you'll want to subclass
kaithem.chandler.Universe. Your universe subclass must handle onFrame,
which takes no arguments, but should trigger the object to transmit the
new values. Frames will happen at the kaithem max frame rate, which by
default is 60fps. Rendering happens in its own thread via a realtime
event.

Rendering is totally synchronous, and assumes that whatever code you use
to handle new values returns quickly.

Values are found in universe.values and will either be an array of
floats, or in the future numpy arrays may be auto-detected and used if
available. Assume that universe.values is an iterable of N floating
point values.

Universes are 0 indexed, however the first channel in the DMX protocol
is referred to as one. To avoid any confusion, When transmitting DMX,
universe value 1 should map to DMX channel 1 and Universe 0 should be
unused.

The constructor for a universe is
universe(name,count=65536,channelNames={}), however the constructor may
ignore count.

channelNames can be an dict mapping channel numbers to friendly names
that will be shown in the GUI.

You must call \_\_init\_\_ of the superclass in your init, and names
must be unique. Duplicates replace the old one.

### LAN Time

From the setup page, you can configure the lighting system to use an
auto-discovered MDNS server if available.
