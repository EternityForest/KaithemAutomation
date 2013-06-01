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

#File for keeping track of and editing kaithem modules(not python modules)

import auth,cherrypy,pages,urllib,directories,os,json,util,newevt,shutil,sys
import kaithem
import threading

if sys.version_info < (3,0):
    from urllib import quote,unquote
else:
    from urllib.parse import quote,unquote

#this lock protects the activemodules thing
modulesLock = threading.RLock()

#Lets just store the entire list of modules as a huge dict for now at least
ActiveModules = {}

#Define a place to keep the module private scope obects.
#Every module has a object of class object that is used so user code can share state between resources in
#a module
scopes ={}




#saveall and loadall are the oes outside code shold use to save and load the state of what modules are loaded
def saveAll():
    saveModules(directories.moduledir)
    
def loadAll():
    loadModules(directories.moduledir)
    auth.importPermissionsFromModules()
    
def saveModules(where):
    with modulesLock:
        for i in ActiveModules:
            #Iterate over all of the resources in a module and save them as json files
            #under the URL quoted module name for the filename.
            for resource in ActiveModules[i]:
                try:
                    #Make sure there is a directory at where/module/
                    util.ensure_dir(os.path.join(where,quote(i,""),quote(resource,"")))
                    #Open a file at /where/module/resource
                    f = open(os.path.join(where,quote(i,""),quote(resource,"")),"w")
                    #Make a json file there and prettyprint it
                    json.dump(ActiveModules[i][resource],f,sort_keys=True,indent=4, separators=(',', ': '))
                finally:
                    f.close()

            #Now we iterate over the existing resource files in the filesystem and delete those that correspond to
            #modules that have been deleted in the ActiveModules workspace thing.
            for i in get_immediate_subdirectories(os.path.join(where,quote(i,""))):
                if urllib.unquote(i) not in ActiveModules:  
                    os.remove(os.path.join(where,quote(i,""),i))

        for i in get_immediate_subdirectories(where):
            #Look in the modules directory, and if the module folder is not in ActiveModules\
            #We assume the user deleted the module so we should delete the save file for it.
            #Note that we URL quote file names for the module filenames and foldernames.
            if urllib.unquote(i) not in ActiveModules:
                shutil.rmtree(os.path.join(where,i))

#Get the names of all subdirectories in a folder but not full paths
def get_immediate_subdirectories(folder):
    return [name for name in os.listdir(folder)
            if os.path.isdir(os.path.join(folder, name))]

#Get a list of all filenames but not the full paths
def get_files(folder):
    return [name for name in os.listdir(folder)
            if not os.path.isdir(os.path.join(folder, name))]

#Load all modules in the given folder to RAM
def loadModules(modulesdir):
    for i in get_immediate_subdirectories(modulesdir):
        loadModule(i,modulesdir)
    newevt.getEventsFromModules()

#Load a single module. Used by loadModules
def loadModule(moduledir,path_to_module_folder):
    with modulesLock:
        #Make an empty dict to hold the module resources
        module = {} 
        #Iterate over all resource files and load them
        for i in get_files(os.path.join(path_to_module_folder,moduledir)):
            try:
                f = open(os.path.join(path_to_module_folder,moduledir,i))
                #Load the resource and add it to the dict. Resouce names are urlencodes in filenames.
                module[unquote(i)] = json.load(f)
            finally:
                f.close()
        
        name = unquote(moduledir)
        ActiveModules[name] = module
        #Create the scopes dict thing for that module
        scopes[name] = {}


#The clas defining the interface to allow the user to perform generic create/delete/upload functionality.
class WebInterface():
    @cherrypy.expose
    def index(self):
        #Require permissions and render page. A lotta that in this file.
        pages.require("/admin/modules.view")
        return pages.get_template("modules/index.html").render(ActiveModules = ActiveModules)

    @cherrypy.expose       
    def newmodule(self):
        pages.require("/admin/modules.edit")
        return pages.get_template("modules/new.html").render()
        
    #CRUD screen to delete a module
    @cherrypy.expose
    def deletemodule(self):
        pages.require("/admin/modules.edit")
        return pages.get_template("modules/delete.html").render()

    #POST target for CRUD screen for deleting module
    @cherrypy.expose
    def deletemoduletarget(self,**kwargs):
        pages.require("/admin/modules.edit")
        with modulesLock:
           ActiveModules.pop(kwargs['name'])
        #Get rid of any lingering cached events
        newevt.removeModuleEvents(kwargs['name'])
        #Get rid of any permissions defined in the modules.
        auth.importPermissionsFromModules()
        raise cherrypy.HTTPRedirect("/modules")
        
    @cherrypy.expose
    def newmoduletarget(self,**kwargs):
        global scopes
        pages.require("/admin/modules.edit")
        #If there is no module by that name, create a blank template and the scope obj
        with modulesLock:
            if kwargs['name'] not in ActiveModules:
                ActiveModules[kwargs['name']] = {"__description":
                {"resource-type":"module-description",
                "text":"Module info here"}}
                #Create the scope that code in the module will run in
                scopes[kwargs['name']] = {}
                #Go directly to the newly created module
                raise cherrypy.HTTPRedirect("/modules/module/"+util.url(kwargs['name']))
            else:
                return pages.get_template("error.html").render(info = " A module already exists by that name,")
            
    @cherrypy.expose
    #This function handles HTTP requests of or relating to one specific already existing module.
    #The URLs that this function handles are of the form /modules/module/<modulename>[something?]     
    def module(self,module,*path,**kwargs):
        #If we are not performing an action on a module just going to its page
        if not path:
            pages.require("/admin/modules.view")
            return pages.get_template("modules/module.html").render(module = ActiveModules[module],name = module)
            
        else:
            #This gets the interface to add a page
            if path[0] == 'addresource':
                #path[1] tells what type of resource is being created and addResourceDispatcher returns the appropriate crud screen
                return addResourceDispatcher(module,path[1])

            #This case handles the POST request from the new resource target
            if path[0] == 'addresourcetarget':
                return addResourceTarget(module,path[1],kwargs['name'],kwargs)

            #This case shows the information and editing page for one resource
            if path[0] == 'resource':
                return resourceEditPage(module,path[1])

            #This goes to a dispatcher that takes into account the type of resource and updates everything about the resource.
            if path[0] == 'updateresource':
                return resourceUpdateTarget(module,path[1],kwargs)

            #This returns a page to delete any resource by name
            if path[0] == 'deleteresource':
                pages.require("/admin/modules.edit")
                return pages.get_template("modules/deleteresource.html").render(module=module)

            #This handles the POST request to actually do the deletion
            if path[0] == 'deleteresourcetarget':
                pages.require("/admin/modules.edit")
                with modulesLock:
                   r = ActiveModules[module].pop(kwargs['name'])
                   
                #Annoying bookkeeping crap to get rid of the cached crap
                if r['resource-type'] == 'event':
                    newevt.removeOneEvent(kwargs['name'])
                    
                if r['resource-type'] == 'permission':
                    auth.importPermissionsFromModules() #sync auth's list of permissions
                    
                raise cherrypy.HTTPRedirect('/modules')

            #This is the target used to change the name and description(basic info) of a module  
            if path[0] == 'update':
                pages.require("/admin/modules.edit")
                with modulesLock:
                    ActiveModules[kwargs['name']] = ActiveModules.pop(module)
                    ActiveModules[module]['__description']['text'] = kwargs['description']
                raise cherrypy.HTTPRedirect('/modules/module/'+util.url(kwargs['name']))

#Return a CRUD screen to create a new resource taking into the type of resource the user wants to create               
def addResourceDispatcher(module,type):
    pages.require("/admin/modules.edit")
    
    #Return a crud to add a new permission
    if type == 'permission':
        return pages.get_template("modules/permissions/new.html").render(module=module)

    #return a crud to add a new event
    if type == 'event':
        return pages.get_template("modules/events/new.html").render(module=module)

    #return a crud to add a new event
    if type == 'page':
        return pages.get_template("modules/pages/new.html").render(module=module)

#The target for the POST from the CRUD to actually create the new resource
#Basically it takes a module, a new resourc name, and a type, and creates a template resource
def addResourceTarget(module,type,name,kwargs):
    pages.require("/admin/modules.edit")
    
    #Create a permission
    if type == 'permission':
        with modulesLock:
            if kwargs['name'] in ActiveModules[module]:
                raise cherrypy.HTTPRedirect("/errors/alreadyexists")
            else:   
                ActiveModules[module] [kwargs['name']]= {"resource-type":"permission","description":kwargs['description']}
                #has its own lock
                auth.importPermissionsFromModules() #sync auth's list of permissions 
                raise cherrypy.HTTPRedirect("/modules/module/" +util.url(module)+ '/resource/' + util.url(name) )
        
    if type == 'event':
        with modulesLock:
           if kwargs['name'] not in ActiveModules[module]:
                ActiveModules[module] [kwargs['name']]= {"resource-type":"event","trigger":"False","action":"pass",
                "once":True}
                #newevt maintains a cache of precompiled events that must be kept in sync with
                #the modules
                newevt.updateOneEvent(kwargs['name'],module)
                raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module)+'/resource/'+util.url(name))
           else:
                raise cherrypy.HTTPRedirect("/errors/alreadyexists")

    if type == 'page':
        with modulesLock:
            if kwargs['name'] not in ActiveModules[module]:
                ActiveModules[module][kwargs['name']]= {"resource-type":"page","body":"Content here"}
                #newevt maintains a cache of precompiled events that must be kept in sync with
                #the modules
                raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module)+'/resource/'+util.url(name))
            else:
                raise cherrypy.HTTPRedirect("/errors/alreadyexists")  
                      
#show a edit page for a resource. No side effect here so it only requires the view permission
def resourceEditPage(module,resource):
    pages.require("/admin/modules.view")
    with modulesLock:
        if ActiveModules[module][resource]['resource-type'] == 'permission':
            return permissionEditPage(module, resource)

        if ActiveModules[module][resource]['resource-type'] == 'event':
            return pages.get_template("/modules/events/event.html").render(module =module,name =resource,event 
            =ActiveModules[module][resource])

        if ActiveModules[module][resource]['resource-type'] == 'page':
            return pages.get_template("/modules/pages/page.html").render(module=module,name=resource,
            page=ActiveModules[module][resource])

def permissionEditPage(module,resource):
    pages.require("/admin/modules.view")
    return pages.get_template("modules/permissions/permission.html").render(module = module, 
    permission = resource, description = ActiveModules[module][resource]['description'])

#The actual POST target to modify a resource. Context dependant based on resource type.
def resourceUpdateTarget(module,resource,kwargs):
    pages.require("/admin/modules.edit")
    t = ActiveModules[module][resource]['resource-type']
    
    if t == 'permission': 
        with modulesLock:
            ActiveModules[module][resource]['description'] = kwargs['description']
        #has its own lock
        auth.importPermissionsFromModules() #sync auth's list of permissions 

    if t == 'event':
        with modulesLock:
            e = newevt.Event(kwargs['trigger'],kwargs['action'],{})#Test compile, throw error on fail.
            ActiveModules[module][resource]['trigger'] = kwargs['trigger']
            ActiveModules[module][resource]['action'] = kwargs['action']
            #I really need to do something about this possibly brittle bookkeeping system
            #But anyway, when the active modules thing changes we must update the newevt cache thing.
            newevt.updateOneEvent(resource,module)

    if t == 'page':
        with modulesLock:
            ActiveModules[module][resource]['body'] = kwargs['body']
    raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module)+'/resource/'+util.url(resource))
    

        
class KaithemEvent(dict):
    pass



