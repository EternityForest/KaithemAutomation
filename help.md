Kaithem Help
============

<a href="" id="intro"></a>Introduction
--------------------------------------

Kaithem is an automation solution based on the concept of events,triggers, and actions. An event is a statement that when the trigger occurs, the action should be executed.

Kaithem is written in pure Python and will run in either 2.6+ or 3.xx without modification, the difference being that unicode resource and user names are not allowed in Kaithem on 2.xx

Kaithem includes all dependancies(except the optional mpg123 or SOX or mplayer for sound support)

In addition, Kaithem provides TLS/SSL encryption, user management, and serves as a basic IDE to create web pages that can interact with your process data. Kaithem was not designed for mission-critical control purposes, but aims to be fully reliable enough for basic home and commercial automation tasks.

An important idea in Kaithem is that resources, such as events, data, and web pages, all exist within *modules*. This allows for a very simple plugin based architecture wherein device plugins can be bundled with the web pages to manage them. Modules can be downloades or uploaded to and from the server as zip files, or can be created and modified straight from the web interface.

One **very important note** about Kaithem is that it does not save anything to the disk except when told to or if autosave was explicilty configured. In kaithem "Save" generally means to update the in-memory copy, wheras "Save to disk" means to actually whatever is in memory to the disk. To do this, go to the Save State page in Settings and follow the instructions. Modules configured as external can be saved individually.

In the event that the software crashes while saving, old data will not be corrupted and the old version will be used. Manual recovery of the new version will likely be possible for at least some files.

The exception to this rule is log files. Logs are maintained in ram till they reach a certain size(default 33,000 entries) then saved to disk. They are also saved when you explicitly save the entire state, or periodically if this is configured.

<a href="" id="modules"></a>Modules:
------------------------------------

Kaithem stores all user created resources in modules. This makes it very easy to write new device drivers, as they can simply be modules that place functions into a global namespace.

Code and management pages are just resources within modules. A module is just a loose collection of resources all with a unique name. Note that two resources with different types still must have unique names(within a module). Resources can be anything from events and actions to user defined pages to custom permissions.

You can name modules as you like, but anything beginning with a double-underscore("\_\_") is reserved. Resource, user, and group names beginning with a double underscore are also reserved.

Resources may have any name, however the slash is considered the path separator to allow for subfolders within modules. The slash may be escaped using an backslash, as can the backslash itself. Whitespace in paths has no special meaning.

To move a resource between folders, you simply rename it. To move foo/baz to a folder bar, simply rename it bar/baz.

<a href="" id="events">Events</a>
---------------------------------

One of the main automation constructs is the *event*. Events are mappings between a *trigger* and an *action*.A trigger can be a python expression that when the return value goes from False to True(edge triggered), the *Action*, which is simply a python script, executes.

A trigger can also be a**Special Trigger Expression**. Trigger expressions begin with an exclamation point and provide functionality that would be cumbersome with a python statement.

Events have their own special scope similar to a local scope that is pre-populated when the event loads with several useful things, among these the kaithem object(see below). Internally they are implemented as modules that are generated on the fly. The setup code runs directly inside the module, whilst the trigger and action are used to generate two functions.

<a href="" id="trigger"></a>
### Availible Trigger Expressions

#### !onmsg \[topic\]

This trigger expression causes the event to occur when a message is posted to the internal message bus matching \[topic\]. The actual topic and message are then availible as \_\_topic and \_\_message respectively. If another message occurs while the event is running, it will be handled after the first event is done.

#### !onchange \[expression\]

This trigger expression causes the event to occur when the value of expression changes. the most recent value of expression is available as \_\_value.

#### !time \[expression\]

This causes the event to occur at a specific time, such as "every Friday" or "every hour on Monday". This is powered by the recurrent library and supports any expression that library does. Events will occur near the start of a second. Specific time zones are supported with Olson format time zones, e.g. "!time Every day at 8:30pm Etc/UTC". If no time zone is provided, the local time zone will be used.

By default, if an event is late it will be run as soon as possible, but if more than one event is missed it will not run multiple times to make up. If the string "exact &ltnumber&gt;" appears, then events more than number seconds late will just be skipped(Events after run as usual).

Examples: "!time every minute exact 2.5", "Every day at 8:30pm".

Some preprocessing occurs before the recurrent library parses it, so that any expression of the form blah/blah will be interpreted as a timezone. Timezone names must be in the Olson TZ list("US/Central","Etc/UTC", etc) If the time expression does not contain a time zone, it will be assumed to be in the server's local time.

If a time event is still running by the next occurrence, it will be skipped unless allow\_overlap is present somewhere in the string.

If you delete the event but something else still has a reference to the function, calling it will raise an error

Be careful with this one. Some input values might just not work, others may crash the system when they are entered, in a bad way where everything just hangs. Mostly the problem is with things that specify a specific range of time like "every day between 2010 and 2012". If the date is in the distance past it will hang. You should strongly consider using standard polled edge triggers, kaithem.time, or rate limit triggers instead.

Other issues are things like "Between april and june". It seems to think you mean april of next year to next june. However "april-june" seems to work as expected.

Another thing to watch out for is that it does not store time reference points. So something like "every month" might run every time kaithem reboots, and then a month on from there, etc. Since you probably want the first of the month, you need to be explicit "on the first of each month".

In general recurrent appears to be a great library but natural language is hard for computers and you should always verify it is doing what you want.

#### !function \[name\]

This trigger expression assigns the action to name. !function module.x is the same as module.x = action, where action is a function that triggers the event. You mak put a semicolon and a statement after it, as in !function f; obj.attach(f) and the statement will be run after the function is assigned.

<a href="" id="pages"></a>Pages:
--------------------------------

Kaithem allows users with the appropriate permissions to create user-defined pages. User defined pages are written in HTML and may contain embedded mako template code. Every page is a resource of a module. Mako is a simple templating language allowing you to embed server-side python in HTML code. Python code in user defined pages has access to the kaithem object(see below) and and if desired the python code may have side effects, allowing a wide variety of web services, information displays, and control panels to be created using only kaithem's page system.

Access to pages is controlled through kaithem's permission system, and any page may require one or more permissions to access. New Permissions can be defined as module resources.

Every user-created page has an URL of the form /pages/MODULENAME/PAGE/PATH/GOES/HERE

For example, A resource bar in module foo would be found at "/pages/foo/bar", while a resource baz in folder bar in foo will be found in /pages/foo/bar/baz

Unlike events, the page-local scope does not persist between calls

User pages should follow the [Theming Guidelines](/docs#theming).

### Default and Index pages.

Should you go to /pages/foo/bar and bar is a folder, foo/bar/\_\_index\_\_will be returned should it exist.

Nonexistant page handling: Should you go to /pages/foo/bar/nonexistant, bar will first be searched for a \_\_default\_\_ page, then foo, then the root. If no default is found, an error will be returned.

<a href="" id="scope"></a>Scoping
---------------------------------

Almost all programming languages have some concept of scope and Python is no different. Every event has its own global scope, similar to a (python) module. If you set a variable in the event action and use the global keyword, it will be there next time the event runs, but will not be directly visible in other resources. If you assign a variable in an event action without the global keyword, it will simply disappear after the event runs like any function local variable. This does not apply to Mako code inside page html. Mako code will act like function local variables and only persist for the life of the call, and globals don't really apply here.

Anything defined in the Setup function of an event becomes a part of the global namespace for that event, and can be accessed by code in Trigger and Action, and written to by use of the global keyword.

Internally, the events are compiled to (in memory, bytecode is not written to disk) python modules and the actions become functions.

Every resource scope(including setup,trigger,action, and Mako pages) however will contain an object called kaithem, which is a global object with some useful utilities, and an object called module, which is shared between all resources within one module (Regardless of where in the nested heirarchy the resoucrce is). The module objects have no special properties beyond the ability to assign objects to them.

<a href="" id="auth"></a>Users and access control:
--------------------------------------------------

Access control is based on *users*, *groups*, and *permissions*.

A user may belong to any number of groups.<span style="font-style: italic;"> </span>A user has access to all permissions of the groups he or she is a member of.

To create new users or groups, change group memberships or permissions, or delete users, you must have the<span style="font-style: italic;"> /admin/users.edit </span>permission. Keep in mind a user with this permission can give himself any other permission and so has full access. Do not give this permission to an untrusted user.

Permissions are generally of the form  "/&lt;path&gt;/&lt;item&gt;.&lt;action&gt;" without quotes. The path describes the general category, the item specifies a resource, and the action specifies an action that may be performed on the resource. Modules may define their own permissions, and user-defined pages may be configured to require one or more permissions to access. For consistency, You should always use the above permission format.

Upon creating a new permission, you will immediately be able to assign it to groups by selecting the checkbox in the group page.

<a href="" id="fileref"></a>File Reference Resources
----------------------------------------------------

Beginning in version 0.55, modules may contain arbitrary files as resources. To preserve kaithem's atomic save functionality, files are stored in one large pool with names that have long strings of characters after them, and the modules themselves only contain references to them. The exception is in external modules and zip files. Saving to an external module will populate a special \_\_filedata\_\_ folder in that module, likewise with zip files. However, due to potential performance and memory constraints, users without the edit permission will not be able to download copies of modules that include files. You should still not make your modules publicly viewable unless you have good reason.

You can always get the real disk path of a file resource from within the same module via the code: module\['name'\].getPath()

The Widget System
-----------------

Kaithem integrates an AJAX library that allows you to create dynamic widgets within HTML pages that automatically interact with the corresponding object on the server. You do not need to write any javascript at all to use Kaithem Widgets. Most Widgets automatically handle multiple users, such as moving sliders on one device to match a change on another.

### widget.js

Somewhere in your page before the first widget, you must include this line:

    <script type="text/javascript" src="/static/widget.js"></script>

This will include a small JS library that will automatically handle polling for you.

### Widget Objects

A widget object represents one widget, and handles AJAX for you automatically. Each widget type is slightly different, but all widgets have a render() method. The render method produces HTML suitable for direct inclusion in a page, as in &lt;%text&gt;

    ${module.myWidget.render()}

The rendered HTML will contain a few functions, the ID of the widget object that created it, and a piece of code that registers it for polling.
Widgets may take parameters in their render() function on a widget specific basis

You must maintain a reference to all widget objects you create to prevent them from being garbage collected.

Most widget objects will have write(value) and read() functions. For example, a calling read() on a slider widget would return whatever slider position the user entered. If there are multiple users, all sliders rendered from the same object will move in sync.

### The Widget() Base Class

All Kaithem widgets inherit from Widget. Widget provides security, polling handling, and bookkeeping. Widget has the following properties, which may be overridden, extendd, or removed in derivd classes:

### Widget.render(\*args,\*\*kwargs)

Returns an HTML representation of the widget, including all javascript needed, and suitable for direct inclusion in HTML code as you would a div or img. Widgets are usually inline-block elements. Many numeric widgets will take an optional keyword argument label and unit.

### Widget.uuid (Always available)

This is a string representation of the Widget's ID. It is automatically created when initializing Widget.

### Widget.require(permission) (Always Available)

Causes the object to reject AJAX read or write requests from any device that does not have the permissions. You can apply as many permissions as you want.

### Widget.requireToWrite(permission) (Always Available)

Causes the object to reject AJAX write requests from any device that does not have the permissions. You can apply as many permissions as you want.

### Widget.onRequest(user) (Always Available)

This function is automatically called when an authorized client requests the latest value. It must return None for unknown/no change or else a JSON serializable value specific to the widget type. You only need to know about this function when creating custom widgets.

### Widget.onUpdate(user,value) (Always Available)

This function is automatically called when an authorized client requests to set a new value. value will be specific to the widget. You only need to know about this function when creating custom widgets.

### Widget.read() (Usually Available)

Returns the current "value" of the widget, an is available for all readable widgets where the idea of "value" makes sense. Generally just returns self.value unless overridden.

### Widget.write(value) (Usually Available)

sets the current "value" of the widget, an is available for all writable widgets where the idea of "value" makes sense. Unless overridden, this will set self.value, invoke any callback set for the widget(with user \_\_SERVER\_\_), and send the value to all subscribed clients.

This should not be used from within the callback or overridden message handler due to the possibility of creating loops. To send a value to all clients without invoking any local callbacks or setting the local value, use send.

### Widget.send(value)

Send value to all subscribed clients.

### []()Widget.attach(f)

Set a callback that fires when new data comes in from the widget. It will fire when write() is called or when the client sends new data The function must take two values, user, and data. User is the username of the user that loaded the page that sent the data the widget, and data is it's new value. user will be set to \_\_SERVER\_\_ if write() is called.

You should not call self.write from within the callback to avoid an infinite loop, although you can call write on other widgets without issue. If you wish to send replies from a callback, use self.send() instead which does not set self.value or trigger the callback.

<a href="" id="kaithemobject"></a>The Kaithem Object:
-----------------------------------------------------

The Kaithem object is one object available in almost all user defined code. It has the following properties:

### General Utilities

#### kaithem.globals

An instance of object() who's only purpose is so that the user can assign it attributes. Be careful, as the kaithem namespace is truly global.

### kaithem.misc

#### kaithem.misc.do(function):

Executes a function of no arguments in the background using kaithem's thread pool. Any errors are posted to the message bus at system/errors/workers. There is no protection against infinite loops.

#### Kaithem.misc.errors(f)

Returns any exception object raised during calling f, or else none if no errors.

#### kaithem.misc.lorem()

Returns about a sentence to a paragraph of placeholder text that may change between calls and may not actually be classic Lorem Ipsum text.

#### Kaithem.misc.uptime()

Returns uptime in seconds of the kaithem server(not of the machine itself)

#### kaithem.misc.version()

Returns the current version as an unformatted short string, such as "x.xx Release". The formatting of this string may change, and it may contain extra text. But it wil be reasonably short and one line.

#### kaithem.misc.version\_info()

Returns the current verson as a 5 element tuple similar to python's sys.version\_info. The format is (major, minor, micro, releaselevel, serial).

releaselevel may be any of dev, alpha, beta, candidate, final

Serial is not guaranteed to actually do anything

### kaithem.time

#### kaithem.time.strftime(timestamp)

Format a time in seconds since the epoch according to the user's preference. When called outside of a page, format according to the default

#### kaithem.time.year()

Return current year in server's time zone as an integer .

#### kaithem.time.month()

Return current month in the server's time zone. s month object, which can be printed like a string, but can be intelligently compared(January="Jan"=="January"==0) Month objects do not support comparisions besides equality, however they can be cast to integers. Jan=0

#### kaithem.time.dayofweek()

Returns a day-of-week object in the server's time zone.that inherits from string and prints as an uppercase full name(like 'Tuesday'), but can be intelligently compared(DoW=='tue','Tue,'Tuesday','tu',1,'1',etc). When usig numbers, monday is 0. Again, only equality comparisions, but you can cast to int.

#### kaithem.time.\[minute|second|hour\]()

All of these functions perform as expected(e.g. minute() returns a number between 0 and 59). hour() uses 24 hour server local time

#### kaithem.time.isdst()

Return true is daylight savings time is in effect where the server is.

#### kaithem.time.day()

Returns the day of the month in the server's time zone.

#### kaithem.time.moonPhase()

Returns the current moon phase as a number:

    0  = New moon
    7  = First quarter
    14 = Full moon
    21 = Last quarter

**NOTE: isDay,isNight,isDark, and isLight may raise an exception if there is no sunrise or sunset in the current day(as in some regions in the arctic circle during some seasons).**
#### kaithem.time.isDay(lat,lon)

Return true if it is before sunset in the given lat-lon location. If no coordinates are supplied, the server location configured in the settings page is used. If no location is configured, an error is raised.

#### kaithem.time.isNight(lat=None,lon=None)

Return true if it is after sunset in the given lat-lon location. Kaithem handles coordinates as floating point values. If no coordinates are supplied, the server location configured in the settings page is used. If no location is configured, an error is raised.

#### kaithem.time.isDark(lat=None,lon=None)

Return true if it is currently past civil twilight in the given lat-lon location. Civil twilight is defined when the sun is 6 degrees below the horizon. In some countries, drivers must turn on headlights past civil twilight. Civil twilight is commonly used as the time to start using artificial light sources. If no coordinates are supplied, the server location configured in the settings page is used. If no location is configured, an error is raised.

#### kaithem.time.isLight(lat=None,lon=None)

Return true if it is not past civil twilight given lat-lon location. If no coordinates are supplied, the server location configured in the settings page is used. If no location is configured, an error is raised.

#### kaithem.time.isRahu(llat=None,lon=None)

Return true if it is currently Rahukalaam (A period during each day that is considered inauspicious for new ventures in Indian astrology) in the given lat-lon location. For more info see the [wiki article.](http://en.wikipedia.org/wiki/Rahukaalam) If no coordinates are supplied, the server location configured in the settings page is used. If no location is configured, an error is raised.

#### kaithem.time.accuracy()

Get a conservative estimate(offset plus root delay plus root dispersion) of the maximum error of the system clock in seconds using pool.ntp.org Only polls NTP at most every 600 seconds. If the server is unreachable, uses the cached value, plus 100ppm of the time since the server was checked. If the server was never reachable, use the value of 30 years.

### kaithem.sys

#### kaithem.sys.shellex(cmd)

Run a command in the system's native shell and return the output.

#### kaithem.sys.shellexbg(cmd)

Run a command in the system's native shell in the background and ignore the output and return codes.

#### kaithem.sys.lsfiles(path)

List all files under path on the server.

#### kaithem.sys.lsdirs(path)

List all directories under path on the server.

#### kaithem.sys.which(exe)

Similar to the unix which command. Returns the path to the program that will be called for a given command in the command line, or None if there is no such program

### kaithem.registry

The kaithem registry is a persistance store for small amounts of configuration data. It does not get saved to disk until the server state is saved, or a configured autosave occurs. The registry is heirarchial and slash separated, keys are strings, values are anything json serializable, and keys should begin with the relevant module name, and should consider double underscores reserved.

Internally as of V0.53, the registry is stored with one file per root path component("foo/bar" and "foo/baz" are stored in the same file)

These should really not be used for large amount of data or frequently acessed data as the registry is not designed for high performance. Applications include small amounts of configuration data such as schedules, playlists, and disk locations for other files.

Registry files are only readable by the user kaithem runs as and so you should store passwords in the registry instead of directly in the code.

#### kaithem.registry.get(key,default=None)

Gets the registry key. Returns default if the key does not exist.

#### kaithem.registry.set(key,value)

Sets the registry key.

#### kaithem.registry.setschema(key, schema)

Set a validictory validation schema for key. Schema must be a dict describing the format(Validictory schemas are very close to JSON schema, see validictory documentation for more info). If you try to set a key to a value that is invalid acording to a schema, it will raise an error.

#### kaithem.registry.delete(key, schema)

Delete a key and and data and schema assosiated with it

### kaithem.sound

The kaithem.sound API is slightly different depending on which backend has been configured. By default mplayer will be used if available and is the recommended backed.

#### kaithem.play(filename,handle="PRIMARY",volume=1,start=0,end=-0.0001, eq=None, output=None,fs=False)

If you have mpg123 or SOX installed, play the file, otherwise do nothing. The handle parameter lets you name the new sound instance to stop it later. If you try to play a sound under the same handle as a stil-playing sound, the old one will be stopped. Defaults to PRIMARY.

With the mplayer backend, if you give it a video file, it will likely open a window and play it. Passing fs=True may allow you to play fullscreen, but any use of this "hidden feature" is very experimental. results may be undefined if you attempt to play a video in an environment that does not support it. All the features that work with audio should also work with video.

Volume is a dimensionless multiplier that only works if using SOX or mplayer. Otherwise it is ignored. Start and end times are in seconds, negative means relative to sound end. Start and end times are also SOX/mplayer specific and are ignored(full sound will always play) with other players.

output and eq are mplayer specific and do nothing with other backends. eq if present can take the value 'party' causing the EQ to be set to allow easier conversation. output must be a string that selects an output device. A typical value on linx would be pulse::n where n is the pulse sink index, see mplayer's -ao option for more details.

#### kaithem.sound.stop(handle="PRIMARY"")

Stop a sound by handle.

#### kaithem.sound.stopAll()

Stop all currently playing sounds.

#### kaithem.sound.isPlaying(handle="PRIMARY")

Return true if a sound with handle handle is playing. Note that the sound might finish before you actually get around to doing anything with the value. If using the dummy backend because a backend is not installed, result is undefined, but will not be an error, and will be a boolean value. If a sound is paused, will return True anyway.

#### kaithem.sound.setvol(vol,handle="PRIMARY")

Set the volume of a sound. Volume goes from 0 to 1. Only works with the mplayer backend. If you are using any other sound backend, this does nothing.

#### kaithem.sound.pause(handle="PRIMARY")

Pause a sound. Does nothing if already paused Only works with the mplayer backend. If you are using any other sound backend, this does nothing.

#### kaithem.sound.resume(handle="PRIMARY")

Resume a paused a sound. Does nothing if not paused. Only works with the mplayer backend. If you are using any other sound backend, this does nothing.

### kaithem.message

#### kaithem.message.post(topic,message)

Post a message to the internal system-wide message bus. Message MUST be a JSON serializable object. i.e True/false, numbers, strings, lists, and dictionaries only. Message topics are hierarchial, delimited by forward slashes, and the root directory is /. However /foo is equivalent to foo.

#### kaithem.message.subscribe(topic,callback)

Request that function *callback* which must take two arguments(topic,message) be called whenever a message matching the topic is posted. Should the topic end with a slash, it will also match all subtopics(e.g. "/foo/" will match "/foo", "/foo/bar" and "/foo/anything"). Uncaaught errors in the callback are ignored.
You must always maintain a reference to the callback, otherwise, the callback will be garbage collected and auto-unsubscribed. This is also how you unsubscribe.

### kaithem.widget

**See Widgets for info on how to use these. Unless otherwise mentioned, their API is defined by the Widget base class.**

#### kaithem.widget.DynamicSpan()

Creates a dynamic span widget. When rendered, A dynamic span widget looks like a normal HTML span. however, you can change it's contents by write()ing strings to it. This widget does not return any data.

#### kaithem.widgets.TimeWidget()

All this does is display the current time in his or her preferred format. use like an HTML span or an image. Render takes a parameter type which defaults to widget. If type is 'inline', will render as simple text without special styling.

Unlike other widgets, the TimeWidget is purely client side and uses the system clock of the client, and as such will even work if /static/widget.js is not included.

#### kaithem.widgets.Button()

This is a button. Data points from it are in the form of lists of states. Normally the value will be \['pushed'\], or \['released'\], but if the user quickly taps the button(a common use for buttons), the value will be \['pressed','released'\] or some such. Basically, the value records what happened during the most recent pollng period in which there was activity.

The sugessted pattern for dealing with these is to use [attach()](#widgetattach) to set a callback, then use a line like "if 'pushed' in value:" to detect button presses. Directly reading the value is not reccomended.

Mobile devices may not be able to register press-and-hold, but should handle normal presses correctly.

render() takes a **required** first argument content which is is usually a short string such as "submit" which will appear as the contents of the HTML button. render() also takes the optional keyword element type. If type is "trigger", it will render as a larger button that is disabled by default, with a smaller arm/disarm button above it, that one must use in order to enable the button. However, as far as the server knows, it acts as a normal button. Good for things you don't want to press accidentally.

#### kaithem.widgets.Meter(\*\*kwargs)

Used for display a changing numeric value. By default, renders to a simple HTML span that changes color on extreme values if limits are defined.

The constructor for meter can take a upper critical value called high, a lower crtitcal value called low, an upper warning threshold called high\_warn, and a lower warning threshold called low\_warn. These are all passes as keyword arguments.

Render takes the optional parameter called unit, that specifies a unit to associate, like "Volts" or "Hz" or such, and the optional parameter label, which specifies a label such as "CH1 Voltage"

#### kaithem.widgets.Slider(\*\*kwargs)

A slider widget, that currently may only be vertical. Optional parameters: min, max, and step, must be numbers and control the range and step size of the slider.

Slider.render() takes an optional parameter *unit* which specifies a unit of measurement to associate. optional parameter label, which specifies a label such as "CH1 Voltage, It also takes a parameter type, which by default is 'realtime', which causes the value to be sent to the server whenever the slider is moved. If this value is "onrelease", data will only be sent to the server when you release your mouse or take your finger off the touchscreen.

#### kaithem.widgets.Switch(\*\*kwargs)

An on-off toggle widget.

Switch.render() takes an optional parameter label, which provides a clickable label.

Switch.read() and Switch.write() return and accept boolean values.

#### kaithem.widgets.TextBox

A text box control. render() takes an optional parameter that provides a label for the box.

On the server, you can call read() to get it's contents or write(s) to set it's contents

TextBox.render() takes an optional parameter label to provide a label for the box.

#### kaithem.widgets.APIWidget

This widget exists to allow you to create custom widgets easily. When you render() it, you pass a parameter htmlid. The render function returns a script that places an object into a global javascript variable of that name. You can use obj.set(x) to set the widget's value to x, and retrieve the widget's value with obj.value.

\\
You can also use obj.send(x), to ensure that all values and not just the latest are transmitted. obj.send is more like a message oriented pipe than a shared variable, although for simplicity set may be implemented similarly to send.

You may transmit any value that can be represented as JSON.

If you would rather receive a callback after every polling cycle with the current value, just redefine the objects upd(val) method.

On the python side, [attach()](#widgetattach), read(), and write() all work as expected.

### kaithem.web

#### kaithem.web.url(url)

URL enode a string.

#### kaithem.web.unurl(url)

Decode an URL enoded string.

#### kaithem.web.goBack()

When called from code embedded in an HTML page, raises an interrupt causing an HTTP redirect to the previous page to be sent. Useful for when you have a page that is only used for it's side effects.

#### kaithem.web.user()

When called from within a page, returns the usernae of the accessing user or else an empty string if not logged in.

#### kaithem.web.WebResource(name,url,priority=50)

register a web resource, return an object that you must keep a reference to or it will be unregisted. The web resource system is intended to allow you to change the source of a file without changing pages depending on it, by simply looking up the URL by name at render-time.

Names of JS libraries should satisfy the following: libname-x.y.z or libname-devx.y.z for versions not subject to minification and compression

Lib names should not include the .js prefix, but may modify the version number if based on a lib that does not use x.y.z formatting.

If two WebResources are registered by the same name, whichever has the higher priority takes effect. If they are equal, the newer one is used

When a WebResource gets replaced, the old one is discarded, so if you want to change back to the old one, you must re-save whatever defines the old version.

#### kaithem.web.resource(n)

#### Given the name of a registered web resource, return an object that prints as a string representing it's URL

#### <a href="" id="servefile"></a>kaithem.web.serveFile(path,contenttype,name = path)

When called from code embedded in an HTML page,raises an interrupt causing the server to skip rendering the current page and instead serve a static file. Useful when you need to serve a static file and also need to restrict access to it with permissions.

#### kaithem.web.hasPermission(permission)

####

When called from within a mako template, returns true if the acessing user has the given permission.

### <a href="" id="kdotmail"></a>kaithem.mail

These functions allow sending email messages through the [SMTP Server](#email) configured in the settings page

#### kaithem.mail.send(recipient,subject,message)

Send a message to an email address, where recipient is an address or list therof, and subject and message are strings.

#### kaithem.mail.listSend(list,subject,message)

Send a message to an email address, where list is the UUID of a mailing list, and subject and message are strings. The message will be sent to all subscribed users.

### kaithem.events

The kaithem.events namespace provides facilities for programmatically creating events. Temporary events created in this manner are handled by the same code as other events.

#### kaithem.events.when(trigger,action,priority="interactive")

This lets you create an event that will fire exactly once and then disappear. Trigger must be a function that returns true when you want it to fire, and action must be a function

#### kaithem.events.after(delay,action,priority)

Same as when(), but creates an event that will fire after *delay* seconds. Useful for things like turning lights on for set lengths of time. This will only be accurate to within a tenth of a second normally, or within one frame if you set priority to 'realtime'

Note that as both these functions create real(through temporary) events, they have the capability to outlast the creating code. If one set up a event that creates temporary events, then deletes the event, the temporary events will remain until triggered or until the server is restarted.

### kaithem.persist

Provides easy-to-use functionality for traditional file based persistence.

#### kaithem.persist.load(filename)

Load data from a file named filename in a format dictated by the file extension. Data will be converted to a python appropriate representation and returned.

#### Supported File Types

.json  
Values may be list, dict, string, int, bool, or None

.yaml  
Values may be list, dict, string, int, bool, or None

.txt  
Values may be anything. str() will be used on it prior to saving.

.bin  
Bytes and bytearrays.

\*.gz  
Any other type may be compressed with gzip compression(e.g. "foo.txt.gz")

\*.bz2  
Any other type may be compressed with bz2 compression(e.g. "bar.json.bz2")

#### kaithem.persist.save(data,filename,mode=default,private=False)

Saves data to a file named fn in a format dictated by the file extension. If the file does it exist, it will be created. If it does, it will be overwritten. If mode=='backup', a tilde will be appended to the existing file's name, the new file written, and then the backup will be deleted. Compressed filetypes are also supported.

If private is True, file will have the mode 700(Only owner or admin/root can read or write the file). The mode is changed before the file is written so there is no race condition attack.

#### Supported File Types

.json  
Values may be list, dict, string, int, bool, or None

.yaml  
Values may be list, dict, string, int, bool, or None

.txt  
Directly reads TXT file and returns as string. May be ASCII or UTF-8.

.bin  
Bytes and bytearrays.

\*.gz  
Any other type may be compressed with gzip compresssion(e.g. "foo.txt.gz")

\*.bz2  
Any other type may be compressed with bz2 compression(e.g. "bar.json.bz2")

### kaithem.string

#### kaithem.string.usrstrftime(\[time\])

When called from within a page, formats the time(in seconds since the epoch), according to the user's time settings. If no time is given, defaults to right now.

#### kaithem.string.siFormat(n,d=2)

Takes a number and formats it with suffixes. 1000 becomes 1K, 1,000,000 becomes 1M. d is the number of digits of precision to use.

#### kaithem.string.formatTimeInterval(n,places=2,clock=False)

Takes a length of time in seconds and formats it. Places is the mx units to use. formatTimeInterval(5,1) becomes ""5 seconds", formatTimeInterval(65,2) returns "1 minute 5 seconds"

If clock==True, places is ignored and output is in HH:MM format. If places is 3 or 4 format will be HH:MM:SS or HH:MM:SS:mmm where mmmm is milliseconds.

### kaithem.plugin

This namespace contains tools for writing plugins for kaithem. A kaithem plugin is just a module meant to extend kaithem's functionality.

#### kaithem.plugin.addPlugin(name,object)

Causes a weak proxy to object to become available at kaithem.name. The object will be deleted as soon as there are no references to it. Note that the automatic deletion feature may fail if the object has any methods that return anything containing a strong reference to the object itself.

If automatic collection of garbage in this manner is not important, and your application is performance critical, you can directly insert objects via attribute assignment, however that could cause other modules to behave unpredictably when calling partially-deleted things.

JS Library
----------

The /static/js/ directory on the webserver(Which in reality maps to the folder kaithem/src/js), contains a file "tablib.js".

By referencing this file, you can enable a custom HTML element tab-panel. Basically a tab panel contains a number of tab-pane elements, each with a name attribute. This implements a rudimentary tabview interface that may be styled through the CSS(see the default scrapbook.css for examples.)

<a href="" id="theming"></a>Theming
-----------------------------------

The following conventions are used for consistency in kaithem CSS. If you want your custom pages to be consistent with the rest of Kaithem's theming, you can use the following CSS classes in your user-created pages.

### Section Boxes

Almost everything that is not a large heading should be in a div with class="sectionbox" or a child thereof. Kaithem backgrounds may not have enough contrast with text to be easily readable outside of sectionboxes.

### Scrolling Boxes

a div with class="scrollbox" will look like a secionbox but scroll on overflow. May be nested in sectionboxes.

### Action Links and Buttons

Any link having the primary purpose of performing an action as opposed to navigation should have the class "button". If the action is delete, it should also have the class "deletebutton", likewise for "createbutton", "savebutton", "editbutton", and "playbutton" These classes may be used on links or actual buttons.

### Short help strings

Short help texts in the gui should be wrapped in a p element with class ="help"

### Menu Bars

Oftentimes you want to have something like the menu bars at the top of windows in desktop apps. An easy way to do this is to put your controls in a p element of class = "menubar"

### Highlighting

Making spans, paragraphs, etc stand out can be done by applying the classes "highlight", "specialentry", "error", or "warning".

specialentry is used when an entry in a list is different from other entries, and might be used for things like \_\_methods\_\_ and admin users

highlight is just a general purpose highlight for more important that usual entries

error and warning should be used when a element is an error notification

### Other Stuff

At the moment, theming kaithem's built in widgets and things like that must be done by reading the the code as most of
classes are not documented.
However, where possible kaithem prefers semantic HTML to classes, so it should be relatively easy to figure out.

The Internal Message Bus
------------------------

Kaithem includes a custom internal messaging system that is accessable from user code through kaithem.message The following topics are of note: However, the system also makes use of the bus in the following ways:

### /system/startup

A message is posted here after the system has fully initialized

### /system/shutdown

A message will be posted here just before the system shuts down or restarts unless it shuts down due to SIGKILL or a bad error or some other non-graceful cause

### /system/errors/events/\*module\*/\*event\*

Mhen an error occurs in a module, A message will be broadcast on this topic,where module and event are the relevant module and event.

### system/errors/workers

When an error occurs in Kaithem's background worker pool, it will be logged here. There could possibly be a lot of traffic here if a realtime event decides to spew a bunch.

### system/errors/scheduler/second

When an event occurs in kaithem's internal time scheduler it will be posted here. Nothing currently uses this except a few system tasks.

### system/errors/scheduler/minute

When an event occurs in kaithem's internal time scheduler it will be posted here. Nothing currently uses this except a few system tasks.

### /system/notifications

All messages broadcasted to this topic will appear on the front page. They should be normal text strings, and should not contain any time information as they will be listed by time on the front page anyway. Care must be taken not to flood the front page and thereby hide important messages. Only system-wide or major events should be logged here. One should subscribe to "/system/notifications/" with the trailing slash, as many messages are posted to subtopics.

### /system/notifications/errors

Messages here are like normal system/notifications/ messages, but are semantically errors, and can show in red in the logs, or trigger sounds, or send out text messages, or similar. Again, only fairly important things should go here, as they will be listed on the front page. Use for things like power failure, network connectivity loss, etc.
Where possible one should wait ten seconds or so before sending a message for something that might resolve itself, like a network issue.

### /system/notifications/warnings

These messages show in yellow in the front page and the logs. Use for generic warnings.

### /system/notifications/important

Messages show highlighted in logs. Use for things that you want to be noticed, but don't necessarily require immediate action, like when a connection has been established or restored with a server, The system boots up, or to notify of important events, store opening hours, etc. Routine things that happen frequently such as "main battery fully charged" shouldn't be put here.

### /system/modules/loaded

When a module has fully initialized, it's name is posted here.

### /system/modules/unloaded

When a module has been deleted, it's name is posted here.

### /system/modules/events/loaded

The module and resource of any event that loads or reloads gets posted here.

### /sytem/perf/FPS

Every ten minutes, a message will be posted to this topic containing only the current frame rate that the event polling runs at. Messages are posted every minute if the frame rate is below 95% of full.

### /sytem/perf/memuse

Every ten minutes, a message will be posted to this topic containing the current total memory usage of the system (0= none, 1=all available memory). Messages are posted every minute if the ram use is greater than 0.8

### /sytem/perf/requestsperminute

Every minute, a message will be posted to this topic containing the number of HTTP requests made to the server in the last minute.

### system/events/ran

When any event runs, a message will be posted here, the message being a list with two items, the first being the module name and the second being the event name

NOTE: the message logging system means that anyone with the /users/logs.view permission can see all traffic on the message bus, because even topics not set up to be logged are kept in ram and shown on the logs page for a short time. Be careful to either not send any private data on the message bus, or be very careful who you give permission to see the logs.

### system/auth/login

When a user logs in, his username and IP are posted here as a two element list.

### system/auth/logout

When a user logs out, his username and IP are posted here as a two element list.

### system/auth/loginfail

When a user fails to logs in, his username and IP are posted here as a two element list.

<a href="" id="logging"></a>Logging
-----------------------------------

Kaithem's native logging support is based on the message bus. Anytime a message is posted to the message bus, it gets stored in a "staging area". If a topic is not configured to be logged, than by default only the 50 most recent messages on that topic will be kept before discarding the oldest

Once the total number of messages in the staging area exceeds a threshold, The messages in the staging area will be filtered by topic then dumped to a file.
What specific get logged is configurable from the logs page, which also allows you to see the messages in the staging area. Log dumps are in JSON format as one big dict of lists of messages indexed by topic, where each message is an array of (timestamp,message)

Log dumps will be found in kaithem/var/logs/dumps while the list of topics to save will be in kaithem/var/logs

<a href="" id="email"></a>Email Alerts
--------------------------------------

Kaithem can be configured to [send email](#kdotmail) through an SMTP server. Go to the settings page to configure this. You can also create mailing lists, to make mail alerting easier to manage. You create these on the settings page. Mailing lists are uniquely identified by a base64 string called a UUID that ends in two equals signs. For every list you create, a corresponding permission will be created containing the UUID. You must have that permission to subscribe to a list. Every user can enter an email address and receive alerts from any list he has the correct permissions to subscribe to.