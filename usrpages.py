#Copyright Daniel Black 2013
#This file is part of Kaithem Automation.

#Kaithem Automation is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, version 3.

#Kaithem Automation is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

#This file handles the display of user-created pages
import kaithem, modules, mako, cherrypy,util,pages
class KaithemPage():
    @cherrypy.expose
   
    def page(self,module,dummy2,page,*args,**kwargs):
        #Permission handling for pages
        if 'require-permissions' in modules.ActiveModules[module][page]:
            for i in modules.ActiveModules[module][page]['require-permissions']:
                pages.require(i)
         
        with modules.modulesLock:  #need to find an alternaive to this lock
            if modules.ActiveModules[module][page]['resource-type'] == 'page':
               
               #Allow a page to specify that it can only be accessed via POST or such
               if "require-method" in modules.ActiveModules[module][page]:
                    if cherrypy.request.method not in modules.ActiveModules[module][page]['require-method']:
                        #Raise a redirect the the wrongmethod error page
                        raise cherrypy.HTTPRedirect('/errors/wrongmethod')
                        
               #This is pretty much the worst perfoming piece of code in the system.
               #Every single request it compiles a new template and renders that, but not before loading two files from
               #Disk. But I don't feel like writing another ten pages of bookkeeping code today. []TODO
               if  'no-navheader' in modules.ActiveModules[module][page]:
                   if modules.ActiveModules[module][page]['no-navheader']:
                       header = util.readfile('pages/pageheader_nonav.html')
                   else:
                       header = util.readfile('pages/pageheader.html')
               else:
                    header = util.readfile('pages/pageheader.html')
                    
               return mako.template.Template(
               header+
               modules.ActiveModules[module][page]['body']+
                util.readfile('pages/pagefooter.html')
               ).render(
               kaithem = kaithem.kaithem,
               request = cherrypy.request,
               )

