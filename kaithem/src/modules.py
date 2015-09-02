#Copyright Daniel Dunn 2013-2015
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
import threading,urllib,shutil,sys,time,os,json,traceback
import cherrypy,yaml
from . import auth,pages,directories,util,newevt,kaithemobj,usrpages,messagebus,scheduling
from .modules_state import ActiveModules,modulesLock,scopes


#2.x vs 3.x once again have renamed stuff
if sys.version_info < (3,0):
   from StringIO import StringIO
else:
    from io import BytesIO as StringIO

import zipfile

from .util import url,unurl

#This must be set to true by anything that changes the modules
#it's o the code knows to save everything is it has been changed.
moduleschanged = False

class event_interface(object):
   def __init__(self, ):
      self.type = "event"

class page_inteface(object):
   def __init__(self, ):
      self.type = "page"

class permission_inteface(object):
   def __init__(self, ):
      self.type = "permission"

class obj(object):
   def __getitem__(self,x):
      x= ActiveModules[self.__kaithem_modulename__][x]
      if x['resource-type'] == 'page':
         x = page_interface()
      if x['resource-type'] == 'event':
         x = event_interface()
      if x['resource-type'] == 'permission':
         x = permission_interface()

def saveAll():
    """saveAll and loadall are the ones outside code shold use to save and load the state of what modules are loaded.
    This function creates a timestamp directory in the confugured modules dir, then saves the modules to it, and deletes the old ones."""
    
    #This is an RLock, and we need to use the lock so that someone else doesn't make a change while we are saving that isn't caught by
    #moduleschanged.
    with modulesLock:
        global moduleschanged
        if not moduleschanged:
            return False
        if time.time()> util.min_time:
            t = time.time()
        else:
            t = int(util.min_time) +1.234
        #This dumps the contents of the active modules in ram to a subfolder of the moduledir named after the current unix time"""
        saveModules(os.path.join(directories.moduledir,str(t) ))
        #We only want 1 backup(for now at least) so clean up old ones.
        util.deleteAllButHighestNumberedNDirectories(directories.moduledir,2)
        moduleschanged = False
        return True

def initModules():
    """"Find the most recent module dump folder and use that. Should there not be a module dump folder, it is corrupted, etc,
    Then start with an empty list of modules. Should normally be called once at startup."""
    try:
        for i in range(0,15):
            #Gets the highest numbered of all directories that are named after floating point values(i.e. most recent timestamp)
            name = util.getHighestNumberedTimeDirectory(directories.moduledir)
            possibledir = os.path.join(directories.moduledir,name)

            #__COMPLETE__ is a special file we write to the dump directory to show it as valid
            if '''__COMPLETE__''' in util.get_files(possibledir):
                loadModules(possibledir)
                auth.importPermissionsFromModules()
                newevt.getEventsFromModules()
                usrpages.getPagesFromModules()
                break #We sucessfully found the latest good ActiveModules dump! so we break the loop
            else:
                #If there was no flag indicating that this was an actual complete dump as opposed
                #To an interruption, rename it and try again
                shutil.copytree(possibledir,os.path.join(directories.moduledir,name+"INCOMPLETE"))
                shutil.rmtree(possibledir)
    except:
        pass


def saveModules(where):
    """Save the modules in a directory as JSON files. Low level and does not handle the timestamp directories, etc."""
    with modulesLock:
        util.ensure_dir2(os.path.join(where))
        util.chmod_private_try(os.path.join(where))
        for i in ActiveModules:
            #Iterate over all of the resources in a module and save them as json files
            #under the URL urld module name for the filename.
            for resource in ActiveModules[i]:
                #Make sure there is a directory at where/module/
                util.ensure_dir(os.path.join(where,url(i),url(resource))  )
                util.chmod_private_try(os.path.join(where,url(i)))
                #Open a file at /where/module/resource
                with  open(os.path.join(where,url(i),url(resource)),"w") as f:
                    util.chmod_private_try(os.path.join(where,url(i),url(resource)))
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
            util.chmod_private_try(os.path.join(where,'__COMPLETE__'))
            f.write("By this string of contents quite arbitrary, I hereby mark this dump as consistant!!!")


def loadModules(modulesdir):
    "Load all modules in the given folder to RAM"
    for i in util.get_immediate_subdirectories(modulesdir):
        loadModule(i,modulesdir)


def loadModule(moduledir,path_to_module_folder):
    "Load a single module but don't bookkeep it . Used by loadModules"
    with modulesLock:
        #Make an empty dict to hold the module resources
        module = {}
        #Iterate over all resource files and load them
        for i in util.get_files(os.path.join(path_to_module_folder,moduledir)):
            try:
                f = open(os.path.join(path_to_module_folder,moduledir,i))
                #Load the resource and add it to the dict. Resouce names are urlencodes in filenames.
                module[unurl(i)] = yaml.load(f)
            finally:
                f.close()

        name = unurl(moduledir)
        scopes[name] = obj()
        ActiveModules[name] = module
        messagebus.postMessage("/system/modules/loaded",name)
        #bookkeeponemodule(name)

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
    auth.importPermissionsFromModules()

    z.close()

def bookkeeponemodule(module,update=False):
    """Given the name of one module that has been copied to activemodules but nothing else,
    let the rest of the system know the module is there."""
    scopes[module] = obj()
    for i in ActiveModules[module]:
        if ActiveModules[module][i]['resource-type'] == 'page':
            try:
                usrpages.updateOnePage(i,module)
            except Exception as e:
                usrpages.makeDummyPage(i,module)
                messagebus.postMessage("/system/notifications/errors","Failed to load page resource: " + i +" module: " + module + "\n" +str(e)+"\n"+"please edit and reload.")

    newevt.getEventsFromModules([module])
    if not update:
        messagebus.postMessage("/system/modules/loaded",module)




#The class defining the interface to allow the user to perform generic create/delete/upload functionality.
class WebInterface():

    @cherrypy.expose
    def nextrun(self,**kwargs):
        pages.require('/admin/modules.view')

        return str(scheduling.get_next_run(kwargs['string']))


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
        global moduleschanged
        moduleschanged = True
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
        global moduleschanged
        moduleschanged = True
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
        global moduleschanged
        moduleschanged = True
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
        global moduleschanged
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
                moduleschanged = True
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
                moduleschanged = True
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
    global moduleschanged
    moduleschanged = True

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
    global moduleschanged
    moduleschanged = True
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
                ev = newevt.Event(kwargs['trigger'],kwargs['action'],newevt.make_eventscope(module),setup=kwargs['setup'],m=module,r=resource)
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

def mvResource(module,resource,toModule,toResource):
    #Raise an error if the user ever tries to move something somewhere that does not exist.
    new = util.split_escape(toResource,"/", "\\",True)
    if not ('/'.join(new[:-1]) in ActiveModules[toModule] or len(new)<2):
        raise cherrypy.HTTPRedirect("/errors/nofoldermoveerror")
    if not toModule in ActiveModules:
        raise cherrypy.HTTPRedirect("/errors/nofoldermoveerror")
    #If something by the name of the directory we are moving to exists but it is not a directory.
    #short circuit evaluating the len makes this clause ignore moves that are to the root of a module.
    if not (len(new)<2 or ActiveModules[toModule]['/'.join(new[:-1])]['resource-type']=='directory'):
        raise cherrypy.HTTPRedirect("/errors/nofoldermoveerror")


    if ActiveModules[module][resource]['resource-type'] == 'event':
        ActiveModules[toModule][toResource] = ActiveModules[module][resource]
        del ActiveModules[module][resource]
        newevt.renameEvent(module,resource,toModule,toResource)
        return

    if ActiveModules[module][resource]['resource-type'] == 'page':
        ActiveModules[toModule][toResource] = ActiveModules[module][resource]
        del ActiveModules[module][resource]
        usrpages.removeOnePage(module,resource)
        usrpages.updateOnePage(toResource,toModule)
        return


class KaithemEvent(dict):
    pass
