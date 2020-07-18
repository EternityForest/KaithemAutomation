# Pi Keypad


### dev.subscribe(f)

f(key) will be called for every keypad.  This is actually a wrapper for a message bus subscription, so it will carry over if
you change the settings in the device, or even delete and recreate it, but uses a weakref, so you must keep a reference to f.

### dev.unsubscribe(f)
Unsubscribe f from keypresses.

