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

import auth,cherrypy,pages,urllib,directories,os,json,util,newevt,shutil,sys,time
import kaithemobj
import threading
import usrpages
import messagebus

#2.x vs 3.x once again have renamed stuff
if sys.version_info < (3,0):
   from StringIO import StringIO
else:
    from io import BytesIO as StringIO
    
import zipfile

from util import url,unurl


#this lock protects the activemodules thing
modulesLock = threading.RLock()

#Lets just store the entire list of modules as a huge dict for now at least
ActiveModules = {}

#Define a place to keep the module private scope obects.
#Every module has a object of class object that is used so user code can share state between resources in
#a module
scopes ={}

class obj(object):
    pass




#saveall and loadall are the ones outside code shold use to save and load the state of what modules are loaded
def saveAll():
    #This dumps the contents of the active modules in ram to a subfolder of the moduledir named after the current unix time"""
    saveModules(os.path.join(directories.moduledir,str(time.time()) ))
    #We only want 1 backup(for now at least) so clean up old ones.  
    util.deleteAllButHighestNumberedNDirectories(directories.moduledir,2)
    
def loadAll():
    for i in range(0,15):
        #Gets the highest numbered of all directories that are named after floating point values(i.e. most recent timestamp)
        name = util.getHighestNumberedTimeDirectory(directories.moduledir)
        possibledir = os.path.join(directories.moduledir,name)
        
        #__COMPLETE__ is a special file we write to the dump directory to show it as valid
        if '''__COMPLETE__''' in util.get_files(possibledir):
            loadModules(possibledir)
            auth.importPermissionsFromModules()
            break #We sucessfully found the latest good ActiveModules dump! so we break the loop
        else:
            #If there was no flag indicating that this was an actual complete dump as opposed
            #To an interruption, rename it and try again
            shutil.copytree(possibledir,os.path.join(directories.moduledir,name+"INCOMPLETE"))
            shutil.rmtree(possibledir)
        
    
def saveModules(where):
    with modulesLock:
        for i in ActiveModules:
            #Iterate over all of the resources in a module and save them as json files
            #under the URL urld module name for the filename.
            for resource in ActiveModules[i]:
                #Make sure there is a directory at where/module/
                util.ensure_dir(os.path.join(where,url(i),url(resource))  )
                #Open a file at /where/module/resource
                with  open(os.path.join(where,url(i),url(resource)),"w") as f:
                    #Make a json file there and prettyprint it
                    json.dump(ActiveModules[i][resource],f,sort_keys=True,indent=4, separators=(',', ': '))

            #Now we iterate over the existing resource files in the filesystem and delete those that correspond to
            #modules that have been deleted in the ActiveModules workspace thing.
            for i in util.get_immediate_subdirectories(os.path.join(where,url(i))):
                if unurl(i) not in ActiveModules:  
                    os.remove(os.path.join(where,url(i),i))

        for i in util.get_immediate_subdirectories(where):
            #Look in the modules directory, and if the module folder is not in ActiveModules\
            #We assume the user deleted the module so we should delete the save file for it.
            #Note that we URL url file names for the module filenames and foldernames.
            if unurl(i) not in ActiveModules:
                shutil.rmtree(os.path.join(where,i))
        with open(os.path.join(where,'__COMPLETE__'),'w') as f:
            f.write("By this string of contents quite arbitrary, I hereby mark this dump as consistant!!!")


#Load all modules in the given folder to RAM
def loadModules(modulesdir):
    for i in util.get_immediate_subdirectories(modulesdir):
        loadModule(i,modulesdir)

#Load a single module. Used by loadModules
def loadModule(moduledir,path_to_module_folder):
    with modulesLock:
        #Make an empty dict to hold the module resources
        module = {} 
        #Iterate over all resource files and load them
        for i in util.get_files(os.path.join(path_to_module_folder,moduledir)):
            try:
                f = open(os.path.join(path_to_module_folder,moduledir,i))
                #Load the resource and add it to the dict. Resouce names are urlencodes in filenames.
                module[unurl(i)] = json.load(f)
            finally:
                f.close()
        
        name = unurl(moduledir)
        ActiveModules[name] = module
        bookkeeponemodule(name)

def getModuleAsZip(module):
    with modulesLock:
        #We use a stringIO so we can avoid using a real file.
        ram_file = StringIO()
        z = zipfile.ZipFile(ram_file,'w')
        #Dump each resource to JSON in the ZIP
        for resource in ActiveModules[module]:
            #AFAIK Zip files fake the directories with naming conventions
            s = json.dumps(ActiveModules[module][resource],sort_keys=True,indent=4, separators=(',', ': '))
            z.writestr(url(module)+'/'+url(resource)+".json",s)
        z.close()
        s = ram_file.getvalue()
        ram_file.close()
        return s
    
def load_modules_from_zip(f):
    "Given a zip file, import all modules found therin."
    new_modules = {}
    z = zipfile.ZipFile(f)

    for i in z.namelist():
        #get just the folder, ie the module
        p = unurl(i.split('/')[0])
        #Remove the.json by getting rid of last 5 chars
        n = unurl((i.split('/'))[1][:-5])
        if p not in new_modules:
            new_modules[p] = {}
        f = z.open(i)
        new_modules[p][n] = json.loads(f.read().decode())
        f.close()
    
    with modulesLock:
        for i in new_modules:
            if i in ActiveModules:
                raise cherrypy.HTTPRedirect("/errors/alreadyexists")
        for i in new_modules:
            ActiveModules[i] = new_modules[i]
            messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " uploaded module" + i + " from a zip file")    
            bookkeeponemodule(i)
            
    z.close()

def bookkeeponemodule(module):
    """Given the name of one module that has been copied to activemodules but nothing else,
    let the rest of the system know the module is there."""
    scopes[module] = obj()
    for i in ActiveModules[module]:
        if ActiveModules[module][i]['resource-type'] == 'page':
            usrpages.updateOnePage(i,module)
        if ActiveModules[module][i]['resource-type'] == 'event':
           newevt.updateOneEvent(i,module)
    


#The clas defining the interface to allow the user to perform generic create/delete/upload functionality.
class WebInterface():
    
    #This lets the user download a module as a zip file
    @cherrypy.expose
    def downloads(self,module):
        pages.require('/admin/modules.view')
        cherrypy.response.headers['Content-Type']= 'application/zip'
        return getModuleAsZip(module)
    
    #This lets the user upload modules
    @cherrypy.expose
    def upload(self):
        pages.require('/admin/modules.edit')
        return pages.get_template("modules/upload.html").render()
        #This lets the user upload modules
        
    @cherrypy.expose
    def uploadtarget(self,modules):
        pages.require('/admin/modules.edit')
        load_modules_from_zip(modules.file)
        raise cherrypy.HTTPRedirect("/modules/") 
            
        
    
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
        usrpages.removeModulePages(kwargs['name'])
        messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " Deleted module " + kwargs['name'])    
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
                scopes[kwargs['name']] = obj()
                #Go directly to the newly created module
                messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " Created Module " + kwargs['name'])    
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
                   
                if r['resource-type'] == 'page':
                    usrpages.removeOnePage(module,kwargs['name'])
                #Annoying bookkeeping crap to get rid of the cached crap
                if r['resource-type'] == 'event':
                    newevt.removeOneEvent(module,kwargs['name'])
                    
                if r['resource-type'] == 'permission':
                    auth.importPermissionsFromModules() #sync auth's list of permissions
                    
                messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " deleted resource " +
                           kwargs['name'] + " from module " + module)    
                raise cherrypy.HTTPRedirect('/modules')

            #This is the target used to change the name and description(basic info) of a module  
            if path[0] == 'update':
                pages.require("/admin/modules.edit")
                with modulesLock:
                    ActiveModules[module]['__description']['text'] = kwargs['description']
                    ActiveModules[kwargs['name']] = ActiveModules.pop(module)
                    
                    #UHHG. So very much code tht just syncs data structures.
                    #This gets rid of the cache under the old name
                    newevt.removeModuleEvents(module)
                    usrpages.removeModulePages(module)
                    #And calls this function the generate the new cache
                    bookkeeponemodule(kwargs['name'])
                    #Just for fun, we should probably also sync the permissions
                    auth.importPermissionsFromModules()
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
    def insertResource(r):
        ActiveModules[module][kwargs['name']] = r
    
    with modulesLock:
        #Check if a resource by that name is already there
        if kwargs['name'] in ActiveModules[module]:
            raise cherrypy.HTTPRedirect("/errors/alreadyexists")
        
        #Create a permission
        if type == 'permission':
            insertResource({
                "resource-type":"permission",
                "description":kwargs['description']})
            #has its own lock
            auth.importPermissionsFromModules() #sync auth's list of permissions 
            
        if type == 'event':
            insertResource({
                "resource-type":"event",
                "trigger":"False",
                "action":"pass",
                "once":True})
            #newevt maintains a cache of precompiled events that must be kept in sync with
            #the modules
            newevt.updateOneEvent(kwargs['name'],module)
        
        if type == 'page':
                insertResource({
                    "resource-type":"page",
                    "body":"Content here",
                    'no-navheader':True})
                usrpages.updateOnePage(kwargs['name'],module)

        messagebus.postMessage("/system/notifications", "User "+ pages.getAcessingUser() + " added resource " +
                           kwargs['name'] + " of type " + type+" to module " + module)
        
        #Take the user straight to the resource page
        raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module)+'/resource/'+util.url(name))
                
                      
#show a edit page for a resource. No side effect here so it only requires the view permission
def resourceEditPage(module,resource):
    pages.require("/admin/modules.view")
    with modulesLock:
        resourceinquestion = ActiveModules[module][resource]
        
        if resourceinquestion['resource-type'] == 'permission':
            return permissionEditPage(module, resource)

        if resourceinquestion['resource-type'] == 'event':
            return pages.get_template("modules/events/event.html").render(
                module =module,
                name =resource,
                event =ActiveModules[module][resource])

        if resourceinquestion['resource-type'] == 'page':
            if 'require-permissions' in resourceinquestion:
                requiredpermissions = resourceinquestion['require-permissions']
            else:
                requiredpermissions = []
                
            return pages.get_template("modules/pages/page.html").render(module=module,name=resource,
            page=ActiveModules[module][resource],requiredpermissions = requiredpermissions)

def permissionEditPage(module,resource):
    pages.require("/admin/modules.view")
    return pages.get_template("modules/permissions/permission.html").render(module = module, 
    permission = resource, description = ActiveModules[module][resource]['description'])

#The actual POST target to modify a resource. Context dependant based on resource type.
def resourceUpdateTarget(module,resource,kwargs):
    pages.require("/admin/modules.edit")

    with modulesLock:
        t = ActiveModules[module][resource]['resource-type']
        resourceobj = ActiveModules[module][resource]
        
        if t == 'permission': 
            resourceobj['description'] = kwargs['description']
            #has its own lock
            auth.importPermissionsFromModules() #sync auth's list of permissions 
    
        if t == 'event':
            e = newevt.Event(kwargs['trigger'],kwargs['action'],{})#Test compile, throw error on fail.
            resourceobj['trigger'] = kwargs['trigger']
            resourceobj['action'] = kwargs['action']
            resourceobj['setup'] = kwargs['setup']
            resourceobj['priority'] = max([int(kwargs['priority']),0])
            resourceobj['continual'] = 'continual' in kwargs
            resourceobj['rate-limit'] = float(kwargs['ratelimit'])
            #I really need to do something about this possibly brittle bookkeeping system
            #But anyway, when the active modules thing changes we must update the newevt cache thing.
            newevt.updateOneEvent(resource,module)
    
        if t == 'page':
            resourceobj['body'] = kwargs['body']
            resourceobj['no-navheader'] = 'no-navheader' in kwargs
            resourceobj['no-header'] = 'no-header' in kwargs       
            #Method checkboxes
            resourceobj['require-method'] = []
            if 'allow-GET' in kwargs:
                resourceobj['require-method'].append('GET')
            if 'allow-POST' in kwargs:
                resourceobj['require-method'].append('POST')                
            #permission checkboxes
            resourceobj['require-permissions'] = []
            for i in kwargs:
                #Since HTTP args don't have namespaces we prefix all the permission checkboxes with permission
                if i[:10] == 'Permission':
                    if kwargs[i] == 'true':
                        resourceobj['require-permissions'].append(i[10:])
            usrpages.updateOnePage(resource,module)
            
    messagebus.postMessage("/system/notifications", "User "+ pages.getAcessingUser() + " modified resource " +
                           resource + " of module " + module)
    #Return user to the module page       
    raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module))#+'/resource/'+util.url(resource))
    

        
class KaithemEvent(dict):
    pass



