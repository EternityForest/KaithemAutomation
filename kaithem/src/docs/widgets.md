## The Widget System


Kaithem integrates an AJAX library that allows you to create dynamic
widgets within HTML pages that automatically interact with the
corresponding object on the server. You do not need to write any
javascript at all to use Kaithem Widgets. Most Widgets automatically
handle multiple users, such as moving sliders on one device to match a
change on another.

### widget.js

Somewhere in your page before the first widget, you must include this
line:

```html
<script type="text/javascript" src="/static/widget.js"></script>
```

This will include a small JS library that will automatically handle just aboud everything for you.


kaithemapi.subscribe(widgetid, callback) is used to programmatically subscribe in JS.
kaithemapi.sendValue(wid, val) is used to send.  

Note: When subscribing, the server always responds with the current value, even if nothing has changed.

### Widget Objects on the server side.

A widget object represents one widget, and handles AJAX for you
automatically. Each widget type is slightly different, but all widgets
have a render() method. The render method produces HTML suitable for
direct inclusion in a page, as in &lt;%text&gt;

    ${module.myWidget.render()}

The rendered HTML will contain a few functions, the ID of the widget
object that created it, and a piece of code that registers it for
polling.



Widgets may take parameters in their render() function on a widget
specific basis

You must maintain a reference to all widget objects you create to
prevent them from being garbage collected.

Most widget objects will have write(value) and read() functions. For
example, a calling read() on a slider widget would return whatever
slider position the user entered. If there are multiple users, all
sliders rendered from the same object will move in synch.



### kaithem.widget.getConnectionRefForID(id, deleteCallback=None)

Using the connection ID from Widget.attach2, return the actual
websocket object.   This allows you to detect when a a particular session
is closed.

### The Widget() Base Class

All Kaithem widgets inherit from Widget. Widget provides security,
polling handling, and bookkeeping. Widget has the following properties,
which may be overridden, extendd, or removed in derivd classes:

### Widget.render(\*args,\*\*kwargs)

Returns an HTML representation of the widget, including all javascript
needed, and suitable for direct inclusion in HTML code as you would a
div or img. Widgets are usually inline-block elements. Many numeric
widgets will take an optional kewyword argument label and unit.

### Widget.uuid (Always available)

This is a string representation of the Widget's ID. It is automatically
created when initializing Widget.

### Widget.require(permission) (Always Available)

Causes the object to reject AJAX read or write requests from any device
that does not have the permissions. You can apply as many permissions as
you want.

### Widget.requireToWrite(permission) (Always Available)

Causes the object to reject AJAX write requests from any device that
does not have the permissions. You can apply as many permissions as you
want.

### Widget.setPermissions(read,write) (Always Available)

Sets the widget's read and write permissions to the two lists specified.
This is the prefered form when dealing with widgets that may already have permissions
that you want to replace.


### Widget.onRequest(user,uuid) (Always Available)

This function is automatically called when Kaithem needs to access the latest value, such as when
a new subscrber subscribes and needs to immediately know.  JS Widgets can no longer explicitly make requests.

It must return None for unknown/no change or else a
JSON serializable value specific to the widget type. You only need to
know about this function when creating custom widgets. uuid is the
connection ID.

### Widget.onUpdate(user,value,uuid) (Always Available)

This function is automatically called when an authorized client requests
to set a new value. value will be specific to the widget. You only need
to know about this function when creating custom widgets. uuid is the
connection ID.

### Widget.read() (Usually Available)

Returns the current "value" of the widget, an is available for all
readable widgets where the idea of "value" makes sense. Generally just
returns self.value unless overridden.

### Widget.write(value) (Usually Available)

sets the current "value" of the widget, an is available for all writable
widgets where the idea of "value" makes sense. Unless overridded, this
will set self.value, invoke any callback set for the widget(with user
\_\_SERVER\_\_), and send the value to all subscribed clients.

This should not be used from within the callback or overridden message
handler due to the possibility of creating loops. To send a value to all
clients without invoking any local callbacks or setting the local value,
use send.

### Widget.send(value)

Send value to all subscribed clients.

### Widget.sendTo(value,connectionID)

Send only to one client by it's connection ID

### <span id="widgetattach"></span>Widget.attach(f)

Set a callback that fires when new data comes in from the widget. It
will fire when write() is called or when the client sends new data The
function must take two values, user, and data. User is the username of
the user that loaded the page that sent the data the widget, and data is
it's new value. user wil be set to \_\_SERVER\_\_ if write() is called.

### Widget.attach2(f)

Same as above, but takes a 3 parameter callback, user,data, and
connection ID. allows distinguishing different connections by the same
user.

You should not call self.write from within the callback to avoid an
infinite loop, although you can call write on other widgets without
issue. If you wish to send replies from a callback, use self.send()
instead which does not set self.value or trigger the callback.
