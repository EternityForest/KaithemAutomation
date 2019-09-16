## Tag Points


### The TagPoint object

TagPoints are created on demand by acccessing them through kaithem.tags['tagname'].

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

### Error Handling
Errors in getters are logged, and the most recent value is used. Errors in setters are logged.

#### TagPoint.value

Property that can get the tag's value, or set the value of the default claim. 

Errors in getters will never cause an error to be raised getting or setting this.



#### TagPoint.min, TagPoint.max
Set the range of the tag point. Out of range values are clipped.

#### TagPoint.interval
Set the sample rate of the tags data in seconds. Affects polling and cacheing.

#### TagPoint.subscribe(f)
f will be called whe the value changes. Polling will only occur if interval
is nonzero and there is at least one subscriber.

The signature of f must be:
f(value, timestamp, annotation)


#### TagPoint.unit
A string that determines the unit of a tag. Units are expressed in strings like "m" or "degF". Currently only a small number 
of unit conversions are supported natively and others use pint, which is not as fast.

SI prefixes should not be used in units, as it interferes with auto-prefixing for display that meter widgets can do, and generally complicates coding. This includes kilograms. Grams should be used for internal calculations instead despite Kg being the base unit according to SI.


Note that operations involving units raise an error if the unit is not set. To prevent this,
both the "sending" and "recieving" code should set the unit before using the tag.

To prevent the very obvious classes of errors where different code thinks a unit is a different thing,
this property will not allow changes once it has been set. You can freely write the same string to it, and
you can set it to None and then to a new value if you must, but you cannot change between two strings without raising
an exception.

For some units, meters will become "unit aware" on the display page.


#### TagPoint.displayUnits

This can be None, or a pipe-separated string listing one or more units that the tag's value should be displayed in.
Base SI units imply that the correct prefix should be used for readability, but units that contain a prefix imply fixed
display only in that unit.

#### TagPoint.convertTo(unit)
Return the value in the given unit

#### TagPoint.convertValue(value,unit)
Value must be a number in the tag's native unit. Returns the value after converting.


#### TagPoint.claim(value, name, priority, timestamp=None, annotation=None)
Adds a claim to the tag. The claim will dissapear if the returned Claim object ever does.
Value may be a function that can be polled to return a float, or a number.

If a function is provided, it may return None to indicate no new data has arrived. This will not update the tags
age.

Should a claim already exist by that name, the exact same claim object as the previous claim is returned.

##### Claim.set(value,timestamp=None,annotation=None)
Set the value of a claim. You can optionally also set the timestamp of the message.

##### Claim.setAs(value,unit,timestamp=None,annotation=None)
Set the value of a claim with a value of the given unit, if neccesary, converts to the tag's
native unit before setting. You can optionally also set the timestamp of the message.


##### Claim.release()
Release a claim.