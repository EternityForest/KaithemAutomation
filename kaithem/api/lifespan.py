from scullery import messagebus

_shutdown_handler_refs = []

# True if the system is shutting down
shutdown = False


def at_shutdown(f):
    """Register a function to be called when the system shuts down,
    before atexit would trigger"""

    def f2(*a):
        f()

    _shutdown_handler_refs.append(f2)
    messagebus.subscribe("/system/shutdown", f2)


def _state(*a):
    global shutdown
    shutdown = True


at_shutdown(_state)
