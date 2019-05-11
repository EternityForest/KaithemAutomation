## Tag Points


### The TagPoint object

TagPoints are created on demand by acccessing them through kaithem.tags['tagname'].

All special chars are reserved in the names.

If a TagPoint already exists when you request it, you get that one instead. Tags
exist until there are no more references or claims on them, and all properties may
be reconfigured on the fly. this allows them to be used for loose coupling between different
parts of a program.

### Error Handling
Errors in getters are logged, and the most recent value is used. Errors in setters are logged.

#### TagPoint.value

Property that can get the tag's value, or set the value of the default claim. 

Errors in getters will never cause an error to be raised getting or setting this.

#### TagPoint.claim(value, name, priority)
Adds a claim to the tag. The claim will dissapear if the returned Claim object ever does.
Value may be a function that can be polled to return a float, or a number.

If a function is provided, it may return None to indicate no new data has arrived. This will not update the tags
age.

Should a claim already exist by that name, the exact same claim object as the previous claim is returned.
##### Claim.set(value)
Set the value of a claim

##### Claim.release()
Release a claim.

#### TagPoint.min, TagPoint.max
Set the range of the tag point. Out of range values are clipped.

#### TagPoint.interval
Set the sample rate of the tags data in seconds. Affects polling and cacheing.

#### TagPoint.subscribe(f)
f will be called whe the value changes. Polling will only occur if interval
is nonzero and there is at least one subscriber.

