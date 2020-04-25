# Kaithem Save File Formats


## Tag Configuration

Tags are saved as YAML, in VARDIR/tags/TAGNAME.  Folders are used here, a tag named /foo/bar will be saved at VARDIR/tags/foo/bar.

All keys can be strings, they are converted to the appropriate type as needed.
Empty strings represent unset properties. Almost everything is optional and will
use the default.

### Structure

```yaml
value: The default val when tag created
interval: Polling rate of tag

#Only applies to numerictags
hi: Value considered excessive. Overrides anything set in code
lo: Value considered too low. Overrides anything set in code
min: Minumum value. Overrides anything set in code
max: Max val. Overrides anything set in code

# Alarms. These are "Merged" with properties set in code.
alarms:
    alarmName:
        condition: "value>3"
        autoAck: "no"
        tripDelay: 3
        #Normally just the opposite of trip
        releaseCondition: ""
        priority: warning
```




```