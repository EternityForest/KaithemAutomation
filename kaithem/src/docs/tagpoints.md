## Tag Points


### The TagPoint object

TagPoints are containers for variables that provide easy debugging and subscription to changes.

Everything about them is completely threadsafe. This requires use of RLocks, which makes
them inappropriate for high-rate stuff.

Numeric TagPoints are created on demand by acccessing them through kaithem.tags['tagname'].

All special chars are reserved in the names.

If a TagPoint already exists when you request it, you get that one instead. Tags
exist until there are no more references or claims on them, and all properties may
be reconfigured on the fly. this allows them to be used for loose coupling between different
parts of a program.

Tag point values have an associated timestamp and annotation(Which have defaults, and you can ignore),
that follow the values, allowing advanced patterns and loop avoidance with remote systems.

The annotation is an arbitrary python object, and the timestamp is always in the time.monotonic()
scale.

It is suggested that you not do anything with annotations besides equality testing, or that you
always typecheck the value as it defaults to None.

### Configuration

The important thing to know about tag points is that they have two configurations: runtime and configured.

Runtime is set directly in code, but can be overridden on a per-setting basis bu configuration set through the web UI.

It is possible to create a tag point entirely via configuration.  Setting a type via the tag config page will cause it to be created when kaithem loads.

You may need to do this with tags that would otherwise be frequently created and destroyed, and thus disconnect from any UI widgets connected to them, in FreeBoard
panels or the like.


### Locking

When you write to a tag, it will call all subscribers under a reentrant lock.
This of course, means that it is possible to create deadlocks.

To prevent this, tags have a timeout, of around ten seconds after which they will give up on most actions and raise a RuntimeError. As kaithem is all about auto-retry in case of error, this shoud save you from most mistaks, but you should still be aware.

Reading from tags may or may not involve the lock, due to caching.

You can always break possible lock cycles by doing something in a background thread,
if the application can handle it.


### Expression Tags
Any tag having a name that begins with an equals sign will be created with a getter that evaluates the name as an expression.  The priority of the expression source will be 98.

You have access to time, math, random, re, and the kaithem object, plus the tag itself as 'tag', and anything else you put in tag.evalContext in code.

Note: tag point configuration is not part of a module and as such is a little harder to share, since you don't get the ZIP file uploads. You may want to create tags through code instead.

#### the tv(n) function

The tv function is used from within a tag expression. It returns the value of a numeric tag with the given name, and adds the tag to the list of source tags.

The tag will re-eval the expression whenever a source tag has new data.

Updating the config data via the interface will reset the list of source tags.

### Error Handling
Errors in getters are logged, and the most recent value is used. Errors in setters are logged.

#### TagPoint.value

Property that can get the tag's value, or set the value of the default claim.

Errors in getters will never cause an error to be raised getting or setting this.


#### TagPoint.min, TagPoint.max
Set the range of the tag point. Out of range values are clipped. Default is None.
Setting does bothing if overridden by configuration.

#### TagPoint.interval
Set the sample rate of the tags data in seconds. Affects polling and cacheing.
Setting does nothing if overridden by configuration.


#### TagPoint.subscribe(f)
f will be called whe the value changes, as long as the function f still exists.

It will also be called the first time you set a tag's value, even if the value has not changed.

It should very very rarely be called on repeated values otherwise, but this behavior is not absolutelu guaranteed and should not be relied on.

All subscribers are called synchronously in the same thread that set the value,
however any errors are logged and ignored.

They will all be called under the tagpoint's lock. To avoid various problems like
endless loops, one should be careful when accessing the tagpoint itself from within
this function.




The signature of f must be:
f(value, timestamp, annotation)

#### TagPoint.setHandler(f)

Similar to subscribe, except the handler is us called before the value is actually stored,
before any subscribers, and any errors are simply unhandled and will we raised in the thread
that tried to set the value.

A tag may only have one handler, and the tag strongly references it.



#### TagPoint.unit
A string that determines the unit of a tag. Units are expressed in strings like "m" or "degF". Currently only a small number
of unit conversions are supported natively and others use pint, which is not as fast.

SI prefixes should not be used in units, as it interferes with auto-prefixing for display that meter widgets can do,
and generally complicates coding. This includes kilograms.

Grams should be used for internal calculations instead despite Kg being the base unit according to SI.


Note that operations involving units raise an error if the unit is not set. To prevent this,
both the "sending" and "recieving" code should set the unit before using the tag.

To prevent the very obvious classes of errors where different code thinks a unit is a different thing,
this property will not allow changes once it has been set. You can freely write the same string to it, and
you can set it to None and then to a new value if you must, but you cannot change between two strings without raising
an exception.

This property can't currently be configured through the UI.

For some units, meters will become "unit aware" on the display page.

#### TagPoint.subtype

A string that determines a more specific type.  Use a com.site.x name, or something like that, to avoid collisions.

"Official" ones include bool, which can be 1 or 0, or tristate, which can be -1 for unset/no effect, 0, or 1.


#### TagPoint.display_units

This can be None, or a pipe-separated string listing one or more units that the tag's value should be displayed in.
Base SI units imply that the correct prefix should be used for readability, but units that contain a prefix imply fixed
display only in that unit.

#### TagPoint.convertTo(unit)
Return the value in the given unit

#### TagPoint.convertValue(value,unit)
Value must be a number in the tag's native unit. Returns the value after converting.


#### TagPoint.claim(value, name, priority, timestamp=None, annotation=None)
Adds a claim to the tag and returns the Claim object. The claim will dissapear if the returned Claim object ever does.
Value may be a function that can be polled to return a float, or a number.

If a function is provided, it may return None to indicate no new data has arrived. This will not update the tags
age.

Should a claim already exist by that name, the exact same claim object as the previous claim is returned.

Rather than using multiple claims, consider whether it's really needed, lots of builtin functionality in the UI is mean
to just work with the default claim, for ease of use.


### tagPoint.pull()

Return the value from a tag, forcing a new update from the getter without any caching. May also trigger the subscribers if the value changes.

##### TagPoint.evalContext
Dict used as globals and locals for evaluating alarm conditions and expression tags.



#### tagPoint.expose(readPerm, writePerm, priority, configured=False)
Expose the tag to web APIs, with the permissions specified. Permissions must be strings, but can use commas for multiple.

Priority must be an integer, and determines the priority at which the web API may set the tag's value.  The web API cannot control the priority, but can
release the claim entirely by sending a null, or reclaim by sending real data again.


The way this works is that tag.dataSourceWidget is created, a Widgets.DataSource instance having id "tag:TAGNAME", with the given permissions.


TO the server will set a claim at the permitted priority, or release any claim if the data is None.
FROM the server indicates the actual current value of the tag.


A second widget, tag.control:TAGNAME is also created.  This widget is write-only, it is not affected by changes to the tagpoint itself, but it will sync between different users.

This means that you can write a Null to it, and everyone will be able to see that null, while also reading back the real currect tag value set from other claims.



You must always have at least one read permission, and write_perms defaults to `__admin__`.   Note that if the user
sets or configures any permissions via the web API, they will override those set in code.

If read_perms or write_perms is empty, disable exposure.

You cannot have different priority levels for different users this way, that would be highly confusing. Use multiple tags
or code your own API for that.

If configured is True, will actually set the persistant config rather than the runtime config. This will not be made permanent till the user clicks "save server state to disk".


#### tagPoint.mqttConnect(self, **,server=None, port=1883, password=None,message_bus_name=None, mqttTopic=None, incomingPriority=None, incomingExpiration=None)

Used to connect a tag point for 2-way sync to an MQTT server.  When the tag's value changes, the value will be sent, JSON encoded if needed, to
the server at the selected topic, or under /tagpoints/TAGNAME.  Messages will be sent with the retain flag active.

When a message is incoming, it's value will set the local tag's value using a claim that has incomingPriority.

This uses Scullery's connection pool system. The suggested use is to leave the server blank, set and set a message_bus_name to use an existing connection
configured through the device manager.


You can use this to sync tags on two Kaithem instances, but the data has been kept as simple as possible so you can also use it to interact with other software.





Note that due to the use of the retain flag, upon reconnection to the server, the value may "snap back" to whatever the server thinks the value should be, the MQTT server
is the "source of truth" here.  Tag points are intended to represent one shared point kept on the server and are not "directional".

The incoming expiration tag will cause the claim representing MQTT data to expire if the data is more than that old.  Note that we currently only send data on changes, so this is of limited utility,
until we have a perioding rebroadcasting feature.

Upon expiration, the value will become that of the next highest claim, and this new value will be sent over the MQTT topic like anything else.




#### tagPoint.getEffectivePermissions()

Returns the read, write, and max priority permissions that are currently in effect, after merging in the web GUI config settings.  If nothing is set up, read abd write will be "",
and you should interpret this as meaning the tag should not be exposed.

Use this as a way to implement your own APIs, but keep the ability to use the standard web config.


#### tagPoint.expose()
Cancels any API exposure

##### TagPoint(v,t,a)
Equivalent to calling set() on the default handler. If no args are provided, just returns the tag's value.

##### Claim.set(value,timestamp=None,annotation=None)
Set the value of a claim. You can optionally also set the timestamp of the message.

##### Claim()
Equivalent to claim.set(). This allows claims themselves to be subscribers for another tagpoint

##### Claim.setAs(value,unit,timestamp=None,annotation=None)
Set the value of a claim with a value of the given unit, if neccesary, converts to the tag's
native unit before setting. You can optionally also set the timestamp of the message.

#### TagPoint.currentSource
Return the Claim object that is currently controlling the tag

##### Claim.release()
Release a claim.



### StringTags

StringTags are created or fetched on demand by kaithem.tags.StringTag(name). They function exactly like regular tagpoints,
minus all features relating to unit conversion.

### ObjectTags

ObjectTags are created or fetched on demand by kaithem.tags.StringTag(name). They are just like any other tag, but the value must be a JSON
serializable object.

### BinaryTag

BinaryTags are created or fetched on demand by kaithem.tags.BinaryTag(name). The value of a binary tag is always a bytes object, defaulting to empty.

You can set the default value from the management page for any particular tag, but for BinaryTags it will be interpreted as a hex string.

### Get arbitrary existing tag ignoring type

kaithem.tags.all_tags_raw is a dict containing a weak reference to every tag.  It
allows raw access to the internal tags list.

kaithem.tags.all_tags_raw['foo']() gets you the foo tag.

#### BinaryTag.unreliable

Set to true, makes tag act more like a UDP connection. Setting the value just pushed to subscribers. Polling not guaranteed to work. Type checking disabled.

#### BinaryTag.fastPush(self, value,timestamp=None, annotation=None)

Just notify sbscribers. Use with unreliable mode.  Does not set the value and ignores all claims and priorities. Allows tag points to be used for realtime
media streaming.  Preferably, use MPEG 2 TS. Subtype should be "mpegts" and data packets must start at 188 byte boundaries for that.






## Soft tags and Filtering

Kaithem has a specific API for filters. Custom filters are encouraged to use this pattern:

### Filter(name, inputTag, *,priority=60,interval=-1)

Create a tag with the name(Or use any existing tag), claim it with priority 60, and manage it as a filtered version of the input tag.
Both pull and push data must be supported.

interval only affects output tags, -1 indicates automatic.



### Filter.tag
This is always the output tag.


#### kaithem.tags.LowpassFilter(name, inputTag, timeConstant, priority=60,interval=-1)
BETA: My math could be off in this implementation

First-order lowpass filter with the given time constant in seconds



#### kaithem.tags.HighpassFilter(name, inputTag, timeConstant, priority=60,interval=-1)
BETA: My math could be off in this implementation

First-order highpass filter with the given time constant in seconds


#### kaithem.tags.HysteresisFilter(name, inputTag, hysteresis, priority=60,interval=-1)
BETA: My math could be off in this implementation

Suppress small changes with a hysteresis window.  If window is 3, and you set input to ten, respond immediately to positive change, but ignore negative change till
you get to 7.

Once at 7, the output will be 7, and positive changes will be ignored till you get back up to 10.  If you go to 11, the back of the window will then move to 8.


### The Tag Point Classes

TagPointClass, StringTagPointClass,ObjectTagPointClass, and BinaryTagPointClass  exist under kaithem.tags.

Subclassing is a bad plan but you mak want them for type hinting.

## The raw data API endpoint

Go to the URL of this form:

`kaithemapi.wsPrefix()+"/widgets/wsraw?widgetid=${obj.tagPoints[i].dataSourceWidget.uuid|u}",`

And if you have read permissions, you will get tag data updates as raw data. Added to support video playback with mpegts.js