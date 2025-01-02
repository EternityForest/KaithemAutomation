# Code outside the data string, setup and action blocks is ignored
# If manually editing, delete resource timestamp and restart kaithem.
__data__ = """
continual: false
enable: true
once: true
priority: interactive
rate_limit: 0.0
resource_timestamp: 1735680378326015
resource_type: event

"""

__trigger__ = "True"

if __name__ == "__setup__":
    # This code runs once when the event loads.
    __doc__ = ""

    import threading
    import time

    def f():
        while 1:
            time.sleep(1)

    t = threading.Thread(target=f, daemon=True, name="stoppable_thread")
    t.start()


def event_action():
    pass
