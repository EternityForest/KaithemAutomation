# ChandlerScript

ChandlerScript is a very minimal lisp like language designed for graphical editing.



### Context Objects

To run the code, you create a context object and add bindings to it. Bindings cause actions to be run when an event occurs.

Contexts are sandboxed and should not be able to access anything but some default safe things, and what you give them.

There is a global  interpreter lock that works a lot like JavaScript, bindings run one at a time to completion without any others in the context running at the same time.


### ChandlerScriptContext.event(evt, arg)
Triggers the given event.  This uses an event queue for deadlock-free excecution.

### ChandlerScriptContext.addBindings(b)

Take a list of bindings and add them to the context.
A binding looks like:
['eventname',[['command','arg1'],['command2']]

When events happen commands run till one returns None.

Also immediately runs any 'now' bindings, the 'now' event is special

### ChandlerScriptContext.clearBindings(b)

Clear the bindings. But don't clear variables.

### ChandlerScriptContext.onBindingAdded(self, evt):
    Called when a binding is added that listens to evt. Does nothing, used for subclassing.


### Events

An event is a message that is sent to the a context that triggers any pipelines bound to it. An event has a name, and a value, and may be global or only to one context.

### Actions

A pipeline is just a sequence of commands. When it runs, execution stops
at the first one that does not return a value. This allows you to implement conditions
and filters.

### Command

A command has a command name with a sequence of arguments. Arguments
are considered numbers if they look like numbers, or else they are strings.


#### Spreadsheet style eval
Arguments starting with = are evaluated using simpleeval, which parses basic math expressions.

If you want to force a number to be a string wrap it in an evaluaton like "='90'"



### Variables

Every context has a set of variables. You can set them with the command "set",
which always returns True.

### The _ variable

This always holds the return value of the last command.


