#Copyright Daniel Dunn 2015
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

import threading,urllib,shutil,sys,time,os,json,traceback, copy
import cherrypy,yaml
from . import auth,pages,directories,util,newevt,kaithemobj,usrpages,messagebus,scheduling
from .modules import *
from src import modules

searchable = {'event': ['setup', 'trigger', 'action'], 'page':['body']}

def searchModules(search,max_results=100,start=0,mstart=0):
    pointer =mstart
    results = []
    for i in sorted(ActiveModules.keys(),reverse=True)[mstart:]:
        x = searchModuleResources(i,search,max_results,start)
        if x[0]:
            results.append((i,x[0]))
        max_results -=len(x[0])
        start =0
        pointer += 1
        if not max_results:
            return(results,max(0,pointer-1),x[1])
    return(results,max(0,pointer-1),x[1])
        

def searchModuleResources(modulename,search,max_results=100,start=0):
    m = ActiveModules[modulename]
    results = []
    pointer = start
    for i in sorted(m.keys(),reverse=True)[start:]:
        if not max_results>0:
            return(results,pointer)
        pointer += 1
        if m[i]['resource-type'] in searchable:
            if search in i:
                results.append(i)
                max_results -=1
                continue
            for j in searchable[ m[i]['resource-type']]:
                x= m[i][j].find(search)
                if x>0:
                    results.append(i)
                    max_results -=1
                    break
    return(results, pointer)


#The class defining the interface to allow the user to perform generic create/delete/upload functionality.
class WebInterface():
    @cherrypy.expose
    def search(self,module,**kwargs):
        start=mstart=0
        if 'mstart' in kwargs:
            mstart = int(kwargs['mstart'])
        if 'start' in kwargs:
            start = int(kwargs['start'])
        pages.require("/admin/modules.edit")
        if not module=="__all__":
            return pages.get_template("modules/search.html").render(search=kwargs['search'], name=module,results=searchModuleResources(module,kwargs['search'],100,start))
        else:
            return pages.get_template("modules/search.html").render(search=kwargs['search'], name=module,results=searchModules(kwargs['search'],100,start,mstart))

    
    @cherrypy.expose
    def nextrun(self,**kwargs):
        pages.require('/admin/modules.view')

        return str(scheduling.get_next_run(kwargs['string']))
    
    

    #This lets the user download a module as a zip file with yaml encoded resources
    @cherrypy.expose
    def yamldownload(self,module):
        pages.require('/admin/modules.view')
        cherrypy.response.headers['Content-Type']= 'application/zip'
        return getModuleAsYamlZip(module[:-4] if module.endswith('.zip') else module)

    #This lets the user download a module as a zip file
    @cherrypy.expose
    def download(self,module):
        pages.require('/admin/modules.view')
        cherrypy.response.headers['Content-Type']= 'application/zip'
        return getModuleAsZip(module[:-4])
    
    #This lets the user download a module as a zip file. But this one is deprecated.
    #It's only here for backwards compatibility, but it really doesn't matter.
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
        
        modules.moduleschanged = True
        load_modules_from_zip(modules.file)
        messagebus.postMessage("/system/modules/uploaded",{'user':pages.getAcessingUser()})
        raise cherrypy.HTTPRedirect("/modules/")



    @cherrypy.expose
    def index(self):
        #Require permissions and render page. A lotta that in this file.
        pages.require("/admin/modules.view")
        return pages.get_template("modules/index.html").render(ActiveModules = ActiveModules)

    @cherrypy.expose
    def library(self):
        #Require permissions and render page. A lotta that in this file.
        pages.require("/admin/modules.view")
        return pages.get_template("modules/library.html").render()


    @cherrypy.expose
    def newmodule(self):
        pages.require("/admin/modules.edit")
        return pages.get_template("modules/new.html").render()
    
    #@cherrypy.expose
    #def manual_run(self,module, resource):
        ##These modules handle their own permissions
        #if isinstance(EventReferences[module,resource], newevt.ManualEvent):
            #EventReferences[module,resource].run()
        #else:
            #raise RuntimeError("Event does not support running manually")
        
    #CRUD screen to delete a module
    @cherrypy.expose
    def deletemodule(self):
        pages.require("/admin/modules.edit")
        return pages.get_template("modules/delete.html").render()

    #POST target for CRUD screen for deleting module
    @cherrypy.expose
    def deletemoduletarget(self,**kwargs):
        pages.require("/admin/modules.edit")
        pages.postOnly()
        
        modules.moduleschanged = True
        with modulesLock:
           ActiveModules.pop(kwargs['name'])
        #Get rid of any lingering cached events
        newevt.removeModuleEvents(kwargs['name'])
        #Get rid of any permissions defined in the modules.
        auth.importPermissionsFromModules()
        usrpages.removeModulePages(kwargs['name'])
        messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " Deleted module " + kwargs['name'])
        messagebus.postMessage("/system/modules/unloaded",kwargs['name'])
        messagebus.postMessage("/system/modules/deleted",{'user':pages.getAcessingUser()})
        raise cherrypy.HTTPRedirect("/modules")

    @cherrypy.expose
    def newmoduletarget(self,**kwargs):
        global scopes
        pages.require("/admin/modules.edit")
        pages.postOnly()
        
        modules.moduleschanged = True
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
                messagebus.postMessage("/system/modules/new",{'user':pages.getAcessingUser(), 'module':kwargs['name']})
                raise cherrypy.HTTPRedirect("/modules/module/"+util.url(kwargs['name']))
            else:
                return pages.get_template("error.html").render(info = " A module already exists by that name,")

    @cherrypy.expose
    def loadlibmodule(self,module):
        pages.require("/admin/modules.edit")
        pages.postOnly()
        if module  in ActiveModules:
            raise cherrypy.HTTPRedirect("/errors/alreadyexists")

        loadModule(module,os.path.join(directories.datadir,"modules"))
        bookkeeponemodule(module)
        auth.importPermissionsFromModules()
        raise cherrypy.HTTPRedirect('/modules')


    @cherrypy.expose
    #This function handles HTTP requests of or relating to one specific already existing module.
    #The URLs that this function handles are of the form /modules/module/<modulename>[something?]
    def module(self,module,*path,**kwargs):
        
        root = util.split_escape(module,"/")[0]
        modulepath = util.split_escape(module,"/")[1:]
        fullpath = module
        if len(path)>2:
         fullpath += "/" + path[2]
        #If we are not performing an action on a module just going to its page
        if not path:
            pages.require("/admin/modules.view")
            return pages.get_template("modules/module.html").render(module = ActiveModules[root],name = root,path=modulepath,fullpath=fullpath)

        else:

            if path[0] == 'obj':
                #There might be a password or something important in the actual module object. Best to restrict who can access it.
                pages.require("/admin/modules.edit")
                return pages.get_template("modules/modulescope.html").render(name = root, obj = scopes[root])

            #This gets the interface to add a page
            if path[0] == 'addresource':
                if len(path)>2:
                  x = path[2]
                else:
                  x =""
                #path[1] tells what type of resource is being created and addResourceDispatcher returns the appropriate crud screen
                return addResourceDispatcher(module,path[1],x)

            #This case handles the POST request from the new resource target
            if path[0] == 'addresourcetarget':
                if len(path)>2:
                  x = path[2]
                else:
                  x =""
                return addResourceTarget(module,path[1],kwargs['name'],kwargs,x)

            #This case shows the information and editing page for one resource
            if path[0] == 'resource':
                version = '__default__'
                if len(path)>2:
                    version = path[2]
                return resourceEditPage(module,path[1],version)

            #This goes to a dispatcher that takes into account the type of resource and updates everything about the resource.
            if path[0] == 'updateresource':
                return resourceUpdateTarget(module,path[1],kwargs)

            #This returns a page to delete any resource by name
            if path[0] == 'deleteresource':
                pages.require("/admin/modules.edit", noautoreturn = True)
                if len(path)>1:
                    x = path[1]
                else:
                    x =""
                return pages.get_template("modules/deleteresource.html").render(module=module,r=x)

            #This handles the POST request to actually do the deletion
            if path[0] == 'deleteresourcetarget':
                pages.require("/admin/modules.edit")
                pages.postOnly()
                modules.moduleschanged = True
                with modulesLock:
                   r = ActiveModules[root].pop(kwargs['name'])

                if r['resource-type'] == 'page':
                    usrpages.removeOnePage(module,kwargs['name'])
                #Annoying bookkeeping crap to get rid of the cached crap
                if r['resource-type'] == 'event':
                    newevt.removeOneEvent(module,kwargs['name'])

                if r['resource-type'] == 'permission':
                    auth.importPermissionsFromModules() #sync auth's list of permissions

                messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " deleted resource " +
                           kwargs['name'] + " from module " + module)
                messagebus.postMessage("/system/modules/deletedresource",{'ip':cherrypy.request.remote.ip,'user':pages.getAcessingUser(),'module':module,'resource':kwargs['name']})
                if len(util.split_escape(kwargs['name'],'/','\\'))>1:
                    raise cherrypy.HTTPRedirect('/modules/module/'+util.url(module)+'/resource/'+util.url(util.module_onelevelup(kwargs['name'])))
                else:
                    raise cherrypy.HTTPRedirect('/modules/module/'+util.url(module))

            #This is the target used to change the name and description(basic info) of a module
            if path[0] == 'update':
                pages.require("/admin/modules.edit")
                pages.postOnly()
                modules.moduleschanged = True
                with modulesLock:
                    ActiveModules[root]['__description']['text'] = kwargs['description']
                    ActiveModules[kwargs['name']] = ActiveModules.pop(root)

                    #UHHG. So very much code tht just syncs data structures.
                    #This gets rid of the cache under the old name
                    newevt.removeModuleEvents(root)
                    usrpages.removeModulePages(root)
                    #And calls this function the generate the new cache
                    bookkeeponemodule(kwargs['name'],update=True)
                    #Just for fun, we should probably also sync the permissions
                    auth.importPermissionsFromModules()
                raise cherrypy.HTTPRedirect('/modules/module/'+util.url(kwargs['name']))

#Return a CRUD screen to create a new resource taking into the type of resource the user wants to create
def addResourceDispatcher(module,type,path):
    pages.require("/admin/modules.edit")

    #Return a crud to add a new permission
    if type == 'permission':
        return pages.get_template("modules/permissions/new.html").render(module=module,path=path)

    #return a crud to add a new event
    if type == 'event':
        return pages.get_template("modules/events/new.html").render(module=module,path=path)

    #return a crud to add a new event
    if type == 'page':
        return pages.get_template("modules/pages/new.html").render(module=module,path=path)

    #return a crud to add a new event
    if type == 'directory':
        return pages.get_template("modules/directories/new.html").render(module=module,path=path)

#The target for the POST from the CRUD to actually create the new resource
#Basically it takes a module, a new resource name, and a type, and creates a template resource
def addResourceTarget(module,type,name,kwargs,path):
    pages.require("/admin/modules.edit")
    pages.postOnly()
    
    modules.moduleschanged = True

    #Wow is this code ever ugly. Bascially we are going to pack the path and the module together.
    escapedName = (kwargs['name'].replace("\\","\\\\").replace("/",'\\/'))
    if path:
      escapedName = path+ "/" + escapedName
    x = util.split_escape(module,"/","\\")
    escapedName = "/".join(x[1:]+[escapedName])
    root = x[0]

    def insertResource(r):
        ActiveModules[root][escapedName] = r

    with modulesLock:
        #Check if a resource by that name is already there
        if escapedName in ActiveModules[root]:
            raise cherrypy.HTTPRedirect("/errors/alreadyexists")

        #Create a permission
        if type == 'directory':
            insertResource({
                "resource-type":"directory"})
            raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module))


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
                "setup" : "#This code runs once when the event loads. It also runs when you save the event during the test compile\n#and may run multiple times when kaithem boots due to dependancy resolution\n__doc__=''",
                "trigger":"False",
                "action":"pass",
                "once":True,
                "disabled":False
                }

                           )
            #newevt maintains a cache of precompiled events that must be kept in sync with
            #the modules
            newevt.updateOneEvent(escapedName,root)

        if type == 'page':
                insertResource({
                    "resource-type":"page",
                    "body":'<%!\n#Code Here runs once when page is first rendered. Good place for import statements.\n__doc__= ""\n%>\n<%\n#Python Code here runs every page load\n%>\n<h2>Title</h2>\n<div class="sectionbox">\nContent here\n</div>',
                    'no-navheader':True})
                usrpages.updateOnePage(escapedName,root)

        messagebus.postMessage("/system/notifications", "User "+ pages.getAcessingUser() + " added resource " +
                           escapedName + " of type " + type+" to module " + root)

        #Take the user straight to the resource page
        raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module)+'/resource/'+util.url(escapedName))


#show a edit page for a resource. No side effect here so it only requires the view permission
def resourceEditPage(module,resource,version='default'):
    pages.require("/admin/modules.view")

    #Workaround for cherrypy decoding unicode as if it is latin 1
    #Because of some bizzare wsgi thing i think.
    module=module.encode("latin-1").decode("utf-8")
    resource=resource.encode("latin-1").decode("utf-8")

    with modulesLock:
        resourceinquestion = ActiveModules[module][resource]
        if version == '__default__':
            try:
                resourceinquestion = ActiveModules[module][resource]['versions']['__draft__']
                version = '__draft__'
            except KeyError as e:
                version = "__live__"
                pass
        else:
            version = '__live__'

        if resourceinquestion['resource-type'] == 'permission':
            return permissionEditPage(module, resource)

        if resourceinquestion['resource-type'] == 'event':
            return pages.get_template("modules/events/event.html").render(
                module =module,
                name =resource,
                event =resourceinquestion,
                version=version)

        if resourceinquestion['resource-type'] == 'page':
            if 'require-permissions' in resourceinquestion:
                requiredpermissions = resourceinquestion['require-permissions']
            else:
                requiredpermissions = []

            return pages.get_template("modules/pages/page.html").render(module=module,name=resource,
            page=ActiveModules[module][resource],requiredpermissions = requiredpermissions)

        if resourceinquestion['resource-type'] == 'directory':
            pages.require("/admin/modules.view")
            return pages.get_template("modules/module.html").render(module = ActiveModules[module],name = module, path=util.split_escape(resource,'\\'), fullpath=module+"/"+resource)

def permissionEditPage(module,resource):
    pages.require("/admin/modules.view")
    return pages.get_template("modules/permissions/permission.html").render(module = module,
    permission = resource, description = ActiveModules[module][resource]['description'])

#The actual POST target to modify a resource. Context dependant based on resource type.
def resourceUpdateTarget(module,resource,kwargs):
    pages.require("/admin/modules.edit",noautoreturn=True)
    pages.postOnly()
    
    modules.moduleschanged = True
    with modulesLock:
        t = ActiveModules[module][resource]['resource-type']
        resourceobj = ActiveModules[module][resource]
        if t == 'permission':
            resourceobj['description'] = kwargs['description']
            #has its own lock
            auth.importPermissionsFromModules() #sync auth's list of permissions

        if t == 'event':

            #Test compile, throw error on fail.
            try:
                evt = newevt.Event(kwargs['trigger'],kwargs['action'],newevt.make_eventscope(module),setup=kwargs['setup'],m=module,r=resource)
                del evt
                time.sleep(0.1)
            except Exception as e:
                if not 'versions' in resourceobj:
                    resourceobj['versions'] = {}
                resourceobj['versions']['__draft__'] = r = resourceobj.copy().pop('versions')
                r['resource-type'] = 'event'
                r['trigger'] = kwargs['trigger']
                r['action'] = kwargs['action']
                r['setup'] = kwargs['setup']
                r['priority'] = kwargs['priority']
                r['continual'] = 'continual' in kwargs
                r['rate-limit'] = float(kwargs['ratelimit'])
                messagebus.postMessage("system/errors/misc/failedeventupdate", "In: "+ module +" "+resource+ "\n"+ traceback.format_exc(4))
                raise

            resourceobj['trigger'] = kwargs['trigger']
            resourceobj['action'] = kwargs['action']
            resourceobj['setup'] = kwargs['setup']
            resourceobj['priority'] = kwargs['priority']
            resourceobj['continual'] = 'continual' in kwargs
            resourceobj['rate-limit'] = float(kwargs['ratelimit'])
            #I really need to do something about this possibly brittle bookkeeping system
            #But anyway, when the active modules thing changes we must update the newevt cache thing.


            #Delete the draft if any
            try:
                del resourceobj['versions']['__draft__']
            except:
                pass


            newevt.updateOneEvent(resource,module)

        if t == 'page':
            resourceobj['body'] = kwargs['body']
            resourceobj['no-navheader'] = 'no-navheader' in kwargs
            resourceobj['no-header'] = 'no-header' in kwargs
            resourceobj['dont-show-in-index'] = 'dont-show-in-index' in kwargs
            resourceobj['auto-reload'] = 'autoreload' in kwargs
            resourceobj['allow-xss'] = 'allow-xss' in kwargs
            resourceobj['allow-origins'] = [i.strip() for i in kwargs['allow-origins'].split(',')]
            resourceobj['auto-reload-interval'] = float(kwargs['autoreloadinterval'])
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

        if 'name' in kwargs:
            if not kwargs['name'] == resource:
                mvResource(module,resource,module,kwargs['name'])

    messagebus.postMessage("/system/notifications", "User "+ pages.getAcessingUser() + " modified resource " +
                           resource + " of module " + module)
    r =resource
    if 'name' in kwargs:
        r = kwargs['name']
    if 'GoNow' in kwargs:
        raise cherrypy.HTTPRedirect(usrpages.url_for_resource(module,r))
    #Return user to the module page. If name has a folder, return the user to it;s containing folder.
    x = util.split_escape(r,"/")
    if len(x)>1:
        raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module)+'/resource/'+'/'.join([util.url(i) for i in x[:-1]])+"#resources")
    else:
        raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module)+"#resources")#+'/resource/'+util.url(resource))