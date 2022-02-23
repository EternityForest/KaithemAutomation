## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1645141613510257, resource-type: event}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    def nbr():
        return(50, '<a href="/pages/Beholder/ui"><i class="icofont-castle"></i>Beholder</a>')
    kaithem.web.navBarPlugins['Beholder']=nbr

def eventAction():
    pass