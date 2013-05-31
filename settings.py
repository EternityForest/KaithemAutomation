import pages, cherrypy, util

class Settings():
    @cherrypy.expose 
    def index(self):
        pages.require("/admin/settings.view")
        return pages.get_template("settings/index.html").render()
        
    @cherrypy.expose    
    def save(self):
        pages.require("/admin/settings.edit")
        return pages.get_template("settings/save.html").render()
        
    @cherrypy.expose    
    def savetarget(self):
        pages.require("/admin/settings.edit")
        util.SaveAllState()
        raise cherrypy.HTTPRedirect('/settings')
