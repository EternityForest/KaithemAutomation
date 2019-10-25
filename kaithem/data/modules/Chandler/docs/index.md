---
allow-origins: ['*']
allow-xss: false
auto-reload: false
auto-reload-interval: 5.0
dont-show-in-index: false
mimetype: text/html
no-header: false
no-navheader: true
require-method: [GET, POST]
require-permissions: []
resource-timestamp: 1566264981206441
resource-type: page
template-engine: markdown

---
Chandler Help
----------------------------

Chandler is a general purpose lighting, sound, and general show control application that is
designed to be easy to use with no programming needed.

This is beta software, usable but may have interface changes in the
future.


### The Console

The module provides a GUI control based on websockets that allows you
to access all features of Chandler.

Only actively running scenes and scenes created via the board will be
shown in the list. Only scenes created via the board can be edited.



### Scenes


A "scene" is more like a Layer in an image editing program than a
traditional lighting scene. There is no limit to the number of scenes
you can have running at once.

Scenes are made up of Cues, each of which can have a different
configuration for the lights, sound, and logic.

A scene has an alpha blend slider that affects how much of an affect the
scene has on the overall look.

By default, scenes blend in "normal" mode, which is true alpha blending
as might be found in an image editor. HTP and Inhinbt modes are provided,
allowing you to use them as traditional submasters.

The alpha slider also controls the volume of the cue's sound.

In other blend modes(notably inhibit), the alpha channel might not
behave as a true alpha. Inhibit mode works as you would expect in a traditional
console, dimmimg everything as the slider is lowered.

Setting the alpha slider to a nonzero value starts it if it is not already started. Scenes
restart at the beginning the same cue they were at when stopped, or at
default.

Scenes are generally fully transparent to all channels the current cue
does not affect.


Scenes have a priority that determines render order.

If two scenes have the same priority, the scene changed cues most recently
goes "on top".

### Cues

A scene is a list of "cues", each of which has a set of lighting values
for channels in it. A scene can only have one active cue at at time.


Cues have a fade in time that controls how long it takes to fully fade
in from the last cue. They may also have a length, which can auto-advance to
the next cue. The length is measured in beats, and the BPM is set per-scene.

Length 0 just stops until something else happens to change the cue.


Newly created cues are numbered by 5, with the first cue at 5, the
second at 10, etc. You can use decimal cues down to 0.001. A cue's
number may be changed at any time to move it around.

Unlike some lighting solutions, cues are also identified by name, and
you can freely select the "next" cue that comes after any given cue.

This allows you to create loops, and even to have multiple selectable
loops within one scene. Names and numbers only need to be unique within
each scene, not globally. Names can't contain special chars.

When you don't explicitly set a next cue, it defaults to whatever comes
next in the list, but if you do want to explicitly set the next cue, you
do it by name not number.

#### Shortcut Codes

Every cue can have a "shortcut code", a brief string of characters use
to quickly jumped to a cue. Typing this code in the shortcut box will
instantly trigger that cue, and activate it's scene if it is not already
active. Multiple cues, in different scenes can have the same shortcut
code and will all be activated when the code is entered.

This shortcut code defaults to the cue's number.

Scenes all have a special cue called "default" that is entered when
activating a scene.

#### Channels and layering

Cues have a list of "channels" they affect, that can be from any number
of universes, a priority, and an opacity. Higher priority scenes "cover
up" lower priority scenes, and their opacity is used to specify how
"transparent" they are.


#### Randomization

You can randomize the cue order in several ways. One is to set the next
cue to the "special cue" \_\_random\_\_ which randomly selects a cue in
the scene. Another is to specify a pipe-delimited list of cues, as in
cue1\|cue2\|cue3\|cue4.

In both these cases the next cue chosen is not truly random, it uses an
algorithm to avoid repeats. It will exclude the most recently used cues,
but will never exclude so many as to reduce the remaining possibilites
to less than 2. The

#### Cue Logic  

Using the graphical editor, you can apply logic to cues via rules.

A rule is just a list of actions to perform when an event occurs.
Actions have a return value, and so can be used to as questions.

Actions happen in sequence until one returns None.


#### Key Bindings

When the chandler console is in send events mode, every keypress triggers a corresponding "keydown.X" event
in all scenes. You can then use script bindings or cue logic to respond to these. Key up events trigger a "keyup.X" event.

### Universes

A universe is a set of "channels" with values represented as 32
bit floats from 0 to 255. They have more or less the same meaning as DMX
values. Each has a number starting at 1, but channels may also have names in addition
to numbers.

You can use any transport you want to actually transmit them to lights.

### Fixtures

Fixtures are specific instances of a fixture type that can be assigned
to a universe and start address.  Fixture assignments
are not stored in the scenes, they are currently key in the kaithem
registry.

A lighting scene doesn't know where a fixture is, the mapping is done
at rendering and is fully dynamic, so you can reuse scenes between setups.

### Saving

You can upload or download the complete set of scenes as a zip file.
You can also save the current set of scenes as the default with one click.

Every scene is saved to disk as an individual version controllable YAML file. 
These are found in Kaithem's VarDir/chandler/scenes/

Universes are saved to the registry automatically and commited when the server state is saved.
They are kept separate from the scenes to allow portability and use with different interfaces.



### Blending Modes

This module supports multiple "blend modes" which have the same meaining
as in image editing. Each scene has a specified blending mode. Some
modes are purely effects, that modify layers below. If the values below
are 0, the result will generally also be 0.

HTP blendmode takes the highest value, simulating traditional lighting
consoles. Inhibit multiplies the scene's alpha by all the channel
values, and restricts the channels to that value. Scenes with a blend
mode of Inhibit don't automatically stop at alpha 0. Note that in this
case "alpha" is being used more as a generic control input than a true
alpha.

Gamma allows you to gamma-correct the output for linear fading on cheap
DMX lights.

Flicker simulates a candle or flame type flicker across all the channels
in the scene. The higher the value, the more flicker. Flicker is an
effect that modifies the colors applied by scenes below it(Set the
priority higher), so if there are no other scenes affecting a channel
the value is 0.

Flicker attempts to detect RGB triples(Consecutive channels), and they
will all flicker together although possibly by different amounts.

You can control the parameters of the flicker algorithm, such as
windiness, gustiness, lowpass filtering, etc, from the web UI.

Vary adds a random variation to layers. Think of it as a randomly
varying gel effect. You can control the interval and amount of
variation. As with flicker, only channels added to the scene are
affected, the higher the value, the more variation. RGB triples are not
detected, all channels are independant.

### Monitor Scenes

A monitor scene is a special scene used in the web UI lightboard to see
the current state of a set of channels. Whatever channels you add to it
will be updated in realtime. They only show contributions from layers
below themselves, and only update while running.


### Programmatic access
See [API Docs](/pages/Chandler/docs/api)

### Script Bindings(Legacy)


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




