# kaithem.api.lifespan

## Attributes

| [`is_shutting_down`](#kaithem.api.lifespan.is_shutting_down)   |    |
|----------------------------------------------------------------|----|

## Functions

| [`shutdown_now`](#kaithem.api.lifespan.shutdown_now)()   | Shut down the system now                                     |
|----------------------------------------------------------|--------------------------------------------------------------|
| [`at_shutdown`](#kaithem.api.lifespan.at_shutdown)(f)    | Register a function to be called when the system shuts down, |

## Module Contents

### kaithem.api.lifespan.is_shutting_down *: bool* *= False*

### kaithem.api.lifespan.shutdown_now()

Shut down the system now

### kaithem.api.lifespan.at_shutdown(f)

Register a function to be called when the system shuts down,
before atexit would trigger
