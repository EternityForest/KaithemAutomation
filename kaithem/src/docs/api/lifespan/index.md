# kaithem.api.lifespan

## Attributes

| [`_shutdown_handler_refs`](#kaithem.api.lifespan._shutdown_handler_refs)   |    |
|----------------------------------------------------------------------------|----|
| [`is_shutting_down`](#kaithem.api.lifespan.is_shutting_down)               |    |

## Functions

| [`shutdown_now`](#kaithem.api.lifespan.shutdown_now)()   | Shut down the system now                                     |
|----------------------------------------------------------|--------------------------------------------------------------|
| [`at_shutdown`](#kaithem.api.lifespan.at_shutdown)(f)    | Register a function to be called when the system shuts down, |
| [`_state`](#kaithem.api.lifespan._state)(\*a)            |                                                              |

## Module Contents

### kaithem.api.lifespan.\_shutdown_handler_refs *= []*

### kaithem.api.lifespan.is_shutting_down *: bool* *= False*

### kaithem.api.lifespan.shutdown_now()

Shut down the system now

### kaithem.api.lifespan.at_shutdown(f)

Register a function to be called when the system shuts down,
before atexit would trigger

### kaithem.api.lifespan.\_state(\*a)
