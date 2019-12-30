## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
{continual: false, enable: true, once: true, priority: interactive, rate-limit: 0.0,
  resource-timestamp: 1568112911280269, resource-type: event}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__='Create a page directly in code as you would in a traditional cherrypy app. Go to /hello to test this.'
    
    
    import cherrypy
    
    class HelloWorld(object):
        @cherrypy.expose
        def index(self):
            return "Hello World!"
    
    hello = HelloWorld()
    kaithem.web.controllers[None]= hello

def eventAction():
    pass
