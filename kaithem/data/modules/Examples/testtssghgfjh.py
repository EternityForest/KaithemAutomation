## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code through the web UI
__data__="""
{enable: true, once: true, resource-timestamp: 1567587618257949, resource-type: event}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''

def eventAction():
    pass
