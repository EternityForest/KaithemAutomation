# ChandlerScript

ChandlerScript is a very minimal lisp like language designed for graphical editing.


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


