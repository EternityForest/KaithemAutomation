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
resource-timestamp: 1571876207940466
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

## Time Expressions

Any event beginning with @ is a time expression. The event will fire as soon as the statement is true.
Things like "@every 10 minutes between 5AM and 6PM" can be used for complex time rules.

## Dynamic lighting channel values

Double click a number of a lighting channel to open the set exact value window. You
can enter a value like "=90*2" and it will be evaluated when the cue is entered, 
and any time a variable changes(pagevars.* variables may not always trigger rerender!)

## The variables universe

The special universe called __variables__ lets you set logic vars directly in the cues. When the cue enters, or a lighting value changes,
a scene variable with the same name as the channel is set to the value.

As with several other features, anything starting with = is evaluated as an expression before setting the variable.

