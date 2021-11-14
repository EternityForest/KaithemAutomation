# Kaithem Devices

Kaithem provides an abstraction called a Device that covers several kinds of device.ted.

## API

All devices appear in the kaithem.devices[] space. 

All Tagpoints the device exposes appear in the tags list under  /devices/<DEVNAME>/<TAGNAME>. 


## Dependency Resolution

The system tries to create all devices before any modules are loaded.

Devices with no driver are created as "Unsuported" devices.  When a driver is later added by a module, the device is automatically recreated as the correct device type.

Attempting to access a device of the "unsupported" type via kaithem.devices will raise a RuntimeError, although they do show up in the management page.

kaithem.devices is iterable, but does not include anything currently unsupported.


This means that the usual "retry on errors" based dependancy resolution will work.

Normally you don't need to think about this at all, but an example dependancy resolution sequence is:

* all devices are created except foo, which is unsupported
* modules load
* Event bar fails because it needs foo. It goes in the retry queue
* Event MyDriver loads, and gives foo it's driver.  Foo is recreated.
* Event bar eventually loads successfully.

### Device Objects

#### dev.alerts(DEPRECATED, USE TAGPOINTS and setAlarm)

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

handleError should be used to inform the user of issues.

#### dev.print(msg)

Print a string to the device's management page. Old messages are automatically cleared.

#### dev.data

The dict containing persistant config data. When subclassing, do not assume this contains any particular key.  At minimum, it will contain the name and type field,
but a newly created device may be almost totally unconfigurable.

To avoid conflicts with core attributes, you can prefix keys with "device.". Such keys are reserved for device spefic attributes.


As everything is configured from HTML settting pages or config files, you must assume that any key could be a string, and convert appropriately.

#### dev.setDataKey(key,val)

This allows setting a persistant config key. Any value will be converted to a string!


#### dev.tagpoints

This a dict of tag point objects indexed by arbitrary names like "voltage" or "foo".

It should generally be replaced atomically, not mutated after object creation if possible.

Items in this dict will create UI with links to the management pages for the points.

Tag points should usually be named relative to the device, like "/devices/NAME/property".


#### dev.handleError(string)

Logs an error as a string. Old errors are automatically flushed to make room for new, and all recent errors will show on the device page.


#### dev.close()
Clean up the device. Must not fail.

## Adding new device types


Devices are defined by a dict of configuration data and a name. At
minimium, the device config data will have a "type" field that
determines what class is used to construct the device object.


Every device has a set of "descriptors", which are objects indexed by
string keys that describe exactly what the device is capable of. String
keys can be anything, but domain name based names help avoid collisions.

To create your own device types, all you have to do is subclass
devices.Device(Also available at kaithem.devices.Device), and add your subclass to the weak dict
devices.deviceTypes(Also available as kaithem.devices.deviceTypes)

deviceTypes is a weakref dict, you must keep a reference to your class.

Java-style "com.foo.devicetype" names are suggested to avoid collisions.

You cannot use special chars in device names, except for parenthesis.

Anything within a matched set of parens will be excluded from the name.


You cannot have two drivers for the same device name.



### VARDIR/devicedrivers

To create a device driver through vardir, all you have to do is create a subfolder within devicedrivers, and put a file named DEVICETYPE.py in that folder.

This file must define a class inheriting from device(Which is a global var in this context), named DEVICETYPE.  The global "kaithem" object is also available here.

DEVICETYPE.edit.html and DEVICETYPE.create.html will be used as Mako templates
to allow custom configuration.


Multiple different drivers may be present in a subfolder. The intent is that driver collections should be easy to distribute via github repositories and clones.

#### ExampleDeviceType.py
```python3
class ExampleDeviceType(Device):
    def hello(self):
        print("Hello World!")
        
    def getColor(self):
        return self.data.get('device.color','Clear')
```
#### ExampleDeviceType.edit.html
Note: This is not a complete page, it gets embedded in a larger page automatically,
you don't need to worry about form targets and such.

The device is the var obj, the name is name, and it's data is data.

```
Choose a Color: <input name="color" value="${data.get('color','Colorless')|h}">
```


#### README.md
Device driver collections should use a README.md file for any documentation they may need to provide.

#### Dependancy

Python code has access to a dict deviceTypes, containing all device types loaded
so far.   You can inherit from one of these, as long as you are careful about load order.

Drivers from the vardir always load after plugins and after builtin base device types.

Drivers in the devicedrivers folder are loaded in order of the length of the name,
*before* stripping the part within parens.

Therefore, foo.bar will always load after foo, and bar(foo) will always load after foo. Dependancies will be correct so long as *every name contains all the names of device types it depends on*.

This allows traditional class style inheritance, just as `KX3209(GenericMultimeter).py`, if inhereting from a device type called GenericMultimeter.


Note that this is entirely done based on length, there is no fancy resolution happening.


### HTML Config

Device configuration pages are structured as HTML forms, and the field
names map directly to data keys in the configuration. Every device has a
getManagementForm() method that returns raw HTML that gets inserted into
that form.

getCreateForm() is similar, but must be a static method. It is used
for creating new devices.

All keywords that get passed from management or create forms
are saved in the "device data" dict. These are what actually gets saved
to files.

The exception is names starting with "temp.", these are passed to the constructor, but they are not saved or loaded from disk.

### Keyword naming

Configuration keys are hierarchially namespaced. To be completely safe,
use the "device." namespace for device specific stuff.

Anything beginning with temp. is passed to the device but not saved or loaded.

#### Reserved Keys

##### name
Always present, you do not need an input for this

##### type
Always present, you do not need an input for this, one is already in the page

##### subclass
Always present, you do not need an input for this, one is already in the page.
It is used to let you subclass the device right from config, and instantiate the subclass instead of the actual device itself.



#### Alerts
Config keys of the form alerts.NAME.priority are used to set the
priority of the corresponding alert in the device.alerts dict, allowing
easy configurable alerting. The config page already has this section,
you do not need to include it in your management form.

The alerts list is autogenerated. To apply configured priorities, call
device.setAlertPriorities()

It is suggested that you use the standard tagpoint-based configurable alarms instead for most things.

## Configuring

You configure devices through the devices page.


#### dev.setDataKey(key,val)
Sets a persistant and savable key for this device in it's data.

#### dev.data
The device data, the stuff passed in over kwargs.

