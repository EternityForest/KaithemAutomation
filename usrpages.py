#This file handles the display of user-created pages
import kaithem, modules, mako, cherrypy
class KaithemPage():
    @cherrypy.expose
   
    def page(self,module,dummy2,page,*args,**kwargs):
        with modules.modulesLock:  #need to find an alternaive to this lock
            if modules.ActiveModules[module][page]['resource-type'] == 'page':
               
               #Allow a page to specify that it can only be accessed via POST or such
               if "require-method" in modules.ActiveModules[module][page]:
                    if cherrypy.request.method not in modules.ActiveModules[module][page]['require-method']:
                        #Raise a redirect the the wrongmethod error page
                        raise cherrypy.HTTPRedirect('/errors/wrongmethod')
                        
               return mako.template.Template(modules.ActiveModules[module][page]['body']).render(
               kaithem = kaithem.kaithem,
               request = cherrypy.request,
               )

