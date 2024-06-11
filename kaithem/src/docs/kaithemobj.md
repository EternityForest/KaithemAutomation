
# Help

## The Kaithem Object:


The Kaithem object is one object available in almost all user defined
code. It has the following properties:

### General Utilities

### kaithem.units

It is recommended that you use [Scullery](https://github.com/EternityForest/scullery) unit conversions directly.


#### kaithem.units.convert(value, fr, to)
Convert a value from unit fr to unit to. Both are expressed as strings,
like "degC" to "degF". Note that there is no protection against all nonsensical conversions.




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

It is recommended that you use workers.do() from [Scullery](https://github.com/EternityForest/scullery) directly.


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

#### kaithem.devices.device\_types
Device driver classes all go here.

#### kaithem.devices.Device
This is the base class you would use to create a new device.


### kaithem.resource

A dict-like object allowing you to access resources by module, resource tuple.



### kaithem.states

This namespace used to deal with kaithem's state machine library.  It is removed and recommended that you use [Scullery](https://github.com/EternityForest/scullery) state machines directly.


### kaithem.alerts

Alerts allow you to create notification when unusual events occur,
trigger periodic sounds, and allow users to "acknowledge" them to shut
them up.

#### kaithem.alerts.Alert(name, priority="normal", zone=None, trip\_delay=0, auto\_ack=False, permissions=\[\], ackPermissions=\[\], \[id\],description='')

Create a new alert. Prority can be one of debug, info, warning, error,
or critical.

Zone should be a heirarchal dot-separated locator string if present,
telling the physical location being monitored. An example might be
"us.md.baltimore.123setterst.shed", but at present you can use whatever
format you like.

Permissions and ackPermissions are additional permissions besides
view\_status and /users/alerts.acknowledge that are needed to see
and ack the alert.

ID is a unique string ID. What happens if you reuse these is undefined
and wil be used to implement features later.

trip\_delay is the delay in seconds that the alarm remains tripped before
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

#### kaithem.time.uptime()

Return the number of seconds as a float that kaithem has been running
for. Useful for event triggers if you want to do something a certain
number of seconds after kaithem loads.

#### kaithem.time.strftime(timestamp)

Format a time in seconds since the epoch according to the user's
preference. When called outside of a page, format according to the
default

#### kaithem.time.moon\_phase()

Returns the current moon phase as a float number:

    0  = New moon
    7  = First quarter
    14 = Full moon
    21-28 = Last quarter


#### kaithem.time.sunrise\_time(lat=None,lon=None,date=None)
Returns the sunrise time on today's date, regardless of whether it is already passed or not.
Defaults to the server location, right now.  Date can be a date object.

#### kaithem.time.sunset\_time()
#### kaithem.time.civil\_dawn\_time()
#### kaithem.time.civil\_dusk\_time()
See above.

**NOTE: any of these may raise an exception if
there is no sunrise or sunset in the current day(as in some regions in
the arctic circle during some seasons).**

#### kaithem.time.is\_day(lat=None,lon=None)

Return true if it is before sunset in the given lat-lon location. If no
coordinates are supplied, the server location configured in the settings
page is used. If no location is configured, an error is raised.

#### kaithem.time.is\_night(lat=None,lon=None)

Return true if it is after sunset in the given lat-lon location. Kaithem
handles coordinates as floating point values. If no coordinates are
supplied, the server location configured in the settings page is used.
If no location is configured, an error is raised.

#### kaithem.time.is\_dark(lat=None,lon=None)

Return true if it is currently past civil twilight in the given lat-lon
location. Civil twilight is defined when the sun is 6 degrees below the
horizon. In some countries, drivers must turn on headlights past civil
twilight. Civil twilight is commonly used as the time to start using
artificial light sources. If no coordinates are supplied, the server
location configured in the settings page is used. If no location is
configured, an error is raised.

#### kaithem.time.is\_light(lat=None,lon=None)

Return true if it is not past civil twilight given lat-lon location. If
no coordinates are supplied, the server location configured in the
settings page is used. If no location is configured, an error is raised.

### kaithem.users

This namespace contains features for working with kaithem's user
management system.

#### kaithem.users.check\_permission(username, permission)

Returns True is the specified use has the given permission and False
otherwise. Also returns False if the user does not exist.

### kaithem.sound

It is recommended that you use [IceMedia](https://github.com/EternityForest/icemedia) sound APIs directly.  They are almost exactly the same as the old Kaithem APIs.



### kaithem.message


It is recommended that you use the message bus in [Scullery](https://github.com/EternityForest/scullery) directly, this was just a thin


### kaithem.widget

**See Widgets for info on how to use these. Unless otherwise mentioned,
their API is defined by the Widget base class.**


#### kaithem.widgets.APIWidget(echo=True)

This widget exists to allow you to create custom widgets easily. When
you render() it, you pass a parameter htmlid. The render function
returns a script that places an object into a global javascript variable
of that name. You can use obj.set(x) to set the widget's value to x, and
retrieve the widget's value with obj.value.



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


#### kaithem.web.nav\_bar\_plugins
This is a WeakValueDictionary that you can use to add items to the top navbar. Entries should have string keys, and
values must be a function that returns None for no item, or a tuple of (sort order, HTML).
HTML will typically be an a tag link.  Default sort order should be 50.

#### kaithem.web.add\_wsgi\_app(pattern: str, app, permission="system\_admin"):
Mount a WSGI application to handle all URLs matching the pattern regex.  The app will only be accessible
to users having the specified permission.

#### kaithem.web.add\_tornado\_app(pattern: str, app, args, permission="system\_admin"):
Mount a Tornado application to handle all URLs matching the pattern regex

##### Subdomains

Normally, the subdomain is entirely ignored, they act exactly like the main domain.  However, you can capture requests to a specific subdomain with:
a tuple like ("subdomain", "/","mountpoint").
For consistency, multiple subdomains are specified top-to-bottom, opposite the way URLs do them.  foo.bar.localhost/baz  maps to ('bar','foo', '/','baz).

You have to bind to an exact subdomain, entries do not match sub-subdomains of the one you specify.


Note that this does not allow you to bind to different main domains, only subdomains.  Ignoring the main domain simplifies access from multiple IPs.

Also note that you cannot capture ALL requests to a subdomain, only ones that do not map to an existing page so this cannot be a means of sandboxing.
However, as different subdomains have different cookies, you can create a certain level of safety if users never log into an "untrusted" subdomain.

Relying on users not to do this, however, seems like a fairly bad idea, so kaithem forbids logging in if the subdomain contains `\_\_nologin\_\_` as a path component.

Note that even with this protection, XSS can still do anything that a guest can do.


#### kaithem.web.go\_back()

When called from code embedded in an HTML page, raises an interrupt
causing an HTTP redirect to the previous page to be sent. Useful for
when you have a page that is only used for it's side effects.

#### kaithem.web.goto(url)

When called from code embedded in an HTML page, raises an interrupt
causing an HTTP redirect to the previous specified url to be sent.

#### kaithem.web.user()

When called from within a page, returns the usernae of the accessing
user or else an empty string if not logged in.

#### <span id="servefile"></span>kaithem.web.serve\_file(path,contenttype,name = path)

When called from code embedded in an HTML page,raises an interrupt
causing the server to skip rendering the current page and instead serve
a static file. Useful when you need to serve a static file and also need
to restrict acess to it with permissions.

Can serve a bytesIO object if mime and filename are provided, or any other object having a read(),
as long as you enable streming response on page config.


#### kaithem.web.has\_permission(permission)

When clled from within a mako template, returns true if the acessing
user has the given permission.


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

#### kaithem.string.si\_format(n,d=2)

Takes a number and formats it with suffixes. 1000 becomes 1K, 1,000,000
becomes 1M. d is the number of digits of precision to use.

#### kaithem.string.format\_time\_interval(n,places=2,clock=False)

Takes a length of time in secons and formats it. Places is the mx units
to use. format\_time\_interval(5,1) becomes ""5 seconds",
format\_time\_interval(65,2) returns "1 minute 5 seconds"

If clock==True, places is ignored and output is in HH:MM format. If
places is 3 or 4 format will be HH:MM:SS or HH:MM:SS:mmm where mmmm is
milliseconds.

### kaithem.plugin

This namespace contains tools for writing plugins for kaithem. A plugin
can be just a module that provides features, or it can be a python file
in src/plugins/startup, which will be automatically imported.

#### kaithem.plugin.add\_plugin(name,object)

Causes a weak proxy to object to become available at kaithem.name. The
object will be deleted as soon as there are no references to it. Note
that the automatic deletion feature may fail if the object has any
methods that return anything containing a strong reference to the object
itself.

If automatic collection of garbage in this manner is not important, and
your application is performance critical, you can directly insert
objects via attribute assignment, however that could cause other modules
to behave unpredictably when calling partially-deleted things.