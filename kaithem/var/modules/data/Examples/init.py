## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1646963650245604
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #You can also use events just for setting things up, like this!
    kaithem.globals.count = 0
    p =0

def eventAction():
    p+=1
    x ={}
