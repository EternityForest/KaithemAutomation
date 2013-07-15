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
import kaithemobj, modules, mako, cherrypy,util,pages,threading,directories,os
import time
from config import config

errors = {}
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

class CompiledPage():
    def __init__(self, resource):
        
        template = resource['body']
        self.errors = []
        #For compatibility with older versions, we provide defaults
        #In case some attributes are missing
        if 'require-permissions' in resource:
             self.permissions = resource["require-permissions"]
        else:
            self.permissions = []
            
        if 'require-method' in resource:
            self.methods = resource['require-method']
        else:
            self.methods = ['POST','GET']
        
        #Yes, I know this logic is ugly.
        if 'no-navheader' in resource:
            if resource['no-navheader']:
                header = util.readfile(os.path.join(directories.htmldir,'pageheader_nonav.html'))
            else:
                header = util.readfile(os.path.join(directories.htmldir,'pageheader.html'))
        else:
            header = util.readfile(os.path.join(directories.htmldir,'pageheader.html'))
            
        if 'no-header' in resource:
            if resource['no-header']:
                header = ""
        
        footer = util.readfile(os.path.join(directories.htmldir,'pagefooter.html'))
        
        templatesource = header + template + footer
        self.template = mako.template.Template(templatesource)
            
            
def getPageErrors(module,resource):
    return _Pages[module][resource].errors


_Pages = {}
_page_list_lock = threading.Lock()

#Delete a event from the cache by module and resource
def removeOnePage(module,resource):
    #Look up the eb
    with _page_list_lock:
        if module in _Pages:
            if resource in _Pages[module]:
                    del _Pages[module][resource]
                    
#Delete all __events in a module from the cache
def removeModulePages(module):
    #There might not be any pages, so we use the if
    if module in _Pages:
        del _Pages[module]

#This piece of code will update the actual event object based on the event resource definition in the module
#Also can add a new event
def updateOnePage(resource,module):

    #This is one of those places that uses two different locks
    with modules.modulesLock:
        if module not in _Pages:
            _Pages[module]={}
            
        #Get the event resource in question
        j = modules.ActiveModules[module][resource]
        _Pages[module][resource] = CompiledPage(j)
        

#look in the modules and compile all the event code
def getPagesFromModules():
    global _Pages
    with modules.modulesLock:
        with _page_list_lock:
            #Set __events to an empty list we can build on
            _Pages = {}
            for i in modules.ActiveModules.copy():
                #For each loaded and active module, we make a subdict in _Pages
                _Pages[i] = {} # make an empty place or __events in this module
                #now we loop over all the resources o the module to see which ones are __events 
                for m in modules.ActiveModules[i].copy():
                    j=modules.ActiveModules[i][m]
                    if j['resource-type']=='page':
                        _Pages[i][m] = CompiledPage(j)

class KaithemPage():
    
    #Method encapsulating one request to a user-defined page
    @cherrypy.expose
    def page(self,module,dummy2,page,*args,**kwargs):
        global _page_list_lock
        with _page_list_lock:
            page = _Pages[module][page]
            page.lastaccessed = time.time()
            #Check user permissions
            for i in page.permissions:
                pages.require(i)
            
            #Check HTTP Method
            if cherrypy.request.method not in page.methods:
                #Raise a redirect the the wrongmethod error page
                raise cherrypy.HTTPRedirect('/errors/wrongmethod')
            try:
                return page.template.render(
                   kaithem = kaithemobj.kaithem,
                   request = cherrypy.request,
                   module = modules.scopes[module]
                   )
            except Exception as e:
                #When an error happens, log it and save the time
                #Note that we are logging to the compiled event object
                page.errors.append([time.strftime(config['time-format']),e])
                #Keep oly the most recent 25 errors
                page.errors = page.errors[-(config['errors-to-keep']):]
                raise (e)