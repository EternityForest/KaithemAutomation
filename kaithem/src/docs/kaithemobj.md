
# Help 

## The Kaithem Object:


The Kaithem object is one object available in almost all user defined
code. It has the following properties:

### General Utilities


### kaithem.units

#### kaithem.units.convert(value, fr, to)
Convert a value from unit fr to unit to. Both are expressed as strings,
like "degC" to "degF". Note that there is no protection against all nonsensical conversions.

This uses the pint library for most units, which can be slow, but for some common units uses kaithem's
optimized fast unit conversions. This only works for abbreviated symbols in the correct case(mmHg, m, g, etc), 
and does not work with SI prefixes

#### kaithem.units.define(name, multiplier, type, baseUnit=None)

Define a new unit. Multiplier is what must be multipllied by to convert the base unit to the new unit.

It may also be a tuple of functions, one to go TO the base unit, and another to go FROM the base unit.
For example: Celcius is defined in terms of Kelvin as: (lambda x: x+273.15, lambda x: x-273.15)

You can base your unit on any unit, otherwise it is assumed you are using the default base, or that you are
defining the a new base unit. You can only use the default "true" global base for units defined as functions.

Kaithem does not know what the base units are, they are simply units with no offset and a multiplier if 1,it is up to the
programmer to know what the base unit for any particular type of measurement is. All conversions are done
by going to the global unit and then to the new unit.

Included Base Units:

mass: g
length: m
temperature(Absolute): K
flow: m3/min
pressure: Pa


#### kaithem.globals

An instance of object() who's only purpose is so that the user can asign
it attributes. Be careful, as the kaithem namespace is truly global.

### kaithem.misc

#### kaithem.misc.vardir:

The configured "var dir" for kaithem, where the modules, users, etc, and most user data is kept.

Some folders are used by kaithem internally, but otherwise it can be treated similar a home dir.  Modules may also
store things in other places though.


#### kaithem.misc.do(function):

Executes a function of no arguments in the background using kaithem's
thread pool. Any errors are posted to the message bus at
system/errors/workers. There is no protection against infinite loops.

#### Kaithem.misc.errors(f)

Returns any exception object raised during calling f, or else none if no
errors.

#### kaithem.misc.lorem()

Returns about a sentence to a paragraph of placeholder text that may
change between calls and may not actually be classic Lorem Ipsum text.

#### kaithem.misc.effwords:
An indexable iterable of every word in the EFF wordlist


#### Kaithem.misc.uptime()

Returns uptime in seconds of the kaithem server(not of the machine
itself). Deprecated in favor of kaithem.time.uptime.

#### kaithem.misc.version()

Returns the current version as an unformatted short string, such as
"x.xx Release". The formatting of this string may change, and it may
contain extra text. But it wil be reasonably short and one line.

#### kaithem.misc.version\_info()

Returns the current verson as a 5 element tuple similar to python's
sys.version\_info. The format is (major, minor, micro, releaselevel,
serial).

releaselevel may be any of dev, alpha, beta, candidate, final

Serial is not guaranteed to actually do anything

#### kaithem.misc.breakpoint

This does nothing except print a notice. It's there so you can find the
function in breakpoint.py, and put a breakpoint there.


### kaithem.tags
Acess tag points, see Tag Points docs.


### kaithem.devices

This namespace is used to manage devices.  All device objects appear at kaithem.devices['DeviceName'], and kaithem.devices.deviceName, if the name is valid and does
not conflict.

You can't currently create a device in code. But you can add a new device type. 

See the main devices docs page for details.  Avoid keeping references to things here long term.  Perfer kaithem.devices['DeviceName'] directly,
otherwise you may not get the latest version of a device when a user modifies it.

#### kaithem.devices.device_types
Device driver classes all go here.

#### kaithem.devices.Device
This is the base class you would use to create a new device.


### kaithem.gpio

This namespace integrates the excellent GPIOZero into kaithem.

### kaithem.gpio.DigitalInput(pin, *,mock=None, pull=True, active\_state=None, bounce\_time=None, hold\_time=1, hold\_repeat=False, pin\_factory=None)

Creates an object that acts as an interface to the specified GPIO. Acts generally like gpiozero.button.

It creates a tag point at /system/gpio/PIN where you can view the status of the pin(Real or fake). The tag will be 1 when the button is active.

If the platform doesn't have GPIO, it will instead use gpiozero's Mock factory, and you'll
be able to use setRawMockValue. Calling this on a platform that DOES have mocking will auto-switch to
mock mode.

Pull is by default True, meaning pull-up, but can also be None for floating. This used to be called pull_up, but that was wrongly named and is now deprecated. 

Active state is normally guessed from the pull state(If the pull is up, active is low)

You can force mock mode with mock=True


#### DigitalInput.on_change(f)
Subscribes a function that must be f(topic,value) to debounced changes. Uses the internal
message bus. The topic will always be `"/system/gpio/change/"+str(self.pin)`, and the value
will always True if active or False if inactive.

#### DigitalInput.on_change(f)
Subscribes a function that must be f(topic,value) to get notified on hold events. Topic will always be `"/system/gpio/hold/"+str(self.pin)`, and the value will always True.

#### DigitalInput.set_raw_mock_value(v)
Switches to mock/testing mode and sets the fake raw input value. Everything should behave
exactly like it's getting real GPIO input.

#### DigitalInput.release_mocking()
Returns to real GPIO.


#### DigitalInput.gpio
The raw gpiozero.button object. Do not override any of the callbacks if you want to use kaithem's
native messagebus/tagpoint based API.


### kaithem.gpio.DigitalOutput(pin, mock=False, comment=False,*, active\_high=True, initial\_value=0, frequency=100, pin\_factory=None)

Sets a digital output to follow the state of a tag point at  /system/gpio/PIN.

#### DigitalOutput.tag
The tag point

#### DigitalOutput.tag.value
The PWM or digital value. Writing this sets the default value, which may be overridden by
another claim.

#### DigitalOutput.on()
Turn on by setting the tag's default value to 1. May be overriden by higher claims.


#### DigitalOutput.off()
Turn off by setting the tag's default value to 0. May be overriden by higher claims.



### kaithem.gpio.PWMOutput(pin, mock=False, comment=False,*, active\_high=True, initial\_value=0, frequency=100, pin\_factory=None)

Same as above but in PWM mode.

Sets a digital output to follow the state of a tag point at  /system/gpio/PIN.
In PWM mode, the range is 0-1.


### kaithem.resource

A dict-like object allowing you to access resources by module, resource tuple.



### kaithem.states

This namespace deals with kaithem's state machine library.

#### sm=kaithem.states.StateMachine(start="start")

Creates a state machine that starts in the given state. State machines are fully
threadsafe. Machines start with no states, so they are in a nonexistant
state to begin with.

#### sm.add_state(name, enter=None, exit=None)

Add a new state. Enter and exit can be functions taking no arguments.
They will run when that state is entered or exited. states are
identified by a string name, but values beginning with \_\_ are reserved

#### sm.remove_state(name)

Remove a state.

#### sm.add_rule(start, event, dest)

Add a rule to an existing state that triggers when event(which can be
any string, or a function but values beginning with \_\_ are reserved) happens.

Dest can be the name of a state, or else it can be a function that takes
one parameter, the machine itself, and returns either None or a string.

This function will be called anytime the rule is triggered. If it
returns None, nothing happens. If it returns a string, the machine will
enter the state named by that string.

The state machine strongly references the function, so it will not be garbage collected.
This allows you to use lambda expressions.

##### Function Polling(PLC logic)
If event is a function, it will be continually polled at sm.pollRate, defaulting to 24(24Hz),
and every time it is true the rule will be followed.

When multiple function triggers are added to the same state, they are polled in the order they
are added.

They are polled under sm.lock, and it is guaranteed that only one function is
polled at a time, and that no events, timers, or polling can happen in between an
event returning True and the state transition.



#### sm.set_timer(state, length, dest)

Attach a timer to a state. The timer starts when you enter the state. If
you remain there for more than length seconds, it goes to the dest. You
can only have one timer per state, the new one replaces the old if one
already exists.

re-entering a state resets the timer. Timers start immediately upon
entering a state, after the exit function of the old state but before
the exit function of the new state.

#### sm(event)

Calling the machine triggers an event. The event can be any string, but
values beginning with \_\_ are reserved. If there is a maching rule, the
rule is activated. Otherwise nothing happens. May raise an exception if
there is an error in the enter or exit function.

This does nothing if the machine is in a nonexistant state.

State machine subscribers, enter, and exit actions occur
synchronously in the thread that triggers the event,
so this function will block until they return.

This ensures Events and transitions are atomic. 

Any other thread that triggers an event during a transition will block until the original transition is complete, as will any modifications to the states, timers, or rules.

#### sm.subscribe(f, state="\_\_all\_\_"):

Subsribe f to be called when the state changes to state("\_\_all\_\_" indicates any state).

f is called with one argument, the name of the state, and this happens in the thread that
triggered the transition, so it should not block for too long.

#### sm.jump(state, condition=None)

Jump immediately to the given state, doing the proper exit and enter
actions. If condition is not None, it will only jump if the condition
matches the current state.

Jumping to a nonexistant state is an error.

#### sm.seek(t)

Seeks to a given position on the state's timeline. If you seek to any
point past the timer length for this state, the timer rule will simply
occur immediatly. Seeking to a negative position is also valid, and will
have the effect of extending the duration as expected.

#### sm.state

The current state as a string.

#### sm.entered_state

The time.time() value when this state was entered.

#### sm.age

A property that returns the time in seconds since entering the current
state.

#### sm.stateage

A property that returns a tuple of the (current state, time in seconds
since entering the current state.)

Both values are guaranteed to match, the state will not change after
checking one but before checking the other. Use this value any time you
want to test if something has been in a state for a certain time

#### sm.prev_state

The previous state of the machine. May be the same as the current state
if re-entry occurs. The initial value is None before any transitions
have occured.

### kaithem.alerts

Alerts allow you to create notification when unusual events occur,
trigger periodic sounds, and allow users to "acknowledge" them to shut
them up.

#### kaithem.alerts.Alert(name, priority="normal", zone=None, trip_delay=0, auto_ack=False, permissions=\[\], ackPermissions=\[\], \[id\],description='')

Create a new alert. Prority can be one of debug, info, warning, error,
or critical.

Zone should be a heirarchal dot-separated locator string if present,
telling the physical location being monitored. An example might be
"us.md.baltimore.123setterst.shed", but at present you can use whatever
format you like.

Permissions and ackPermissions are additional permissions besides
/users/alerts.view and /users/alerts.acknowledge that are needed to see
and ack the alert.

ID is a unique string ID. What happens if you reuse these is undefined
and wil be used to implement features later.

trip_delay is the delay in seconds that the alarm remains tripped before
becoming active.

Internally, alarms are state machines that may be in any of the listed
states. The underlying state machine object can be accessed as alert.sm.

#### normal

#### trip

Entered by calling a.trip(). This will be logged, but nothig will
actually happen until the trip delay passes, after which the alarm
becomes active.

#### active

The alarm will beep periodically from the configured sound devide(In
system settings), at an interval depending on the rate. It will be shown
on the front page(To users with the correct permissions). It remains
such until a clear event happens(by calling a.clear()), which would
cause it to enter the cleared state, or an acknowledge happens, causing
it to enter the acknowledged state.

#### cleared

This state indicates the undesired condition has stopped, but the alarm
has not been acknowledged. Acknowledging an alarm in this state causes
it to become normal. The alarm is visible but will not beep.

#### acknowledged

The condition is occuring, but is has been acknowledged. It will not
beep, but will show on the main page. Clearing in this state will cause
it to become normal.

#### error

Entered by calling a.error(), the alarm behaves as if it were an
error-priority active alarm, but returns to normal after being
acknowledged. Used to indicate an error with the alarm itself.

### kaithem.time

#### kaithem.time.lantime()
Same as time.time().  Previously Kaithem had built in NTP sync.

#### kaithem.time.uptime()

Return the number of seconds as a float that kaithem has been running
for. Useful for event triggers if you want to do something a certain
number of seconds after kaithem loads.

#### kaithem.time.strftime(timestamp)

Format a time in seconds since the epoch according to the user's
preference. When called outside of a page, format according to the
default

#### kaithem.time.moon_phase()

Returns the current moon phase as a float number:

    0  = New moon
    7  = First quarter
    14 = Full moon
    21-28 = Last quarter


#### kaithem.time.sunrise_time(lat=None,lon=None,date=None)
Returns the sunrise time on today's date, regardless of whether it is already passed or not.
Defaults to the server location, right now.  Date can be a date object.

#### kaithem.time.sunset_time()
#### kaithem.time.civil_dawn_time()
#### kaithem.time.civil_dusk_time()
See above.

**NOTE: any of these may raise an exception if
there is no sunrise or sunset in the current day(as in some regions in
the arctic circle during some seasons).**

#### kaithem.time.is_day(lat=None,lon=None)

Return true if it is before sunset in the given lat-lon location. If no
coordinates are supplied, the server location configured in the settings
page is used. If no location is configured, an error is raised.

#### kaithem.time.is_night(lat=None,lon=None)

Return true if it is after sunset in the given lat-lon location. Kaithem
handles coordinates as floating point values. If no coordinates are
supplied, the server location configured in the settings page is used.
If no location is configured, an error is raised.

#### kaithem.time.is_dark(lat=None,lon=None)

Return true if it is currently past civil twilight in the given lat-lon
location. Civil twilight is defined when the sun is 6 degrees below the
horizon. In some countries, drivers must turn on headlights past civil
twilight. Civil twilight is commonly used as the time to start using
artificial light sources. If no coordinates are supplied, the server
location configured in the settings page is used. If no location is
configured, an error is raised.

#### kaithem.time.is_light(lat=None,lon=None)

Return true if it is not past civil twilight given lat-lon location. If
no coordinates are supplied, the server location configured in the
settings page is used. If no location is configured, an error is raised.

#### kaithem.time.is_rahu(llat=None,lon=None)

Return true if it is currently Rahukalaam (A period during each day that
is considered inauspicious for new ventures in Indian astrology) in the
given lat-lon location. For more info see the [wiki
article.](http://en.wikipedia.org/wiki/Rahukaalam) If no coordinates are
supplied, the server location configured in the settings page is used.
If no location is configured, an error is raised.

### kaithem.sys

#### kaithem.sys.shellex(cmd)

Run a command in the system's native shell and return the output.

#### kaithem.sys.shellexbg(cmd)

Run a command in the system's native shell in the background and ignore
the output and return codes.

#### kaithem.sys.which(exe)

Similar to the unix which command. Returns the path to the program that
will be called for a given command in the command line, or None if there
is no such program

### kaithem.users

This namespace contains features for working with kaithem's user
management system.

#### kaithem.users.check_permission(username, permission)

Returns True is the specified use has the given permission and False
otherwise. Also returns False if the user does not exist.


### kaithem.midi
This namespace deals with MIDI.

#### kaithem.midi.FluidSynth(soundfont=DEFAULT, jackClientName=None)
Creates a FluidSynth instance using a specified soundfont. It
is a wrapper around https://github.com/nwhitehead/pyfluidsynth.

If no soundfont is supplied, kaithem includes babyfont.sf3, an excellent 4MB
soundfont file.

The library is a fork that has been patched to support FluidSynth 2 as well as 1.

#### FluidSynth.setInstrument(channel, instrument, bank=0)
Uses a MIDI program select message to set the instrument for the channel. You
can directly use a patch number, or you can use a string. The first instrument
in the soundfont or in general midi to match all words(case insensitive) is chosen.


Example:
`synth.setInstrument(0, "jazz guitar")`
Will select:
`26 : "Electric Guitar (jazz)"`


#### FluidSynth.fs
This is the raw synth in the library we are wrapping.

### kaithem.sound

The kaithem.sound API is slightly different depending on which backend
has been configured. By default mplayer will be used if available and is
the recommended backed.

#### kaithem.ogg_test([output])
Attempt to play an OGG test chime. May raise an error if it detects that it does not work.

#### kaithem.sound.directories
The `audio-paths` entry from the config YAML. May contain an entry called "__default__"

#### kaithem.sound.outputs()

Returns a list of available sound card names you could pass to 

#### kaithem.sound.preload(filename,output="@auto")
Spins up a paused player for that filename and player. Garbage collecting old cache entries is handled for you.
Will be used when sound.play is called for the same filename and output.

Does nothing on non-gstreamer backends.



#### kaithem.sound.fade_to(self,file,length=1.0, block=False, detach=True, handle="PRIMARY",**kwargs):

Only guaranteed to work with GStreamer backend.

Fades the current sound on a given channel to the file. **kwargs aare equivalent to those on playSound.

Passing none for the file allows you to fade to silence, and if no sound is playing. it will fade FROM silence.

Block will block till the fade ends. Detach lets you keep the faded copy attached to the handle(Which makes it end when a new sound plays,
so it only makes sense if fading to silence).

Fading is perceptually linear.


#### kaithem.sound.play(filename,handle="PRIMARY",volume=1,start=0,end=-0.0001, output=None,fs=False,extraPaths=\[\])

If you have a backend installed, play the file, otherwise do
nothing. The handle parameter lets you name the new sound instance to
stop it later. If you try to play a sound under the same handle as a
stil-playing sound, the old one will be stopped. Defaults to PRIMARY.

Relative paths are searched in a set of directories.

First in the configured directories and a default
builtin one(Unless you remove it from the config).

Next in all folders named "media" in modules. For example,
asking for "Music/foo.wav" will look for a file resource called media/Music/foo.wav in each loaded module.

Searching is not recursive, but relative paths work. If searching for "foo/bar" in
"/baz", it will look for "/baz/foo/bar".

If you want to search paths for relative files other than the default
abd the ones in the config, add them to extraPaths.


Volume is a dimensionless multiplier that only works if using SOX or
mplayer or Gstreamer. Otherwise it is ignored. Start and end times are in seconds,
negative means relative to sound end. Start and end times are also
SOX/mplayer specific and are ignored(full sound will always play) with
other players.


On the recommended gstreamer backend, output is a jack client or port if JACK is running, otherwise 
it is an alsa  device. The special string @auto(the default) autoselects an appropriate output.


#### kaithem.sound.builtinSounds

A list of filenames of sounds included with Kaithem. They are found in
the data dir, and cann be drectly passed to play.

#### kaithem.sound.stop(handle="PRIMARY"")

Stop a sound by handle.

#### kaithem.sound.stop_all()

Stop all currently playing sounds.

#### kaithem.sound.is_playing(handle="PRIMARY")

Return true if a sound with handle handle is playing. Note that the
sound might finish before you actually get around to doing anything with
the value. If using the dummy backend because a backend is not
installed, result is undefined, but will not be an error, and will be a
boolean value. If a sound is paused, will return True anyway.

#### kaithem.sound.setvol(vol,handle="PRIMARY")

Set the volume of a sound. Volume goes from 0 to 1. Only works with the
mplayer backend. If you are using any other sound backend, this does
nothing.

#### kaithem.sound.pause(handle="PRIMARY")

Pause a sound. Does nothing if already paused Only works with the
mplayer backend. If you are using any other sound backend, this does
nothing.

#### kaithem.sound.resume(handle="PRIMARY")

Resume a paused a sound. Does nothing if not paused. Only works with the
mplayer backend. If you are using any other sound backend, this does
nothing.

#### kaithem.sound.resolveSound(fn,extrapaths=[])
Search every default sound path, and all the extra paths for the sound file.
Return full absolute path to the sound if found.

### kaithem.message

#### kaithem.message.post(topic,message, timestamp=None, annotation=None)

Post a message to the internal system-wide message bus.
Message topics are hierarchial, delimited by forward
slashes, and the root directory is /. However /foo is equivalent to
foo.  

Formerly, messages could only be JSON serializable objects. Now that
we do not use the message system for logging, messages may be any python object at all.

The most recent messages are still logged in ram and viewable as before, for debugging purposes.

The timestamp will be set to time.monotonic() if it is None.

Annotation is used for sending "extra" or "hidden" metadata, same as it is for Tag Points,
usually for preventing loops. It defaults to None.

#### kaithem.message.subscribe(topic,callback)

Request that function *callback* which must take four arguments(topic,message, timestamp,annotation), two
arguments(topic,message), or just one argument(message) be called whenever a message matching the topic
is posted.

Wildcards follow MQTT subscription rules.

Should the topic end with a slash and a hash, it will also match all
subtopics(e.g. "/foo/#" will match "/foo", "/foo/bar" and
"/foo/anything"). 

Uncaught errors in the callback are ignored but logged.

You must always maintain a reference to the callback, otherwise, the
callback will be garbage collected and auto-unsubscribed. This is also
how you unsubscribe.

### kaithem.widget

**See Widgets for info on how to use these. Unless otherwise mentioned,
their API is defined by the Widget base class.**

#### kaithem.widget.DynamicSpan()

Creates a dynamic span widget. When rendered, A dynamic span widget
looks like a normal HTML span. however, you can change it's contents by
write()ing strings to it. This widget does not return any data.

#### kaithem.widgets.TimeWidget()

All this does is display the current time in his or her prefered format.
use like an HTML span or an image. Render takes a parameter type which
defaults to widget. If type is 'inline', will render as simple text
without special styling.

Unlike other widgets, the TimeWidget is purely client side and uses the
system clock of the client, and as such will even work if
/static/widget.js is not included.

#### kaithem.widgets.Button()

This is a button. Data points from it are in the form of lists of
states. Normally the value will be \['pushed'\], or \['released'\], but
if the user quickly taps the button(a common use for buttons), the value
will be \['pressed','released'\] or some such. Basically, the value
records what happened during the most recent pollng period in which
there was activity.

The sugessted pattern for dealing with these is to use
[attach()](#widgetattach) to set a callback, then use a line like "if
'pushed' in value:" to detect button presses. Directly reading the value
is not reccomended.

Mobile devices may not be able to register press-and-hold, but should
handle normall presses correctly.

render() takes a **required** first argument content which is is usually
a short string such as "submit" which will appear as the contents of the
HTML button. render() also takes the optional keyword element type. If
type is "trigger", it will render as a larger button that is disabled by
default, with a smaller arm/disarm button above it, that one must use in
order to enable the button. However, as far as the server knows, it acts
as a normal button. Good for things you don't want to press
accidentally.

#### kaithem.widgets.Meter(\*\*kwargs)

Used for display a changing numeric value. By default, renders to a
simple HTML span that changes color on extreme values if limits are
defined.

The constructor for meter can take a upper critical value called high, a
lower crtitcal value called low, an upper warning threshold called
high\_warn, and a lower warning threshold called low\_warn. These are
all passes as keyword arguments.

Render takes the optional parameter called unit, that specifies a unit
to associate, like "Volts" or "Hz" or such, and the optional parameter
label, which specifies a label such as "CH1 Voltage"


The constructor takes an optional "unit" parameter, which is a string like "m" that describes the
native unit of the meter.

It also takes a parameter displayUnits, which describe what units should be displayed. It is a pipe-separated
list without spaces.

#### kaithem.widgets.Slider(\*\*kwargs)

A slider widget, that currently may only be vertical. Optional
parameters: min, max, and step, must be numbers and control the range
and step size of the slider.

Slider.render() takes an optional parameter *unit* which specifies a
unit of measurement to associate. optional parameter label, which
specifies a label such as "CH1 Voltage, It also takes a parameter type,
which by default is 'realtime', which causes the value to be sent to the
server whenever the slider is moved. If this value is "onrelease", data
will only be sent to the server when you release your mouse or take your
finger off the touchscreen.

#### kaithem.widgets.Switch(\*\*kwargs)

An on-off toggle widget.

Switch.render() takes an optional parameter label, which provides a
clickable label.

Switch.read() and Switch.write() return and accept boolean values.

#### kaithem.widgets.TextBox

A text box control. render() takes an optional parameter that provides a
label for the box.

On the server, you can call read() to get it's contents or write(s) to
set it's contents

TextBox.render() takes an optional parameter label to provide a label
for the box.

#### kaithem.widgets.ScrollBox(length=250)

A scrolling widget used for things like logging. Whatever HTML you
write() will be appended to the end of a log on all the browsers in a
div tag. The last length entries are kept. Even without websocket
support, you can refresh to get the most recent entries.

#### kaithem.widgets.APIWidget(echo=True)

This widget exists to allow you to create custom widgets easily. When
you render() it, you pass a parameter htmlid. The render function
returns a script that places an object into a global javascript variable
of that name. You can use obj.set(x) to set the widget's value to x, and
retrieve the widget's value with obj.value.

\\

You can also use obj.send(x), to ensure that all values and not just the
latest are transmitted. obj.send is more like a message oriented pipe
than a shared variable, although for simplicity set may be implemented
similarly to send.

You may transmit any value that can be represented as JSON.

If you would rather recieve a callback after every pollingcycle with the
current value, just redefine the objects upd(val) method.

You can also use obj.now() to get a time in milliseconds since the
epoch(As in Date.now()) that represents what the server thinks is the
current time. The precision may only be 100ms due to browsers degrading
performance.now(). It may take a few seconds to stabilize.

On the python side, [attach()](#widgetattach), read(), and write() all
work as expected.

If echo is true(the default), any messges send from a client will be
echoed back to all clients

### kaithem.web


#### kaithem.web.nav_bar_plugins
This is a WeakValueDictionary that you can use to add items to the top navbar. Entries should have string keys, and
values must be a function that returns None for no item, or a tuple of (sort order, HTML).
HTML will typically be an a tag link.  Default sort order should be 50.

#### kaithem.web.controllers 

This is a WeakValueDict that maps path tuples to CherryPy
style controller objects.  It allows you to handle requests for
arbitrary URLs so long as they do not conflict.

These are raw CherryPy pages. You are responsible for checking permissions
yourself.

Controllers are simply objects with @cherrypy.expose methods. Putting
them in this dict "Mounts" them at a given path.

The controller with a key of ("hello","test") would map to
/hello/test, and would also be used for hello/test/foo, etc.

The handler which is mounted at the longest path is chosen.

You may also mount Exception objects this way. These will be raised if anyone
tries to go to that path.

Note that these are just straight up native Cherrypy handlers. You cannot
use kaithem.web.serveFile like you can in a page created as a Page Resource, you must use CherryPy's API for this.

You can't mount objects with levels of heirarchy this way. Visiting mountpoint/foo will access the foo methond on the controller, and /foo/bar/ will pass bar as a path arg to foo,  but you can't have a second object baz as a property of the controller.


You can't bind to the root / path, because there is already a default index page there.


##### Subdomains

Normally, the subdomain is entirely ignored, they act exactly like the main domain.  However, you can capture requests to a specific subdomain with:
a tuple like ("subdomain", "/","mountpoint").
For consistency, multiple subdomains are specified top-to-bottom, opposite the way URLs do them.  foo.bar.localhost/baz  maps to ('bar','foo', '/','baz).

You have to bind to an exact subdomain, entries do not match sub-subdomains of the one you specify.


Note that this does not allow you to bind to different main domains, only subdomains.  Ignoring the main domain simplifies access from multiple IPs.

Also note that you cannot capture ALL requests to a subdomain, only ones that do not map to an existing page so this cannot be a means of sandboxing. 
However, as different subdomains have different cookies, you can create a certain level of safety if users never log into an "untrusted" subdomain.

Relying on users not to do this, however, seems like a fairly bad idea, so kaithem forbids logging in if the subdomain contains `__nologin__` as a path component.

Note that even with this protection, XSS can still do anything that a guest can do.


#### kaithem.web.go_back()

When called from code embedded in an HTML page, raises an interrupt
causing an HTTP redirect to the previous page to be sent. Useful for
when you have a page that is only used for it's side effects.

#### kaithem.web.goto(url)

When called from code embedded in an HTML page, raises an interrupt
causing an HTTP redirect to the previous specified url to be sent.

#### kaithem.web.user()

When called from within a page, returns the usernae of the accessing
user or else an empty string if not logged in.

#### <span id="servefile"></span>kaithem.web.serve_file(path,contenttype,name = path)

When called from code embedded in an HTML page,raises an interrupt
causing the server to skip rendering the current page and instead serve
a static file. Useful when you need to serve a static file and also need
to restrict acess to it with permissions.

Can serve a bytesIO object if mime and filename are provided, or any other object having a read(),
as long as you enable streming response on page config.


#### kaithem.web.has_permission(permission)

When clled from within a mako template, returns true if the acessing
user has the given permission.

### kaithem.events

The kaithem.events namespace provides facilities for programmatically
creating events. Temporary events created in this manner are handled by
the same code as other events.

#### kaithem.events.when(trigger,action,priority="interactive")

This lets you create an event that will fire exactly once and then
dissapear. Trigger must be a function that returns true when you want it
to fire, and action must be a function

#### kaithem.events.after(delay,action,priority)

Same as when(), but creates an event that will fire after *delay*
seconds. Usful for things like turning lights on for set lengths of
time. This will only be accurate to within a tenth of a second normally,
or within one frame if you set priority to 'realtime'

Note that as both these functions create real(through temporary) events,
they have the capability to outlast the creating code. If one set up a
event that creates temporary events, then deletes the event, the
temporary events will remain until triggered or until the server is
restarted.

### kaithem.persist

Provides easy-to-use functionality for traditional file based
persistance. relative filenames provided to these functions will use
kaithem's vardir/data as the working directory. $envars and ~ will be
expanded if expand is set to true.

Each module should in general have it's own subfolder in this data
directory unless the data will be shared between modules


To store things directly in the vardir, use kaithem.misc.vardir
to find it.

#### Supported File Types

.json  
Values may any JSON serializable object

.toml  
Values may any TOML serializable object


.yaml  
Values may any YAML serializable object

.txt  
Values must be a sting or unicode string. Any other object will be
converted to a string in some undefined manner Text will be saved as
UTF-8, but no BOM will be added.

.bin  
Bytes and bytearrays may be directly saved with this.

\*.gz

Any other type may be compressed with gzip compresssion(e.g.
"foo.txt.gz")

\*.bz2

Any other type may be compressed with bz2 compression(e.g.
"bar.json.bz2")

#### kaithem.persist.unsaved

This is just a dict. When anything is in here, an asterisk is displayed in the UI.

What you do is kaithem.persist.unsaved['filename'] = "Explanation".

When you save that file(Such as by listening to the /system/save message), then you pop it out of the dict.

It is equivalent to scullery.persist.unsavedFiles.

#### kaithem.persist.load(filename, *, expand=True)

Load data from a file named filname in a format dictated by the file
extension. Data will be converted to a python appropriate representation
and returned.

#### kaithem.persist.save(data,filename,*,private=False,backup=True,expand=False)

Saves data to a file named fn in a format dictated by the file
extension. If the file does it exist, it will be created. If it does, it
will be overwritten. If backup is true, the file will be written to filename~, then atomically renamed to filename, making this fully atomic.



If the directory you try to save into does not exist, it will be created
along with any higher level directories needed.


If private is True, file will have the mode 700(Only owner or admin/root
can read or write the file). The mode is changed before the file is
written so there is no race condition attack.

### kaithem.string

#### kaithem.string.usrstrftime(\[time\])

When called from within a page, formats the time(in seconds since the
epoch), according to the user's time settings. If no time is given,
defaults to right now.

#### kaithem.string.si_format(n,d=2)

Takes a number and formats it with suffixes. 1000 becomes 1K, 1,000,000
becomes 1M. d is the number of digits of precision to use.

#### kaithem.string.format_time_interval(n,places=2,clock=False)

Takes a length of time in secons and formats it. Places is the mx units
to use. formatTimeInterval(5,1) becomes ""5 seconds",
formatTimeInterval(65,2) returns "1 minute 5 seconds"

If clock==True, places is ignored and output is in HH:MM format. If
places is 3 or 4 format will be HH:MM:SS or HH:MM:SS:mmm where mmmm is
milliseconds.

### kaithem.plugin

This namespace contains tools for writing plugins for kaithem. A plugin
can be just a module that provides features, or it can be a python file
in src/plugins/startup, which will be automatically imported.

#### kaithem.plugin.add_plugin(name,object)

Causes a weak proxy to object to become available at kaithem.name. The
object will be deleted as soon as there are no references to it. Note
that the automatic deletion feature may fail if the object has any
methods that return anything containing a strong reference to the object
itself.

If automatic collection of garbage in this manner is not important, and
your application is performance critical, you can directly insert
objects via attribute assignment, however that could cause other modules
to behave unpredictably when calling partially-deleted things.