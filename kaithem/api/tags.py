import weakref

from kaithem.src import tagpoints
from kaithem.src.tagpoints import (
    BinaryTagPointClass,
    Claim,
    GenericTagPointClass,
    NumericTagPointClass,
    ObjectTagPointClass,
    StringTagPointClass,
)

"""
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


### Expression Tags

Any tag having a name that begins with an equals sign
will be created with a getter that evaluates the name as an expression. The
priority of the expression source will be 98.

You have access to time, math, random, re, plus the tag itself as 'tag', and
anything else you put in tag.context in code.


#### the tv(n) function

The tv function is used from within a tag expression. It returns the value
of a numeric tag with the given name, and adds the tag to the list of source
tags.

The tag will re-eval the expression whenever a source tag has new data.

Updating the config data via the interface will reset the list of source
tags.

### Error Handling Errors in getters are logged, and the most recent value
is used. Errors in setters are logged.


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


def all_tags_raw() -> dict[str, weakref.ref[tagpoints.GenericTagPointClass]]:
    "Return a dict of weakrefs to all existing tag points."
    return tagpoints.allTagsAtomic


def existing_tag(s) -> tagpoints.GenericTagPointClass | None:
    "Return tag by that name, of any type, if it exists, else None"
    s = normalize_tag_name(s)
    try:
        return tagpoints.allTagsAtomic[s]()
    except KeyError:
        return None


def normalize_tag_name(s: str):
    """Add the leading / if needed, and normalize kebab-case to snake_case"""

    return tagpoints.normalize_tag_name(s)


def NumericTag(k: str) -> tagpoints.NumericTagPointClass:
    "Create a tag, if it already exists, return that one"
    t = tagpoints.Tag(k)
    return t


def StringTag(k: str) -> tagpoints.StringTagPointClass:
    "Create a tag, if it already exists, return that one"
    t = tagpoints.StringTag(k)
    return t


def ObjectTag(k: str) -> tagpoints.ObjectTagPointClass:
    "Create a tag, if it already exists, return that one"
    t = tagpoints.ObjectTag(k)
    return t


def BinaryTag(k: str) -> tagpoints.BinaryTagPointClass:
    "Create a tag, if it already exists, return that one"
    t = tagpoints.BinaryTag(k)
    return t


__all__ = [
    "NumericTag",
    "StringTag",
    "ObjectTag",
    "BinaryTag",
    "all_tags_raw",
    "existing_tag",
    "normalize_tag_name",
    "GenericTagPointClass",
    "NumericTagPointClass",
    "StringTagPointClass",
    "ObjectTagPointClass",
    "BinaryTagPointClass",
    "Claim",
]
