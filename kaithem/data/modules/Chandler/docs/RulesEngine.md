---
allow-origins: ['*']
allow-xss: false
auto-reload: false
auto-reload-interval: 5.0
dont-show-in-index: false
mimetype: text/html
no-header: false
no-navheader: true
require-method: [GET, POST]
require-permissions: []
resource-timestamp: 1576476101108743
resource-type: page
template-engine: markdown

---
Chandler Rules Engine
=====================

## Intro

Each row in the rules editor is a left-to-right sequence that starts with a trigger and stops at the end, or when a command does not return anything.

The block inspector will tell you what commands return. Generally they will answer "True" and continue the action, unless they are Questions,
in which case they will answer with None(stopping the action) if the answer to the question is No.

Any parameter for a block that starts with = is considered a math expression that may use variables,boolean logic, and text operations (Similar to spreadsheets).

Some blocks may return an interesting number,boolean, or text value. You may access it expressions in the next block as the variable _ just like many scientific calculators.

## Available functions in expressions

### sin(x)
### cos(x)
### min(a,b)
### max(a,b)
### random()
Returns random number from 0 to 1
### log(a,[b])
### log10(a)

### millis()
Return a monotonic milliseconds counter. It will not go backwards till the system
reboots.

### tagValue(tagName)
Returns the value of the tagpoint with that name, or 0 if the tag does not exist.
Any tagpoint beginning with /chandler/ is allowed.

Accessing a tag will add it to the list of tags being "watched" by that tag, until
the next cue transition.

The variable $tag:NAME will be updated to match the value, so long as the tag is watched.
Also, all =expression events that use the tag(Currently just all of them) will be re-polled whenever a watched tag changes.

### stringTagValue(tagName)
Same as tagValue, for string tagpoints "" if the tag does not exist.


## Time Expressions

Any event beginning with @ is a time expression. The event will fire as soon as the statement is true.
Things like "@every 10 minutes between 5AM and 6PM" can be used for complex time rules.

## Polled expressions

Amy event beginning with = is a polled expression. It will be polled every few seconds at minimum,
but will also be polled:
* When a relevant tag point (One that is mentioned in any event name) changes.
* Immediately on entering the cue
* When updating it's scripting
* When a relevant variable(One that is mentioned in any event name) changes

It will fire whenever True.

Note that these are level-triggered, not edge triggered. The event should fire when it becomes true,
but may also fire at any time again while it is true.

The intent is to use them to trigger cue transitions as soon as an expression involving tags becomes True

## MQTT Message Expressions

Any event like "$mqtt:topic/name" is an MQTT expression. If the scene is connected to an MQTT server, it fires when
someone publishes a message on that topic. Wildcards are not currently not supported.

## Dynamic lighting channel values

Double click a number of a lighting channel to open the set exact value window. You
can enter a value like "=90*2" and it will be evaluated when the cue is entered, 
and any time a variable changes(pagevars.* variables may not always trigger rerender!)

## The variables universe

The special universe called __variables__ lets you set logic vars directly in the cues. When the cue enters, or a lighting value changes,
a scene variable with the same name as the channel is set to the value.

As with several other features, anything starting with = is evaluated as an expression before setting the variable.


