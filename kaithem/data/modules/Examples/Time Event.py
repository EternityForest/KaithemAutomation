# Code outside the data string, setup and action blocks is ignored
# If manually editing, delete resource timestamp and restart kaithem.
__data__ = """
continual: false
enable: true
once: true
priority: interactive
rate_limit: 0.0
resource_label_image: 16x9/prague-astronomical-clock.avif
resource_timestamp: 1699743201983962
resource_type: event

"""

__trigger__ = "!time every hour"

if __name__ == "__setup__":
    # This code runs once when the event loads. It also runs when you save the event during the test compile
    # and may run multiple times when kaithem boots due to dependancy resolution
    __doc__ = ""


def event_action():
    pass
