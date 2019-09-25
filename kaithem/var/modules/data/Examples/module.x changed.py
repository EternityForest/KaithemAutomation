## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code through the web UI
__data__="""
continual: false
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1566264981078414
resource-type: event
versions: {}

"""

__trigger__='!onchange module.x'

if __name__=='__setup__':
    module.x = 0

def eventAction():
    #This is like a useless machine. Whenever x changes, it sets it back to 0!
    module.x = 0
