from kaithem.src import tagpoints


## handsdown not picking up module docstring
def tags_docstring():
    """## Tag Points

    ### The TagPoint object

    TagPoints are threadsafe containers for variables that provide easy
    debugging and subscription to changes.

    TagPoints are created on demand. To create a tagpoint
      holding a number, use kaithem.api.tags.NumericTag(name).

    Once a tag exists, it shows up in the tags listing page.

    If a TagPoint already exists when you request it, you get that one instead.
    Tags exist until there are no more references or claims on them, and all
    properties may be reconfigured on the fly. this allows them to be used for
    loose coupling between different parts of a program.


    Tag point values have an associated timestamp and annotation(Which have
    defaults, and you can ignore), that follow the values, allowing advanced
    patterns and loop avoidance with remote systems.

    When a tag is first created, it's value is the default for that type, and
    it's timestamp will be 0.

    The annotation is an arbitrary python object, and the timestamp is always in
    the time.time() scale.

    It is suggested that you not do anything with annotations besides equality
    testing, or that you always typecheck the value as it defaults to None.



    ### Locking

    When you write to a tag, it will call all subscribers under a reentrant
    lock. This of course, means that it is possible to create deadlocks if you
    do something really crazy.

    To prevent this, tags have a timeout, of around ten seconds, after which
    they will give up on most actions and raise a RuntimeError.

    As kaithem is all about auto-retry in case of error, this should save you
    from most mistakes, but you should still be aware.

    Reading from tags may or may not involve the lock, due to caching.

    You can always break possible lock cycles by doing something in a background
    thread, if the application can handle it.


    ### Expression Tags Any tag having a name that begins with an equals sign
    will be created with a getter that evaluates the name as an expression. The
    priority of the expression source will be 98.

    You have access to time, math, random, re, plus the tag itself as 'tag', and
    anything else you put in tag.eval_context in code.


    #### the tv(n) function

    The tv function is used from within a tag expression. It returns the value
    of a numeric tag with the given name, and adds the tag to the list of source
    tags.

    The tag will re-eval the expression whenever a source tag has new data.

    Updating the config data via the interface will reset the list of source
    tags.

    ### Error Handling Errors in getters are logged, and the most recent value
    is used. Errors in setters are logged.

    #### TagPoint.value

    Property that can get the tag's value, or set the value of the default
    claim.

    Errors in getters will never cause an error to be raised getting or setting
    this.


    #### TagPoint.min, TagPoint.max Set the range of the tag point. Out of range
    values are clipped. Default is None. Setting does bothing if overridden by
    configuration.

    #### TagPoint.interval Set the sample rate of the tags data in seconds.
    Affects polling and cacheing. Setting does nothing if overridden by
    configuration.


    #### TagPoint.subscribe(f) f will be called whe the value changes, as long
    as the function f still exists.

    It will also be called the first time you set a tag's value, even if the
    value has not changed.

    It should very very rarely be called on repeated values otherwise, but this
    behavior is not absolutelu guaranteed and should not be relied on.

    All subscribers are called synchronously in the same thread that set the
    value, however any errors are logged and ignored.

    They will all be called under the tagpoint's lock. To avoid various problems
    like endless loops, one should be careful when accessing the tagpoint itself
    from within this function.




    The signature of f must be: f(value, timestamp, annotation)

    #### TagPoint.set_handler(f)

    Similar to subscribe, except the handler is us called before the value is
    actually stored, before any subscribers, and any errors are simply unhandled
    and will we raised in the thread that tried to set the value.

    A tag may only have one handler, and the tag strongly references it.



    #### TagPoint.unit A string that determines the unit of a tag. Units are
    expressed in strings like "m" or "degF". Currently only a small number of
    unit conversions are supported natively and others use pint, which is not as
    fast.

    SI prefixes should not be used in units, as it interferes with
    auto-prefixing for display that meter widgets can do, and generally
    complicates coding. This includes kilograms.

    Grams should be used for internal calculations instead despite Kg being the
    base unit according to SI.


    Note that operations involving units raise an error if the unit is not set.
    To prevent this, both the "sending" and "recieving" code should set the unit
    before using the tag.

    To prevent the very obvious classes of errors where different code thinks a
    unit is a different thing, this property will not allow changes once it has
    been set. You can freely write the same string to it, and you can set it to
    None and then to a new value if you must, but you cannot change between two
    strings without raising an exception.

    This property can't currently be configured through the UI.

    For some units, meters will become "unit aware" on the display page.

    #### TagPoint.subtype

    A string that determines a more specific type.  Use a com.site.x name, or
    something like that, to avoid collisions.

    "Official" ones include bool, which can be 1 or 0, or tristate, which can be
    -1 for unset/no effect, 0, or 1.


    #### TagPoint.display_units

    This can be None, or a pipe-separated string listing one or more units that
    the tag's value should be displayed in. Base SI units imply that the correct
    prefix should be used for readability, but units that contain a prefix imply
    fixed display only in that unit.

    #### TagPoint.convert_to(unit) Return the value in the given unit

    #### TagPoint.convert_value(value,unit) Value must be a number in the tag's
    native unit. Returns the value after converting.


    #### TagPoint.claim(value, name, priority, timestamp=None, annotation=None)
    Adds a claim to the tag and returns the Claim object. The claim will
    dissapear if the returned Claim object ever does. Value may be a function
    that can be polled to return a float, or a number.

    If a function is provided, it may return None to indicate no new data has
    arrived. This will not update the tags age.

    Should a claim already exist by that name, the exact same claim object as
    the previous claim is returned.

    Rather than using multiple claims, consider whether it's really needed, lots
    of builtin functionality in the UI is mean to just work with the default
    claim, for ease of use.


    ### tagPoint.pull()

    Return the value from a tag, forcing a new update from the getter without
    any caching. May also trigger the subscribers if the value changes.

    ##### TagPoint.eval_context

    Dict used as globals and locals for evaluating
    alarm conditions and expression tags.



    #### tagPoint.expose(readPerm, writePerm, priority, configured=False)

    Expose the tag to web APIs, with the permissions specified. Permissions must be
    strings, but can use commas for multiple.

    Priority must be an integer, and determines the priority at which the web
    API may set the tag's value.  The web API cannot control the priority, but
    can release the claim entirely by sending a null, or reclaim by sending real
    data again.


    The way this works is that tag.data_source_widget is created, a
    Widgets.DataSource instance having id "tag:TAGNAME", with the given
    permissions.


    TO the server will set a claim at the permitted priority, or release any
    claim if the data is None. FROM the server indicates the actual current
    value of the tag.


    A second widget, tag.control:TAGNAME is also created.  This widget is
    write-only, it is not affected by changes to the tagpoint itself, but it
    will sync between different users.

    This means that you can write a Null to it, and everyone will be able to see
    that null, while also reading back the real currect tag value set from other
    claims.



    You must always have at least one read permission, and write_perms defaults
    to `__admin__`.   Note that if the user sets or configures any permissions
    via the web API, they will override those set in code.

    If read_perms or write_perms is empty, disable exposure.

    You cannot have different priority levels for different users this way, that
    would be highly confusing. Use multiple tags or code your own API for that.

    If configured is True, will actually set the persistant config rather than
    the runtime config. This will not be made permanent till the user clicks
    "save server state to disk".



    #### tagPoint.get_effective_permissions()

    Returns the read, write, and max priority permissions currently in effect.


    #### tagPoint.expose() Cancels any API exposure

    ##### TagPoint(v,t,a)

    Equivalent to calling set() on the default handler. If
    no args are provided, just returns the tag's value.

    ##### Claim.set(value,timestamp=None,annotation=None)

    Set the value of a
    claim. You can optionally also set the timestamp of the message.

    ##### Claim()

    Equivalent to claim.set(). This allows claims themselves to be
    subscribers for another tagpoint

    ##### Claim.set_as(value,unit,timestamp=None,annotation=None)

    Set the value
    of a claim with a value of the given unit, if neccesary, converts to the
    tag's native unit before setting. You can optionally also set the timestamp
    of the message.

    #### TagPoint.current_source

    Return the Claim object that is currently
    controlling the tag

    ##### Claim.release() Release a claim.



    ### StringTags

    StringTags are created or fetched on demand by kaithem.tags.StringTag(name).
    They function exactly like regular tagpoints, minus all features relating to
    unit conversion.

    ### ObjectTags

    ObjectTags are created or fetched on demand by kaithem.tags.StringTag(name).
    They are just like any other tag, but the value must be a JSON serializable
    object.

    ### BinaryTag

    BinaryTags are created or fetched on demand by kaithem.tags.BinaryTag(name).
    The value of a binary tag is always a bytes object, defaulting to empty.

    You can set the default value from the management page for any particular
    tag, but for BinaryTags it will be interpreted as a hex string.

    ### Get arbitrary existing tag ignoring type

    kaithem.tags.all_tags_raw is a dict containing a weak reference to every
    tag.  It allows raw access to the internal tags list.

    kaithem.tags.all_tags_raw['foo']() gets you the foo tag.

    #### BinaryTag.unreliable

    Set to true, makes tag act more like a UDP connection. Setting the value
    just pushed to subscribers. Polling not guaranteed to work. Type checking
    disabled.

    #### BinaryTag.fast_push(self, value,timestamp=None, annotation=None)

    Just notify sbscribers. Use with unreliable mode.  Does not set the value
    and ignores all claims and priorities. Allows tag points to be used for
    realtime media streaming.  Preferably, use MPEG 2 TS. Subtype should be
    "mpegts" and data packets must start at 188 byte boundaries for that.




    ### The Tag Point Classes

    TagPointClass, StringTagPointClass,ObjectTagPointClass, and
    BinaryTagPointClass  exist under kaithem.tags.

    Subclassing is a bad plan but you may want them for type hinting.

    ## The raw data API endpoint

    Create a websocket connection to the URL of this form:

    `globalThis.kaithemapi.wsPrefix()+"/widgets/wsraw?widgetid={obj.tagPoints[i].data_source_widget.uuid}",`

    And if you have read permissions, you will get tag data updates as raw data.
    Added to support video playback with mpegts.js
    """


def all_tags_raw():
    return tagpoints.allTagsAtomic


def existing_tag(s) -> tagpoints.GenericTagPointClass | None:
    "Return tag by that name, of any type, if it exists"
    s = normalize_tag_name(s)
    try:
        return tagpoints.allTagsAtomic[s]()
    except KeyError:
        return None


def normalize_tag_name(s: str):
    """Add the leading / if needed"""

    return tagpoints.normalize_tag_name(s)


def NumericTag(k: str) -> tagpoints.NumericTagPointClass:
    t = tagpoints.Tag(k)
    return t


def StringTag(k: str) -> tagpoints.StringTagPointClass:
    t = tagpoints.StringTag(k)
    return t


def ObjectTag(k: str) -> tagpoints.ObjectTagPointClass:
    t = tagpoints.ObjectTag(k)
    return t


def BinaryTag(k: str) -> tagpoints.BinaryTagPointClass:
    t = tagpoints.BinaryTag(k)
    return t


GenericTagPointClass = tagpoints.GenericTagPointClass
StringTagPointClass = tagpoints.StringTagPointClass
ObjectTagPointClass = tagpoints.ObjectTagPointClass
BinaryTagPointClass = tagpoints.BinaryTagPointClass
NumericTagPointClass = tagpoints.NumericTagPointClass
