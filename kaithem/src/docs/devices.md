# Kaithem Devices

Kaithem provides an abstraction called a Device that covers several kinds of device.


## Creating through the GUI

Previously you could create a device in a global devices list.  Now devicesmust be stored in modules.

## Device names

Devices have their own namespace separate from anything else.  Devices can be saved to
any filename in a module, independently of the name that appears in the tag points and devices list.

By default, kaithem will try to put config for any subdevices in DEVICE_RESOURCE.d/

If a device needs a config folder, it will be at DEVICE_RESOURCE.config.d/

### On-disk location

Note that due to the way things are saved, the actual on-disk files are under  \_\_filedata\_\_/ in the module folder.  Kaithem stores arbitrary files in modules separately from it's internal
resource metadata.

## API

All devices appear in the kaithem.devices[] space.

All Tagpoints the device exposes appear in the tags list under  /devices/<DEVNAME>/<TAGNAME>.


## Dependency Resolution

The system tries to create all devices before any modules are loaded.

Devices with no driver are created as "Unsuported" devices.

Attempting to access a device of the "unsupported" type via kaithem.devices will raise a RuntimeError, although they do show up in the management page.

kaithem.devices is iterable, but does not include anything currently unsupported.


### Device Objects

#### dev.alerts(DEPRECATED, USE TAGPOINTS and set_alarm)

Dict of Alert objects the device defines

#### dev.readme
Should be a local filename of a README file for the device type.

use `readme = os.path.join(os.path.dirname(__file__),"README.md")' to load the file from
the same dir as the script.


#### dev.\_\_init\_\_(name, data)
Data will be the same kwargs from the HTTP POST used to create or delete.

Keys starting with temp. do not become part of persistent config.

Subclasses should never raise errors, and should instead just act as "dummy" devices,
to allow the user to edit and correct any problems.

handle_error should be used to inform the user of issues.

#### dev.print(msg)

Print a string to the device's management page. Old messages are automatically cleared.

#### dev.config

The dict containing persistant config data. When subclassing, do not assume this contains any particular key.  At minimum, it will contain the name and type field,
but a newly created device may be almost totally unconfigurable.

To avoid conflicts with core attributes, you can prefix keys with "device.". Such keys are reserved for device spefic attributes.


As everything is configured from HTML settting pages or config files, you must assume that any key could be a string, and convert appropriately.

#### dev.set_data_key(key,val)

This allows setting a persistant config key. Any value will be converted to a string!


#### dev.tagpoints

This a dict of tag point objects indexed by arbitrary names like "voltage" or "foo".

It should generally be replaced atomically, not mutated after object creation if possible.

Items in this dict will create UI with links to the management pages for the points.

Tag points should usually be named relative to the device, like "/devices/NAME/property".


#### dev.handle_error(string)

Logs an error as a string. Old errors are automatically flushed to make room for new, and all recent errors will show on the device page.


#### dev.close()
Clean up the device. Must not fail.

## Adding new device types

See the iot_devices library.  Kaithem's old builtin device system is not recommended for new implementations