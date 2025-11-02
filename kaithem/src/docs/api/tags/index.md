# kaithem.api.tags

## Classes

| [`BinaryTagPointClass`](#kaithem.api.tags.BinaryTagPointClass)   | A Tag Point is a named object that can be chooses from a set of data sources based on priority,   |
|------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| [`Claim`](#kaithem.api.tags.Claim)                               | Represents a claim on a tag point's value                                                         |
| [`GenericTagPointClass`](#kaithem.api.tags.GenericTagPointClass) | A Tag Point is a named object that can be chooses from a set of data sources based on priority,   |
| [`NumericTagPointClass`](#kaithem.api.tags.NumericTagPointClass) | A Tag Point is a named object that can be chooses from a set of data sources based on priority,   |
| [`ObjectTagPointClass`](#kaithem.api.tags.ObjectTagPointClass)   | A Tag Point is a named object that can be chooses from a set of data sources based on priority,   |
| [`StringTagPointClass`](#kaithem.api.tags.StringTagPointClass)   | A Tag Point is a named object that can be chooses from a set of data sources based on priority,   |

## Functions

| [`all_tags_raw`](#kaithem.api.tags.all_tags_raw)(→ dict[str, ...)                          | Return a dict of weakrefs to all existing tag points.               |
|--------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`existing_tag`](#kaithem.api.tags.existing_tag)(...)                                      | Return tag by that name, of any type, if it exists, else None       |
| [`normalize_tag_name`](#kaithem.api.tags.normalize_tag_name)(s)                            | Add the leading / if needed, and normalize kebab-case to snake_case |
| [`NumericTag`](#kaithem.api.tags.NumericTag)(→ kaithem.src.tagpoints.NumericTagPointClass) | Create a tag, if it already exists, return that one                 |
| [`StringTag`](#kaithem.api.tags.StringTag)(→ kaithem.src.tagpoints.StringTagPointClass)    | Create a tag, if it already exists, return that one                 |
| [`ObjectTag`](#kaithem.api.tags.ObjectTag)(→ kaithem.src.tagpoints.ObjectTagPointClass)    | Create a tag, if it already exists, return that one                 |
| [`BinaryTag`](#kaithem.api.tags.BinaryTag)(→ kaithem.src.tagpoints.BinaryTagPointClass)    | Create a tag, if it already exists, return that one                 |

## Module Contents

### *class* kaithem.api.tags.BinaryTagPointClass(name: str)

Bases: [`GenericTagPointClass`](#kaithem.api.tags.GenericTagPointClass)[`bytes`]

A Tag Point is a named object that can be chooses from a set of data sources based on priority,
filters that data, and returns it on a push or a pull basis.

A data source here is called a "Claim", and can either be a number or a function. The highest
priority claim is called the active claim.

If the claim is a function, it will be called at most once per interval, which is set by tag.interval=N
in seconds. However the filter function is called every time the data is requested.

If there are any subscribed functions to the tag, they will automatically be called at the tag's interval,
with the one parameter being the tag's value. Any getter functions will be called to get the value.

One generally does not instantiate a tag this way, instead they use the Tag function
which can get existing tags. This allows use of tags for cross=

#### default_data *: bytes* *= b''*

#### type *= 'binary'*

#### vta *: tuple[bytes, float, Any]*

#### validate *= None*

#### processValue(value)

Represents the transform from the claim input to the output.
Must be a pure-ish function

#### filterValue(v)

Pure function that returns a cleaned up or normalized version of the value

### *class* kaithem.api.tags.Claim(tag: [GenericTagPointClass](#kaithem.api.tags.GenericTagPointClass)[T], value: T, name: str = 'default', priority: int | float = 50.0, timestamp: int | float | None = None, annotation=None)

Bases: `Generic`[`T`]

Represents a claim on a tag point's value

#### name *= 'default'*

#### tag

#### vta *: tuple[T | collections.abc.Callable[[], T | None], float, Any]*

#### cachedValue *: tuple[T | None, int | float]*

#### lastGotValue *= 0.0*

#### effective_priority *= 50.0*

#### priority *= 50.0*

#### poller *= None*

#### released *= False*

#### \_\_del_\_()

#### \_\_lt_\_(other)

#### \_\_eq_\_(other) → bool

#### *property* value

#### *property* timestamp

#### *property* annotation

#### set(value, timestamp: float | None = None, annotation: Any = None)

#### release()

#### set_priority(priority: float, realPriority: bool = True)

#### \_\_call_\_(\*args, \*\*kwargs)

### *class* kaithem.api.tags.GenericTagPointClass(name: str)

Bases: `Generic`[`T`]

A Tag Point is a named object that can be chooses from a set of data sources based on priority,
filters that data, and returns it on a push or a pull basis.

A data source here is called a "Claim", and can either be a number or a function. The highest
priority claim is called the active claim.

If the claim is a function, it will be called at most once per interval, which is set by tag.interval=N
in seconds. However the filter function is called every time the data is requested.

If there are any subscribed functions to the tag, they will automatically be called at the tag's interval,
with the one parameter being the tag's value. Any getter functions will be called to get the value.

One generally does not instantiate a tag this way, instead they use the Tag function
which can get existing tags. This allows use of tags for cross=

#### DEFAULT_ANNOTATION *= '1d289116-b250-482e-a3d3-ffd9e8ac2b57'*

#### default_data *: T*

#### type *= 'object'*

#### mqtt_encoding *= 'json'*

#### \_\_repr_\_()

#### name *: str*

Internal use only, holds references to logger objects

#### configLoggers *: weakref.WeakValueDictionary[str, object]*

#### aliases *: set[str]*

#### description *: str* *= ''*

#### vta *: tuple[T | collections.abc.Callable[[], T | None], float, Any]*

#### unreliable *: bool* *= False*

#### last_value *: T*

#### active_claim *: None | [Claim](#kaithem.api.tags.Claim)[T]* *= None*

#### writable *= True*

Dict used as globals and locals for evaluating
alarm conditions and expression tags.

#### eval_context

When was the last time we got *real* new data

#### last_got_value *: int | float* *= 0*

#### owner *: str* *= ''*

#### default_claim *= None*

#### *property* timestamp *: float*

#### *property* annotation *: Any*

#### isDynamic() → bool

#### expose(read_perms: str | list[str] = '', write_perms: str | list[str] = 'system_admin', expose_priority: str | int | float = 50)

Expose the tag to web APIs, with the permissions specified. Permissions must be
strings, but can use commas for multiple.

Priority must be an integer, and determines the priority at which the web
API may set the tag's value.  The web API cannot control the priority, but
can release the claim entirely by sending a null, or reclaim by sending real
data again.

The way this works is that tag.data_source_widget is created, a
Widgets.DataSource instance having id "[tag:TAGNAME](tag:TAGNAME)", with the given
permissions.

Messages TO the server will set a claim at the permitted priority, or release any
claim if the data is None. Data FROM the server indicates the actual current
value of the tag.

You must always have at least one read permission, and write_perms defaults
to \_\_admin_\_.   Note that if the user sets or configures any permissions
via the web API, they will override those set in code.

If read_perms or write_perms is empty, disable exposure.

You cannot have different priority levels for different users this way, that
would be highly confusing. Use multiple tags or code your own API for that.

#### *static* makeWeakApiHandler(wr) → collections.abc.Callable[[str, T | None], None]

#### apiHandler(u, v: T | None)

#### get_effective_permissions() → tuple[str, str, float]

Get the permissions that currently apply here. Configured ones override in-code ones

Returns:
: list: [read_perms, write_perms, writePriority]. Priority determines the priority of web API claims.

#### testForDeadlock()

Run a check in the background to make sure this lock isn't clogged up

#### recalc(\*a: Any, \*\*k: Any)

Just re-get the value as needed

#### set_alarm(name: str, condition: str | None = '', priority: str = 'info', release_condition: str | None = '', auto_ack: bool = False, trip_delay: float | int | str = '0') → [kaithem.src.alerts.Alert](../../src/alerts/index.md#kaithem.src.alerts.Alert) | None

#### recalc_alarm_self_subscriber(value: T, timestamp: float, annotation: Any)

#### recalc_alerts()

#### createGetterFromExpression(e: str, priority: int | float = 98) → [Claim](#kaithem.api.tags.Claim)[T]

Create a getter for tag self using expression e

#### *property* interval

Set the sample rate of the tags data in seconds.
Affects polling and cacheing if getters are used.

#### *property* subtype

A string that determines a more specific type.  Use a com.site.x name, or
something like that, to avoid collisions.

"Official" ones include bool, which can be 1 or 0, or tristate, which can be
-1 for unset/no effect, 0, or 1.

#### *property* default *: T*

#### *classmethod* Tag(name: str, defaults: dict[str, Any] = {})

#### *property* current_source *: str*

Return the Claim object that is currently
controlling the tag

#### filterValue(v: T) → T

Pure function that returns a cleaned up or normalized version of the value

#### \_\_del_\_()

#### \_\_call_\_(\*args, \*\*kwargs)

Equivalent to calling set() on the default handler. If
no args are provided, just returns the tag's value.

#### fast_push(value: T, timestamp: float | None = None, annotation: Any = None) → None

Push a value to all subscribers. Does not set the tag's value.  Ignores any and all
overriding claims.
Bypasses all claims. Does not guarantee to get any locks, multiples of this call can happen at once.
Does not perform any checks on the value.  Might decide to do nothing if the system is too busy at the moment.

Meant for streaming video and the like.

#### subscribe(f: collections.abc.Callable[[T, float, Any], Any], immediate: bool = False)

f will be called whe the value changes, as long
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

#### unsubscribe(f: collections.abc.Callable[[T, float, Any], Any])

#### poll()

#### processValue(value) → T

Represents the transform from the claim input to the output.
Must be a pure-ish function

#### *property* age

#### *property* value *: T*

#### pull() → T

Return the value from a tag, forcing a new update from the getter without
any caching. May also trigger the subscribers if the value changes.

#### add_alias(alias: str)

Adds an alias of this tag, allowing access by another name.

#### remove_alias(alias: str)

Removes an alias of this tag

#### claim(value: T | collections.abc.Callable[[], T | None], name: str | None = None, priority: float | None = None, timestamp: float | None = None, annotation: Any = None) → [Claim](#kaithem.api.tags.Claim)[T]

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

#### set_claim_val(claim: str, val: T | collections.abc.Callable[[], T | None] | Any, timestamp: float | None, annotation: Any)

Set the value of an existing claim

#### claimFactory(value: Any, name: str, priority: float, timestamp: float, annotation: Any)

#### get_top_claim() → [Claim](#kaithem.api.tags.Claim)[T]

#### release(name: str)

### *class* kaithem.api.tags.NumericTagPointClass(name: str, min: float | None = None, max: float | None = None)

Bases: [`GenericTagPointClass`](#kaithem.api.tags.GenericTagPointClass)[`float`]

A Tag Point is a named object that can be chooses from a set of data sources based on priority,
filters that data, and returns it on a push or a pull basis.

A data source here is called a "Claim", and can either be a number or a function. The highest
priority claim is called the active claim.

If the claim is a function, it will be called at most once per interval, which is set by tag.interval=N
in seconds. However the filter function is called every time the data is requested.

If there are any subscribed functions to the tag, they will automatically be called at the tag's interval,
with the one parameter being the tag's value. Any getter functions will be called to get the value.

One generally does not instantiate a tag this way, instead they use the Tag function
which can get existing tags. This allows use of tags for cross=

#### default_data *= 0*

#### type *= 'number'*

#### vta *: tuple[float, float, Any]*

#### default_claim *: [NumericClaim](../../src/tagpoints/index.md#kaithem.src.tagpoints.NumericClaim)*

#### enum

#### trigger()

Used for tags with subtype: trigger, for
things that are triggered on changes to nonzero values.

this just increments the value, wrapping at
2\*\*20, and wrapping to 1 instead of 0.

#### processValue(value: float | int)

Represents the transform from the claim input to the output.
Must be a pure-ish function

#### filterValue(v: float) → float

Pure function that returns a cleaned up or normalized version of the value

#### claimFactory(value: float | collections.abc.Callable[[], float | None], name: str, priority: float, timestamp: float, annotation: Any)

#### *property* min *: float | int*

Set the range of the tag point. Out of range
values are clipped. Default is None.

#### *property* max *: float | int*

Set the range of the tag point. Out of range
values are clipped. Default is None.

#### *property* hi *: float | int*

#### *property* lo *: float | int*

#### convert_to(unit: str)

Return the tag's current value converted to the given unit

#### convert_value(value: float | int, unit: str) → float | int

Convert a value in the tag's native unit to the given unit

#### *property* unit

A string that determines the unit of a tag. Units are
expressed in strings like "m" or "degF". Currently only a small number of
unit conversions are supported natively and others use pint, which is not as
fast.

SI prefixes should not be used in units, as it interferes with
auto-prefixing for display that meter widgets can do, and generally
complicates coding.

This includes kilograms, Grams should be used for internal calculations instead despite Kg being the
base unit according to SI.

Note that operations involving units raise an error if the unit is not set.
To prevent this, both the "sending" and "recieving" code should set the unit
before using the tag.

To prevent the very obvious classes of errors where different code thinks a
unit is a different thing, this property will not allow changes once it has
been set. You can freely write the same string to it, and you can set it to
None and then to a new value if you must, but you cannot change between two
strings without raising an exception.

For some units, meters will become "unit aware" on the display page.

#### set_as(value: float, unit: str, timestamp: float | None = None, annotation: Any = None)

Set the default claim, with unit conversion.

#### *property* display_units

This can be None, or a pipe-separated string listing one or more units that
the tag's value should be displayed in. Base SI units imply that the correct
prefix should be used for readability, but units that contain a prefix imply
fixed display only in that unit.

### *class* kaithem.api.tags.ObjectTagPointClass(name: str)

Bases: [`GenericTagPointClass`](#kaithem.api.tags.GenericTagPointClass)[`dict`[`str`, `Any`]]

A Tag Point is a named object that can be chooses from a set of data sources based on priority,
filters that data, and returns it on a push or a pull basis.

A data source here is called a "Claim", and can either be a number or a function. The highest
priority claim is called the active claim.

If the claim is a function, it will be called at most once per interval, which is set by tag.interval=N
in seconds. However the filter function is called every time the data is requested.

If there are any subscribed functions to the tag, they will automatically be called at the tag's interval,
with the one parameter being the tag's value. Any getter functions will be called to get the value.

One generally does not instantiate a tag this way, instead they use the Tag function
which can get existing tags. This allows use of tags for cross=

#### default_data *: dict[str, Any]*

#### type *= 'object'*

#### vta *: tuple[dict[str, Any], float, Any]*

#### validate *= None*

#### processValue(value)

Represents the transform from the claim input to the output.
Must be a pure-ish function

#### filterValue(v)

Pure function that returns a cleaned up or normalized version of the value

### *class* kaithem.api.tags.StringTagPointClass(name: str)

Bases: [`GenericTagPointClass`](#kaithem.api.tags.GenericTagPointClass)[`str`]

A Tag Point is a named object that can be chooses from a set of data sources based on priority,
filters that data, and returns it on a push or a pull basis.

A data source here is called a "Claim", and can either be a number or a function. The highest
priority claim is called the active claim.

If the claim is a function, it will be called at most once per interval, which is set by tag.interval=N
in seconds. However the filter function is called every time the data is requested.

If there are any subscribed functions to the tag, they will automatically be called at the tag's interval,
with the one parameter being the tag's value. Any getter functions will be called to get the value.

One generally does not instantiate a tag this way, instead they use the Tag function
which can get existing tags. This allows use of tags for cross=

#### default_data *= ''*

#### unit *= 'string'*

#### type *= 'string'*

#### mqtt_encoding *= 'utf8'*

#### vta *: tuple[str, float, Any]*

#### processValue(value)

Represents the transform from the claim input to the output.
Must be a pure-ish function

#### filterValue(v)

Pure function that returns a cleaned up or normalized version of the value

### kaithem.api.tags.all_tags_raw() → dict[str, weakref.ref[[kaithem.src.tagpoints.GenericTagPointClass](../../src/tagpoints/index.md#kaithem.src.tagpoints.GenericTagPointClass)]]

Return a dict of weakrefs to all existing tag points.

### kaithem.api.tags.existing_tag(s) → [kaithem.src.tagpoints.GenericTagPointClass](../../src/tagpoints/index.md#kaithem.src.tagpoints.GenericTagPointClass) | None

Return tag by that name, of any type, if it exists, else None

### kaithem.api.tags.normalize_tag_name(s: str)

Add the leading / if needed, and normalize kebab-case to snake_case

### kaithem.api.tags.NumericTag(k: str) → [kaithem.src.tagpoints.NumericTagPointClass](../../src/tagpoints/index.md#kaithem.src.tagpoints.NumericTagPointClass)

Create a tag, if it already exists, return that one

### kaithem.api.tags.StringTag(k: str) → [kaithem.src.tagpoints.StringTagPointClass](../../src/tagpoints/index.md#kaithem.src.tagpoints.StringTagPointClass)

Create a tag, if it already exists, return that one

### kaithem.api.tags.ObjectTag(k: str) → [kaithem.src.tagpoints.ObjectTagPointClass](../../src/tagpoints/index.md#kaithem.src.tagpoints.ObjectTagPointClass)

Create a tag, if it already exists, return that one

### kaithem.api.tags.BinaryTag(k: str) → [kaithem.src.tagpoints.BinaryTagPointClass](../../src/tagpoints/index.md#kaithem.src.tagpoints.BinaryTagPointClass)

Create a tag, if it already exists, return that one
