## Code outside the data string, and the setup and action blocks is ignored
## If manually editing, you must reload the code. Delete the resource timestamp so kaithem knows it's new
__data__="""
continual: false
enable: true
once: true
priority: interactive
rate-limit: 0.0
resource-timestamp: 1604311447266157
resource-type: event
versions: {}

"""

__trigger__='False'

if __name__=='__setup__':
    #This code runs once when the event loads. It also runs when you save the event during the test compile
    #and may run multiple times when kaithem boots due to dependancy resolution
    __doc__=''
    
    import cherrypy,os
    
    def serve(f):
        return cherrypy.lib.static.serve_file(f,"imange/png","tile.png")
        
    
    class API():
        
        @cherrypy.expose
        def tile(self,z,x,y):
            if os.path.exists(os.path.join(os.path.expanduser("~/.local/share/marble/maps/earth/opentopomap"),z,x,y)):
                 return serve(os.path.join(os.path.expanduser("~/.local/share/marble/maps/earth/opentopomap"),z,x,y))
            if os.path.exists(os.path.join("/home/pi/.local/share/marble/maps/earth/opentopomap",z,x,y)):
                return serve(os.path.exists(os.path.join("/home/pi/share/marble/maps/earth/opentopomap",z,x,y)))
            
            raise RuntimeError("No Tile Found")
    
    api = API()
    kaithem.web.controllers[('maptiles',)]= api

def eventAction():
    pass
