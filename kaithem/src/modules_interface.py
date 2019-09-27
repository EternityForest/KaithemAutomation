#Copyright Daniel Dunn 2015, 2017
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

import threading,urllib,shutil,sys,time,os,json,traceback, copy,mimetypes,uuid
import cherrypy,yaml
from . import auth,pages,directories,util,newevt,kaithemobj,usrpages,messagebus,scheduling, registry,remotedevices
from .modules import *
from src import modules
from src.config import config
from cherrypy.lib.static import serve_file

searchable = {'event': ['setup', 'trigger', 'action'], 'page':['body']}

def validate_upload():
    #Allow 4gb uploads for admin users, otherwise only allow 64k 
    return 64*1024 if not pages.canUserDoThis("/admin/modules.edit") else 1024*1024*4096

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


def followAttributes(root, path):
    l = util.split_escape(path,",",escape="\\")
    for i in l:
        if i.startswith("t"):
            root =root[tuple(json.loads(i[1:]))]
        elif i.startswith("a"):
            root = getattr(root, i[1:])
        elif i.startswith("i"):
            root = root[int(i[1:])]
        #This one is mostly for weak refs. Watch out we don't make any refs stick around that shouldn't
        elif i.startswith("c"):
            root = root()
        else:
            root = root[util.unurl(i[1:])]
    return root

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
        if config["downloads-include-md5-in-filename"]:
            cherrypy.response.headers['Content-Disposition'] = 'attachment; filename="%s"'%util.url(module[:-4]+"_"+getModuleHash(module[:-4]))
        cherrypy.response.headers['Content-Type']= 'application/zip'
        try:
            return getModuleAsYamlZip(module[:-4] if module.endswith('.zip') else module, noFiles =not pages.canUserDoThis("/admin/modules.edit"))
        except:
            logging.exception("Failed to handle zip download request")
            raise
    #This lets the user download a module as a zip file
    @cherrypy.expose
    def download(self,module):
        pages.require('/admin/modules.view')
        if config["downloads-include-md5-in-filename"]:
            cherrypy.response.headers['Content-Disposition'] = 'attachment; filename="%s"' % util.url(module[:-4]+"_"+getModuleHash(module[:-4]))
        cherrypy.response.headers['Content-Type']= 'application/zip'
        try:
            return getModuleAsZip(module[:-4],noFiles =not pages.canUserDoThis("/admin/modules.edit"))
        except:
            logging.exception("Failed to handle zip download request")


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
    @cherrypy.config(**{'tools.allow_upload.on':True, 'tools.allow_upload.f':validate_upload})
    def uploadtarget(self,modulesfile,**kwargs):
        pages.require('/admin/modules.edit')
        pages.postOnly()
        modulesHaveChanged()
        for i in load_modules_from_zip(modulesfile.file, replace='replace' in kwargs):
            unsaved_changed_obj[i] = "Module uploaded by"+ pages.getAcessingUser()
            for j in ActiveModules[i]:
                unsaved_changed_obj[i,j] = "Resource is part of module uploaded by"+ pages.getAcessingUser()

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
    def editlibrary(self):
        pages.require("/admin/modules.edit")
        return pages.get_template("modules/library_edit.html").render()


    @cherrypy.expose
    def newmodule(self):
        pages.require("/admin/modules.edit")
        return pages.get_template("modules/new.html").render()

    @cherrypy.expose
    def savemodule(self, module):
        pages.require("/admin/modules.edit")
        return pages.get_template("modules/savemodule.html").render(m=module)

    @cherrypy.expose
    def savemoduletarget(self, module):
        with modulesLock:
            pages.require("/admin/modules.edit")
            pages.postOnly()
            s = saveModule(ActiveModules[module],external_module_locations[module],module)
            if not os.path.isfile(os.path.join(directories.moduledir,"data","__"+url(module)+".location")):
                with open(os.path.join(directories.moduledir,"data","__"+url(module)+".location"),"w") as f:
                    f.write(external_module_locations[module])
            for i in s:
                if i in unsaved_changed_obj:
                    del unsaved_changed_obj[i]

        raise cherrypy.HTTPRedirect("/modules")

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
        rmModule(kwargs['name'],"Module Deleted by " + pages.getAcessingUser())
        messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " Deleted module " + kwargs['name'])

        raise cherrypy.HTTPRedirect("/modules")

    @cherrypy.expose
    def newmoduletarget(self,**kwargs):
        global scopes
        pages.require("/admin/modules.edit")
        pages.postOnly()

        #If there is no module by that name, create a blank template and the scope obj
        with modulesLock:
            if kwargs['name'] in ActiveModules:
                return pages.get_template("error.html").render(info = " A module already exists by that name,")
            newModule(kwargs['name'], kwargs.get("location",None))
            raise cherrypy.HTTPRedirect("/modules/module/"+util.url(kwargs['name']))

    @cherrypy.expose
    def loadlibmodule(self,module):
        "Load a module from the library"
        pages.require("/admin/modules.edit")
        pages.postOnly()
        if module  in ActiveModules:
            raise cherrypy.HTTPRedirect("/errors/alreadyexists")

        loadModule(os.path.join(directories.datadir,"modules",module),module)
        modulesHaveChanged()
        unsaved_changed_obj[module]="Loaded from library by user"
        for i in ActiveModules[module]:
            unsaved_changed_obj[module,i]= "Loaded from kibrary by user"
        bookkeeponemodule(module)
        auth.importPermissionsFromModules()
        raise cherrypy.HTTPRedirect('/modules')

    @cherrypy.expose
    def editlibmodule(self,module):
        "Load a module from the library"
        pages.require("/admin/modules.edit")
        pages.postOnly()
        if module  in ActiveModules:
            raise cherrypy.HTTPRedirect("/errors/alreadyexists")

        #This is the only difference. In edit mode we can load a library module
        #And save it back to the library. At the moment this is pretty much entirely
        #For developers
        external_module_locations[kwargs['name']]= kwargs['location']

        loadModule(os.path.join(directories.datadir,"modules",module),module)
        modulesHaveChanged()
        unsaved_changed_obj[module]="Loaded from library by user"
        for i in ActiveModules[module]:
            unsaved_changed_obj[module,i]= "Loaded from kibrary by user"
        bookkeeponemodule(module)
        auth.importPermissionsFromModules()
        raise cherrypy.HTTPRedirect('/modules')


    @cherrypy.expose
    @cherrypy.config(**{'tools.allow_upload.on':True, 'tools.allow_upload.f':validate_upload})
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
            if path[0] == 'runevent':
                pages.require("/admin/modules.edit")
                pages.postOnly()
                newevt.manualRun((module,kwargs['name']))
                raise cherrypy.HTTPRedirect('/modules/module/'+util.url(root))

            if path[0] == 'runeventdialog':
                #There might be a password or something important in the actual module object. Best to restrict who can access it.
                pages.require("/admin/modules.edit")
                return pages.get_template("modules/events/run.html").render(module = root,event=path[1])

            if path[0] == 'obj':
                #There might be a password or something important in the actual module object. Best to restrict who can access it.
                pages.require("/admin/modules.edit")

                if path[1] == "module":
                    obj = scopes[root]
                    objname = "Module Obj: " +root

                if path[1] == "event":
                    obj = newevt.EventReferences[root,path[2]].pymodule
                    objname = "Event: " +path[2]

                #Inspector should prob be its own module since it does all this.
                if path[1] == "sys":
                    import kaithem
                    obj = kaithem
                    objname = "PythonRoot"

                if 'objname' in kwargs:
                    objname = kwargs['objname']

                if not "objpath" in kwargs:
                    return pages.get_template("modules/modulescope.html").render(kwargs=kwargs, name = root,obj=obj, objname=objname)
                else:
                    return pages.get_template("obj_insp.html").render(objpath = kwargs['objpath'],objname=objname, obj = followAttributes(obj,kwargs['objpath']))

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
                return resourceEditPage(module,path[1],version,kwargs)

            #This goes to a dispatcher that takes into account the type of resource and updates everything about the resource.
            if path[0] == 'updateresource':
                return resourceUpdateTarget(module,path[1],kwargs)

            #This goes to a dispatcher that takes into account the type of resource and updates everything about the resource.
            if path[0] == 'reloadresource':
                pages.require("/admin/modules.edit")
                modules.reloadOneResource(module,path[1])
                return resourceEditPage(module,path[1],version,kwargs)

            if path[0] == 'getfileresource':
                pages.require("/admin/modules.edit")
                folder = os.path.join(directories.vardir,"modules","filedata")
                data_basename =fileResourceAbsPaths[module,path[1]]
                dataname = os.path.join(folder,data_basename)
                if os.path.isfile(dataname):
                    return serve_file(dataname,
                    content_type=mimetypes.guess_type(path[1],False)[0] or "application/x-unknown",
                    disposition="inline;",
                    name=path[1])


            #This gets the interface to add a page
            if path[0] == 'addfileresource':
                pages.require("/admin/modules.edit")
                if len(path)>1:
                    x = path[1]
                else:
                    x =""
                #path[1] tells what type of resource is being created and addResourceDispatcher returns the appropriate crud screen
                return pages.get_template("modules/uploadfileresource.html").render(module=module,path=x)


            #This goes to a dispatcher that takes into account the type of resource and updates everything about the resource.
            if path[0] == 'uploadfileresourcetarget':
                pages.require("/admin/modules.edit", noautoreturn = True)
                pages.postOnly()

                if not module in external_module_locations:
                    folder = os.path.join(directories.vardir,"modules","filedata")
                else:
                    folder = os.path.join(external_module_locations[module],"__filedata__")

                util.ensure_dir2(folder)
                data_basename = kwargs['name']

                dataname=data_basename
                if len(path)>1:
                    dataname = path[1]+'/'+dataname

                if not module in external_module_locations:
                    dataname = os.path.join(folder,module, dataname)
                else:
                    dataname = os.path.join(folder, dataname)

                inputfile = kwargs['file']

                util.ensure_dir(dataname)
                with open(dataname,"wb") as f:
                    while True:
                        d = inputfile.file.read(8192)
                        if not d:
                            break
                        f.write(d)

                with modulesLock:
                    #####BEGIN BLOCK OF CODE COPY PASTED FROM ANOTHER PART OF CODE. I DO NOT REALLY UNDERSTAND IT
                    #Wow is this code ever ugly. Bascially we are going to pack the path and the module together.
                    escapedName = (kwargs['name'].replace("\\","\\\\").replace("/",'\\/'))
                    if len(path)>1:
                        escapedName = path[1]+ "/" + escapedName
                    x = util.split_escape(module,"/","\\")
                    escapedName = "/".join(x[1:]+[escapedName])
                    root = x[0]
                    unsaved_changed_obj[(root,escapedName)] = "Resource added by"+ pages.getAcessingUser()

                    def insertResource(r):
                        ActiveModules[root][escapedName] = r
                        modules_state.createRecoveryEntry(root,escapedName,r)
                    ####END BLOCK OF COPY PASTED CODE.

                    insertResource({'resource-type':'internal-fileref', 'target':"$MODULERESOURCES/"+data_basename})
                    if len(path)>1:
                        x = path[1]+"/"
                    else:
                        x =""
                    fileResourceAbsPaths[root,x+kwargs['name']] = dataname
                    modulesHaveChanged()
                raise cherrypy.HTTPRedirect("/modules/module/"+util.url(root))


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
                rmResource(module,kwargs['name'],"Resource Deleted by " + pages.getAcessingUser())

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
                modulesHaveChanged()
                with modulesLock:
                    if not kwargs['name'] == root:
                        unsaved_changed_obj[kwargs['name']] = "New name of module. "+ pages.getAcessingUser()+ " old name was "+root
                        unsaved_changed_obj[root] = "Old name of module that was renamed by "+ pages.getAcessingUser()+" new name is "+kwargs['name']
                    else:
                        unsaved_changed_obj[root] = "Module metadata changed"

                    if "location" in kwargs and kwargs['location']:
                        external_module_locations[kwargs['name']]= kwargs['location']
                        #We can't just do a delete and then set, what if something odd happens between?
                        if not kwargs['name']== root and root in external_module_locations:
                            del external_module_locations[root]
                    else:
                        #We must delete this before deleting the actual external_module_locations entry
                        #If this fails, we can still save, and will reload correctly.
                        #But if there was no entry, but there was a file,
                        #It would reload from the external, but save to the internal,
                        #Which would be very confusing. We want to load from where we saved.

                        #If we somehow have no file but an entry, saving will remake the file.
                        #If there's no entry, we will only be able to save by saving the whole state.
                        if  os.path.isfile(os.path.join(directories.moduledir,"data","__"+url(root)+".location")):
                            if root in external_module_locations:
                                os.remove(external_module_locations[root])

                        if root in external_module_locations:
                            external_module_locations.pop(root)
                    #Missing descriptions have caused a lot of bugs
                    if '__description' in ActiveModules[root]:
                        ActiveModules[root]['__description']['text'] = kwargs['description']
                    else:
                        ActiveModules[root]['__description'] = {'resource-type':'module-description','text':kwargs['description']}

                    #Renaming reloads the entire module.
                    #TODO This needs to handle custom resource types if we ever implement them.
                    if not kwargs['name'] == root:
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
    elif type == 'event':
        return pages.get_template("modules/events/new.html").render(module=module,path=path)

    #return a crud to add a new event
    elif type == 'k4dprog_sq':
        return pages.get_template("modules/remoteprograms/new.html").render(module=module,path=path)


    #return a crud to add a new event
    elif type == 'page':
        return pages.get_template("modules/pages/new.html").render(module=module,path=path)

    #return a crud to add a new event
    elif type == 'directory':
        return pages.get_template("modules/directories/new.html").render(module=module,path=path)
    else:
        return additionalTypes[type].createpage(module,path)

#The target for the POST from the CRUD to actually create the new resource
#Basically it takes a module, a new resource name, and a type, and creates a template resource
def addResourceTarget(module,type,name,kwargs,path):
    pages.require("/admin/modules.edit")
    pages.postOnly()
    modulesHaveChanged()

    #Wow is this code ever ugly. Bascially we are going to pack the path and the module together.
    escapedName = (kwargs['name'].replace("\\","\\\\").replace("/",'\\/'))
    if path:
        escapedName = path+ "/" + escapedName
    x = util.split_escape(module,"/","\\")
    escapedName = "/".join(x[1:]+[escapedName])
    root = x[0]
    unsaved_changed_obj[(root,escapedName)] = "Resource added by"+ pages.getAcessingUser()

    def insertResource(r):
        ActiveModules[root][escapedName] = r
        modules_state.createRecoveryEntry(module,escapedName, r)

    with modulesLock:
        #Check if a resource by that name is already there
        if escapedName in ActiveModules[root]:
            raise cherrypy.HTTPRedirect("/errors/alreadyexists")

        if type == 'directory':
            insertResource({
                "resource-type":"directory"})
            raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module))

        #Create a permission
        if type == 'k4dprog_sq':
            insertResource({
                "resource-type":"k4dprog_sq",
                "device": "__none__",
                "code":"",
                "prgid":name[-15:].replace("/","_")
                })

            remotedevices.updateProgram(root, escapedName,None, False)
            raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module))

        elif type == 'permission':
            insertResource({
                "resource-type":"permission",
                "description":kwargs['description']})
            #has its own lock
            auth.importPermissionsFromModules() #sync auth's list of permissions

        elif type == 'event':
            insertResource({
                "resource-type":"event",
                "setup" : "#This code runs once when the event loads. It also runs when you save the event during the test compile\n#and may run multiple times when kaithem boots due to dependancy resolution\n__doc__=''",
                "trigger":"False",
                "action":"pass",
                "once":True,
                "enable":True
                })
            #newevt maintains a cache of precompiled events that must be kept in sync with
            #the modules
            newevt.updateOneEvent(escapedName,root)

        elif type == 'page':
                basename=util.split_escape(name,'/','\\')[-1]
                insertResource({
                    "resource-type":"page",
                    "body":'<%!\n#Code Here runs once when page is first rendered. Good place for import statements.\n__doc__= ""\n%>\n<%\n#Python Code here runs every page load\n%>\n<h2>'+basename+'</h2>\n'+'<title>'+basename+'</title>\n\n<div class="sectionbox">\nContent here\n</div>',
                    'no-navheader':True})
                usrpages.updateOnePage(escapedName,root)

        else:
            r = additionalTypes[type].create(module,path,name,kwargs)
            insertResource(r)
            f=additionalTypes[type].onload
            if f:
                f(module,name, r)

        messagebus.postMessage("/system/notifications", "User "+ pages.getAcessingUser() + " added resource " +
                            escapedName + " of type " + type+" to module " + root)
        #Take the user straight to the resource page
        raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module)+'/resource/'+util.url(escapedName))


#show a edit page for a resource. No side effect here so it only requires the view permission
def resourceEditPage(module,resource,version='default',kwargs=None):
    pages.require("/admin/modules.view")

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

        if not 'resource-type' in resourceinquestion:
            logging.warning("No resource type found for "+resource)
            return

        if resourceinquestion['resource-type'] == 'permission':
            return permissionEditPage(module, resource)

        if resourceinquestion['resource-type'] == 'k4dprog_sq':
            if not "preview" in kwargs:
                d = remotedevices.remote_devices.get(resourceinquestion['device'], None)
                p = remotedevices.loadedSquirrelPrograms.get((module,resource),None)
                return pages.get_template("modules/remoteprograms/sqprog.html").render(
                    module =module,
                    name =resource,
                    data =resourceinquestion,
                    device= weakref.proxy(d) if d else None,
                    printout= p.print if p else None,
                    errs= p.errors if p else None
                    )
            d = remotedevices.remote_devices.get(resourceinquestion['device'], None)
            p = remotedevices.loadedSquirrelPrograms.get((module,resource),None)
            return pages.get_template("modules/remoteprograms/sqprogprev.html").render(
                code = p.getPreprocessedCode(kwargs['code'], True if kwargs['preview']=='2' else False),
                module =module,
                name =resource,
                data =resourceinquestion,
                device= weakref.proxy(d) if d else None,
                printout= p.print if p else None,
                errs= p.errors if p else None
                )

                    

        if resourceinquestion['resource-type'] == 'event':
            return pages.get_template("modules/events/event.html").render(
                module =module,
                name =resource,
                event =resourceinquestion,
                version=version)

        if resourceinquestion['resource-type'] == 'internal-fileref':
            return pages.get_template("modules/fileresources/fileresource.html").render(
                module =module,
                resource =resource,
                resourceobj =resourceinquestion)

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

        #This is for the custom resource types interface stuff.
        return additionalTypes[resourceinquestion['resource-type']].editpage(module,resource, resourceinquestion)

def permissionEditPage(module,resource):
    pages.require("/admin/modules.view")
    return pages.get_template("modules/permissions/permission.html").render(module = module,
    permission = resource, description = ActiveModules[module][resource]['description'])





#The actual POST target to modify a resource. Context dependant based on resource type.
def resourceUpdateTarget(module,resource,kwargs):
    pages.require("/admin/modules.edit",noautoreturn=True)
    pages.postOnly()
    modulesHaveChanged()
    unsaved_changed_obj[(module,resource)] = "Resource modified by"+ pages.getAcessingUser()
    with modulesLock:
        t = ActiveModules[module][resource]['resource-type']
        resourceobj = ActiveModules[module][resource]
        if t == 'permission':
            resourceobj['description'] = kwargs['description']
            #has its own lock
            modules_state.createRecoveryEntry(module,resource, resourceobj)
            auth.importPermissionsFromModules() #sync auth's list of permissions
        
        if t=="k4dprog_sq":
            resourceobj['code'] = kwargs['code']
            resourceobj['device'] = kwargs['device']
            resourceobj['prgid'] = kwargs['prgid']
            modules_state.createRecoveryEntry(module,resource, resourceobj)
            remotedevices.updateProgram(module, resource, resourceobj)

        elif t == 'event':
            evt = None
            #Test compile, throw error on fail.

            if 'tabtospace' in kwargs:
                actioncode =  kwargs['action'].replace("\t","    ")
                setupcode =  kwargs['setup'].replace("\t","    ")
            else:
                actioncode =  kwargs['action']
                setupcode =  kwargs['setup']

            if 'enable' in kwargs:
                try:
                    #Make a copy of the old resource object and modify it
                    r2= resourceobj.copy()
                    r2['trigger'] = kwargs['trigger']
                    r2['action'] = actioncode
                    r2['setup'] = setupcode
                    r2['priority'] = kwargs['priority']
                    r2['continual'] = 'continual' in kwargs
                    r2['rate-limit'] = float(kwargs['ratelimit'])
                    r2['enable'] = 'enable' in kwargs

                    #Remove the old event even before we even do a test compile. If we can't do the new version just put the old one back.
                    newevt.removeOneEvent(module,resource)
                    #Leave a delay so that effects of cleanup can fully propagate.
                    time.sleep(0.08)
                    #UMake event from resource, but use our substitute modified dict
                    evt = newevt. make_event_from_resource(module,resource, r2)

                except Exception as e:
                    if not 'versions' in resourceobj:
                        resourceobj['versions'] = {}
                    if 'versions' in r2:
                        r2.pop("versions")

                    resourceobj['versions']['__draft__'] = copy.deepcopy(r2)
                    modules_state.createRecoveryEntry(module,resource, resourceobj)

                    messagebus.postMessage("system/errors/misc/failedeventupdate", "In: "+ module +" "+resource+ "\n"+ traceback.format_exc(4))
                    raise

                #If everything seems fine, then we update the actual resource data
                ActiveModules[module][resource]=r2
                resourceobj = r2
            #Save but don't enable
            else:
                #Make a copy of the old resource object and modify it
                r2= resourceobj.copy()
                r2['trigger'] = kwargs['trigger']
                r2['action'] = actioncode
                r2['setup'] = setupcode
                r2['priority'] = kwargs['priority']
                r2['continual'] = 'continual' in kwargs
                r2['rate-limit'] = float(kwargs['ratelimit'])
                r2['enable'] = 'enable' in kwargs

                #Remove the old event even before we do a test compile. If we can't do the new version just put the old one back.
                newevt.removeOneEvent(module,resource)
                #Leave a delay so that effects of cleanup can fully propagate.
                time.sleep(0.08)

                #If everything seems fine, then we update the actual resource data
                ActiveModules[module][resource]=r2


            #I really need to do something about this possibly brittle bookkeeping system
            #But anyway, when the active modules thing changes we must update the newevt cache thing.


            #Delete the draft if any
            try:
                del resourceobj['versions']['__draft__']
            except:
                pass

            modules_state.createRecoveryEntry(module,resource, resourceobj)

            #if the test compile fails, evt will be None and the function will look up the old one in the modules database
            #And compile that. Otherwise, we avoid having to double-compile.
            newevt.updateOneEvent(resource,module,evt)
            resourceobj = r2

        elif t == 'page':

            if 'tabtospace' in kwargs:
                body =  kwargs['body'].replace("\t","    ")
            else:
                body =  kwargs['body']

            resourceobj['body'] = body
            resourceobj['mimetype'] = kwargs['mimetype']
            resourceobj['template-engine'] = kwargs['template-engine']
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

            modules_state.createRecoveryEntry(module,resource, resourceobj)
            usrpages.updateOnePage(resource,module)

        else:
            modules_state.createRecoveryEntry(module,resource, resourceobj)
            additionalTypes[resourceobj['resource-type']].update(module,resource, kwargs)

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
    x = util.split_escape(r,"/","\\")
    if len(x)>1:
        raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module)+'/resource/'+'/'.join([util.url(i) for i in x[:-1]])+"#resources")
    else:
        raise cherrypy.HTTPRedirect("/modules/module/"+util.url(module)+"#resources")#+'/resource/'+util.url(resource))
