## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1610570976331421, resource-type: event}

"""

__trigger__='!time every day at midnight Etc/UTC'

if __name__=='__setup__':
    __doc__="This should be scheduled to run at midnight, UTC"

def eventAction():
    pass
