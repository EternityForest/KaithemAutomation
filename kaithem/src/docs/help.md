Kaithem Help
============

<span id="intro"></span>Introduction
------------------------------------

Kaithem is an automation solution based on the concept of
events,triggers, and actions. An event is a statement that when the
trigger occurs, the action should be executed.

Kaithem is written in pure Python and will run in either 2.6+ or 3.xx
without modification, the difference being that unicode resource and
user names are not allowed in Kaithem on 2.xx

Kaithem includes all dependancies(except the optional mpg123 or SOX or
mplayer for sound support)

In addition, Kaithem provides TLS/SSL encryption, user management, and
serves as a basic IDE to create web pages that can interact with your
process data. Kaithem was not designed for mission-critical control
purposes, but aims to be fully reliable enough for basic home and
commercial automation tasks.

An important idea in Kaithem is that resources, such as events, data,
and web pages, all exist within *modules*. This allows for a very simple
plugin based architecture wherein device plugins can be bundled with the
web pages to manage them. Modules can be downloades or uploaded to and
from the server as zip files, or can be created and modified straight
from the web interface.

One **very important note** about Kaithem is that it does not save
anything to the disk except when told to or if autosave was explicilty
configured. In kaithem "Save" generally means to update the in-memory
copy, wheras "Save to disk" means to actually whatever is in memory to
the disk. To do this, go to the Save State page in Settings and follow
the instructions. Modules configured as external can be saved
individually.

In the event that the software crashes while saving, old data will not
be corrupted and the old version will be used. Manual recovery of the
new version will likely be possible for at least some files.

The exception to this rule is log files. Logs are maintained in ram till
they reach a certain size(default 33,000 entries) then saved to disk.
They are also saved when you explicitly save the entire state, or
periodically if this is configured.

<span id="modules"></span>Modules:
----------------------------------

Kaithem stores all user created resources in modules. This makes it very
easy to write new device drivers, as they can simply be modules that
place functions into a global namespace.

Code and management pages are just resources within modules. A module is
just a loose collection of resources all with a unique name. Note that
two resources with different types still must have unique names(within a
module). Resources can be anything from events and actions to user
defined pages to custom permissions.

You can name modules as you like, but anything beginning with a
double-underscore("\_\_") is reserved. Resource, user, and group names
beginning with a double underscore are also reserved.

Resources may have any name, however the slash is considered the path
separator to allow for subfolders within modules. The slash may be
escaped using an backslash, as can the backslash itself. Whitespace in
paths has no special meaning.

To move a resource between folders, you simply rename it. To move
foo/baz to a folder bar, simply rename it bar/baz.

<span id="events">Events</span>
-------------------------------

One of the main automation constructs is the *event*. Events are
mappings between a *trigger* and an *action*.A trigger can be a python
expression that when the return value goes from False to True(edge
triggered), the *Action*, which is simply a python script, executes.

A trigger can also be a**Special Trigger Expression**. Trigger
expressions begin with an exclamation point and provide functionality
that would be cumbersome with a python statement.

Events have their own special scope similar to a local scope that is
pre-populated when the event loads with several useful things, among
these the kaithem object(see below). Internally they are implemented as
modules that are generated on the fly. The setup code runs directly
inside the module, whilst the trigger and action are used to generate
two functions.

<span id="trigger"></span>

### Availible Trigger Expressions

#### !onmsg \[topic\]

This trigger expression causes the event to occur when a message is
posted to the internal message bus matching \[topic\]. The actual topic
and message are then availible as \_\_topic and \_\_message
respectively. If another message occurs while the event is running, it
will be handled after the first event is done.

#### !onchange \[expression\]

This trigger expression causes the event to occur when the value of
expression changes. the most recent value of expression is availible as
\_\_value.

#### !time \[expression\]

This causes the event to occur at a specific time, such as "every
Friday" or "every hour on Monday". This is powered by the recur library
and supports any expression that library does. Events will occur near
the start of a second. Specific time zones are supported with olson
format time zones, e.g. "!time Every day at 8:30pm Etc/UTC". If no time
zone is provided, the local time zone will be used.

By default, if an event is late it will be run as soon as possible, but
if more than one event is missed it will not run multiple times to make
up.

Examples: "!time every minute", "Every day at 8:30pm".

This feature previously used a library called recurrent, but now uses a
custom library called recur that solves some performance issues.

#### !function \[name\]

This trigger expression assigns the action to name. !function module.x
is the same as module.x = action, where action is a function that
triggers the event. You mak put a semicolon and a statement after it, as
in !function f; obj.attach(f) and the statement will be run after the
function is assigned.

<span id="pages"></span>Pages:
------------------------------

Kaithem allows users with the appropriate permissions to create
user-defined pages. User defined pages are written in HTML and may
contain embedded mako template code. Every page is a resource of a
module. Mako is a simple templating language allowing you to embed
server-side python in HTML code. Python code in user defined pages has
access to the kaithem object(see below) and and if desired the python
code may have side effects, allowing a wide variety of web services,
information displays, and control panels to be created using only
kaithem's page system.

Access to pages is controlled through kaithem's permission system, and
any page may require one or more permissions to access. New Permissions
can be defined as module resources.

Every user-created page has an URL of the form
/pages/MODULENAME/PAGE/PATH/GOES/HERE

For example, A resource bar in module foo would be found at
"/pages/foo/bar", while a resource baz in folder bar in foo will be
found in /pages/foo/bar/baz

Unlike events, the page-local scope does not persist between calls

User pages should follow the [Theming Guidelines](/docs#theming).

### Default and Index pages.

Should you go to /pages/foo/bar and bar is a folder,
foo/bar/\_\_index\_\_will be returned should it exist.

Nonexistant page handling: Should you go to /pages/foo/bar/nonexistant,
bar will first be searched for a \_\_default\_\_ page, then foo, then
the root. If no default is found, an error will be returned.

### Available Static Resources

Kaithem provides a few static resources that are included with the
distribution, notably Font Awesome and iconicss.
```html
<link rel="stylesheet" href="/static/img/icons/iconicss/iconicss.min.css">
<link rel="stylesheet" href="/static/img/icons/fontawesome/css/fontawesome-all.min.css">
```
Also include is the complete Fugue icon pack, accessible as follows:

    /zipstatic/img/icons/fugue.zip/cross-button.png

Also, the following JS libraries:

#### /static/js/vue2.js
The Vue framework

#### /static/js/strftime-min.js
Add this to your page, and get a strftime on date objects.

```js
var d = new Date();

var ymd = d.strftime('%Y/%m/%d');
var iso = d.strftime('%Y-%m-%dT%H:%M:%S%z');
```

#### /static/js/include.js

Add this to your page, and you'll be able to include other HTML
docs:

`<include src="child.html"></include>`

<span id="scope"></span>Scoping
-------------------------------

Almost all programming languages have some concept of scope and Python
is no different. Every event has its own global scope, similar to a
(python) module. If you set a variable in the event action and use the
global keyword, it will be there next time the event runs, but will not
be directly visible in other resources. If you assign a variable in an
event action without the global keyword, it will simply disappear after
the event runs like any function local variable. This does not apply to
Mako code inside page html. Mako code will act like function local
variables and only persist for the life of the call, and globals don't
really apply here.

Anything defined in the Setup function of an event becomes a part of the
global namespace for that event, and can be accessed by code in Trigger
and Action, and written to by use of the global keyword.

If you define a \_\_del\_\_() function, it gets called when the event is cleaned
up.

Internally, the events are compiled to (in memory, bytecode is not
written to disk) python modules and the actions become functions.

Every resource scope(including setup,trigger,action, and Mako pages)
however will contain an object called kaithem, which is a global object
with some useful utilities, and an object called module, which is shared
between all resources within one module (Regardless of where in the
nested heirarchy the resoucrce is). The module objects have no
properties beyond the ability to assign properties to share data, and
act like dicts of [API objects](#apiobjects) for resources.

New in 0.60, event scopes will contain an object called "event", which
is an easier way to access the event's API object.

<span id="auth"></span>Users and access control:
------------------------------------------------

Access control is based on *users*, *groups*, and *permissions*.

A user may belong to any number of groups.<span
style="font-style: italic;"> </span>A user has access to all permissions
of the groups he or she is a member of.

To create new users or groups, change group memberships or permissions,
or delete users, you must have the<span style="font-style: italic;">
/admin/users.edit </span>permission. Keep in mind a user with this
permission can give himself any other permission and so has full access.
Do not give this permission to an untrusted user.

Permissions are generally of the form 
"/&lt;path&gt;/&lt;item&gt;.&lt;action&gt;" without quotes. The path
describes the general catergory, the item specifies a resource, and the
action specifies an action that may be performed on the resource.
Modules may define their own permissions, and user-defined pages may be
configured to require one or more permissions to access. For
consistancy, You should always use the above permission format.

Upon creating a new permission, you will immediately be able to assign
it to groups by selecting the checkbox in the group page.

New in 0.58, groups also have "limits". A limit is simply a numeric
key-value pair associated with group. A user has access to the highest
limit of any group he is a member of, including \_\_guest\_\_, if it
exists.

At the moment, there is only one limit catergory, web.maxbytes, which is
used to allow members of certain groups to upload large files to the
server. You can set limits from the group pages.

Users with \_\_all\_permissions\_\_ have no practical upload limit.
Users with /admin/modules.edit can upload up to 4Gb file resources and
modules. Users with /admin/settings.edit can upload up to 4Gb files in
the file manager

Devices
-------

Kaithem suports a generic Device API that abstracts common functionality
in devices that might be connected, and gives you a central place to
manage, list, and configure all your connected devices.

Devices allow a certain amount of no-code GUI configuration for
supported types, by adding them on the devices page.

Devices are defined by a dict of configuration data and a name. At
minimium, the device config data will have a "type" field that
determines what class is used to construct the device object.

The generated device objects are accessible at kaithem.devices.name or
kaithem.devices\['name'\]

Every device has a set of "descriptors", which are objects indexed by
string keys that describe exactly what the device is capable of. String
keys can be anything, but domain name based names help avoid collisions.

To create your own device types, all you have to do is subclass
remotedevices.RemoreDevice, and add your subclass to the weak dict
remotedevices.deviceTypes.

Device configuration pages are structured as HTML forms, and the field
names map directly to data keys in the configuration. Every device has a
getManagementForm() method that returns raw HTML that gets inserted into
that form.

Configuration keys are hierarchially namespaced. To be completely safe,
use the "device." namespace for device specific stuff.

Config keys of the form alerts.NAME.priority are used to set the
priority of the corresponding alert in the device.alerts dict, allowing
easy configurable alerting. The config page already has this section,
you do not need to include it in your management form.

<span id="fileref"></span>File Reference Resources
--------------------------------------------------

Beginning in version 0.55, modules may contain arbitrary files as
resources. 

To preserve kaithem's atomic save functionality without making copies of large data, files are
stored a separate folder, and the modules themselves only contain references to them.
The exception is in external modules and zip files. 

Saving to an
external module will populate a special \_\_filedata\_\_ folder in that
module, likewise with zip files. 

However, due to potential performance and memory constraints, users without the edit permission will not be
able to download copies of modules that include files. 

You can always get the real disk path of a file resource from within the
same module via the code: module\['name'\].getPath()

You can directly access a file resource KAITHEMVARDIR/modules/filedata/MODULE/RESOURCE


<span id="apiobjects"></span>API Objects
----------------------------------------

Certain resource types have "API objects" used to access some additional
features. These API objects may be accessed within a module as
"module\[resourcename\]", or from within an event itself using the name
"event".

### File API Objects

#### file.getPath()
Returns the real absolute filesystem path of the object.

### Event API Objects

#### event.stop()

Pause execution of the event. It will not poll or run until unpaused, or
re-saved/reloaded. The event is not disabled or deleted so no variables
are lost.

#### event.start()

Restarts a paused event.

#### event.run()

Manually runs an event if it is not already running.

#### event.reportException()

When called from an exception handler, the traceback will show in that
event's page.

#### event.data

A blank object that you can assign properties to, which will persist
when the event is modified, but not across reboots.

# [/docs/mdtemplate?page=kaithemobj.md](The Kaithem Object)
This object provides useful APIs and is available in many contexts.


## [/docs/mdtemplate?page=kaithemobj.md] The Widgets API


JS Library
----------

The /static/js/ directory on the webserver(Which in reality maps to the
folder kaithem/src/js), contains a file "tablib.js".

By referencing this file, you can enable a custom HTML element
tab-panel. Basically a tab panel contains a number of tab-pane elements,
each with a name attribute. This implements a rudimentary tabview
interface that may be styled through the CSS(see the default
scrapbook.css for examples.)

<span id="theming"></span>Theming
---------------------------------

The following conventions are used for consistancy in kaithem CSS. If
you want your custom pages to be consistant with the rest of Kaithem's
theming, you can use the following CSS classes in your user-created
pages.

### Section Boxes

Almost everything that is not a large heading should be in a div with
class="sectionbox" or a child therof. Kaithem backgrounds may not have
enough contrast with text to be easily readable outside of sectionboxes.

### Scrolling Boxes

a div with class="scrollbox" will look like a secionbox but scroll on
overflow. May be nested in sectionboxes.

### Action Links and Buttons

Any link having the primary purpose of performing an action as opposed
to navigation should have the class "button". If the action is delete,
it should also have the class "deletebutton", likewise for
"createbutton", "savebutton", "editbutton", and "playbutton" These
classes may be used on links or actual buttons.

### Short help strings

Short help texts in the gui should be wrapped in a p element with class
="help"

### Menu Bars

Oftentimes you want to have something like the menu bars at the top of
windows in desktop apps. An easy way to do this is to put your controls
in a p element of class = "menubar"

### Highlighting

Making spans, paragraphs, etc stand out can be done by applying the
classes "highlight", "specialentry", "error", or "warning".

specialentry is used when an entry in a list is different from other
entries, and might be used for things like \_\_methods\_\_ and admin
users

highlight is just a general purpose highlight for more important that
usual entries

error and warning should be used when a element is an error notification

### Other Stuff

At the moment, theming kaithem's built in widgets and things like that
must be done by reading the the code as most of

classes are not documented.

However, where possible kaithem prefers semantic HTML to classes, so it
should be relatively easy to figure out.

The Internal Message Bus
------------------------

Kaithem includes a custom internal messaging system that is accessable
from user code through kaithem.message The following topics are of note:
However, the system also makes use of the bus in the following ways:

### /system/startup

A message is posted here after the system has fully initialized

### /system/shutdown

A message will be posted here just before the system shuts down or
restarts unless it shuts down due to SIGKILL or a bad error or some
other non-graceful cause

### /system/errors/events/\*module\*/\*event\*

Mhen an error occurs in a module, A message will be broadcast on this
topic,where module and event are the relevant module and event.

### system/errors/workers

When an error occurs in Kaithem's background worker pool, it will be
logged here. There could possibly be a lot of traffic here if a realtime
event decides to spew a bunch.

### /system/notifications

All messages broadcasted to this topic will appear on the front page.
They should be normal text strings, and should not contain any time
information as they will be listed by time on the front page anyway.
Care must be taken not to flood the front page and thereby hide
important messages. Only system-wide or major events should be logged
here. One should subscribe to "/system/notifications/" with the trailing
slash, as many messages are posted to subtopics.

### /system/notifications/errors

Messages here are like normal system/notifications/ messages, but are
semantically errors, and can show in red in the logs, or trigger sounds,
or send out text messages, or similar. Again, only fairly important
things should go here, as they will be listed on the front page. Use for
things like power failure, network connectivity loss, etc.  
Where possible one should wait ten seconds or so before sending a
message for something that might resolve itself, like a network issue.

### /system/notifications/warnings

These messages show in yellow in the front page and the logs. Use for
generic warnings.

### /system/notifications/important

Messages show highlighted in logs. Use for things that you want to be
noticed, but don't neccesarily require immediate action, like when a
connection has been established or restored with a server, The system
boots up, or to notify of important events, store opening hours, etc.
Routine things that happen frequently such as "main battery fully
charged" shouldn't be put here.

### /system/modules/loaded

When a module has fully initialized, it's name is posted here.

### /system/modules/unloaded

When a module has been deleted, it's name is posted here.

### /system/modules/events/loaded

The module and resource of any event that loads or reloads gets posted
here.

NOTE: the message logging system means that anyone with the
/users/logs.view permission can see all traffic on the message bus,
because even topics not set up to be logged are kept in ram and shown on
the logs page for a short time. Be careful to either not send any
private data on the message bus, or be very careful who you give
permission to see the logs.

### system/auth/login

When a user logs in, his username and IP are posted here as a two
element list.

### system/auth/logout

When a user logs out, his username and IP are posted here as a two
element list.

### system/auth/loginfail

When a user fails to logs in, his username and IP are posted here as a
two element list.

<span id="logging"></span>Logging
---------------------------------

Kaithem's logging was formerly based on JSON dumps of filtered message
bus traffic, but now uses python's native logging module. A special
logger called "system" is used, and anything logged to that logger will
be logged to the output file.

Logging defaults to disabled, so if you want to use logging you will
need to set log-format to normal.

This new method allows you to view realtime streaming logs. Note that
some things are still be logged to the message bus for now, like event
errors, for conveinence.

You can still configure topics to be forwarded from the message bus to
the logger What specific get logged is configurable from the logs page,
which also allows you to see the messages in the staging area. Log dumps
are in JSON format as one big dict of lists of messages indexed by
topic, where each message is an array of (timestamp,message)

Configuration options like log-format still work, although only
normal(semi-normal python log file output), and none(no logging to disk)
work

The new option log-buffer determines how many entries to buffer before
dumping to file. A new file is started after log-dump-size entries. With
log-buffer==1, you can append each entry to the file in real time,
similar to other programs.

If using compression, log-buffer must == log-dump-size, because we don't
support appending compressed files yet.

Log dumps will be found in kaithem/var/logs/dumps while the list of
messagebus topics to forward will be in kaithem/var/logs

<span id="email"></span>Email Alerts
------------------------------------

Kaithem can be configured to [send email](#kdotmail) through an SMTP
server. Go to the settings page to configure this. You can also create
mailing lists, to make mail alerting easier to manage. You create these
on the settings page. Mailing lists are uniquely identified by a base64
string called a UUID that ends in two equals signs. For every list you
create, a corresponding permission will be created containing the UUID.
You must have that permission to subscribe to a list. Every user can
enter an email address and recieve alerts from any list he has the
correct permissions to subscribe to.

&lt;%include file="/pagefooter.html"/&gt;
