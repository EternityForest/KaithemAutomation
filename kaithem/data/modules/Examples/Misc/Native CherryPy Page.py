## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1622980209179690
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    import cherrypy
    
    class App():
        @cherrypy.expose
        def index(self):
            return "hello world"
            
        @cherrypy.expose
        def hi(self,name):
            return "Hi "+name+"!"
    app=App()
    
    class SubdomainApp():
        @cherrypy.expose
        def index(self):
            return "Subdomain capture example"
            
       
    app2=SubdomainApp()
    
    kaithem.web.controllers[("handler_example",)]=app
    
    #visit /handler_example or /handler_example/hi/<YOURNAMEHERE>
    
    
    # The / indicates the end of a subdomain.  Note that if you don't override this way, all subdomains are exactly the same as the main domain.
    #visit hello.world.localhost:8002/hello
    
    #Note reversed order to match heirarchy
    kaithem.web.controllers[('world','hello','/','hello')]=app2

def eventAction():
    pass
