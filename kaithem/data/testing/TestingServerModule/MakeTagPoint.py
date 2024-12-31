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

    from kaithem.api.tags import NumericTag

    t = NumericTag("/test_preloaded_module")


def event_action():
    t.value = 123
