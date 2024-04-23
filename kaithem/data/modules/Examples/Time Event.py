## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__ = """
continual: false
enable: true
once: true
priority: interactive
rate_limit: 0.0
resource-timestamp: 1699743201983962
resource-type: event

"""

__trigger__ = "!time every hour"

if __name__ == "__setup__":
    # This code runs once when the event loads. It also runs when you save the event during the test compile
    # and may run multiple times when kaithem boots due to dependancy resolution
    __doc__ = ""


def eventAction():
    pass
