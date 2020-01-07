## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1578386048937657
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    module.genericFixtureClasses={
        "7ch DGBR": [["dim","intensity"],["green","green"],["blue","blue"],["red","red"],["unused1","unused"],["unused2","unused"],["unused3","unused"],["unused4","unused"]],
        "7ch DBGR": [["dim","intensity"],["blue","blue"],["green","green"],["red","red"],["unused1","unused"],["unused2","unused"],["unused3","unused"],["unused4","unused"]],
        "7ch DRGB": [["dim","intensity"],["red","red"],["green","green"],["blue","blue"],["unused1","unused"],["unused2","unused"],["unused3","unused"],["unused4","unused"]],
    }

def eventAction():
    pass
