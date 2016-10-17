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
import threading,urllib,shutil,sys,time,os,json,traceback,copy,hashlib,logging,uuid, gc
import cherrypy,yaml
from . import auth,pages,directories,util,newevt,kaithemobj,usrpages,messagebus,scheduling,modules_state,registry
from .modules_state import ActiveModules,modulesLock,scopes,additionalTypes,fileResourceAbsPaths


def new_empty_module():
    return {"__description":
                {"resource-type":"module-description",
                "text":"Module info here"}}

def new_module_container():
    return {}

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
unsaved_changed_obj = {}

#This lets us have some modules saved outside the var dir.
external_module_locations = {}

moduleshash= "000000000000000000000000"
modulehashes = {}

def hashModules():
    m=hashlib.md5()
    with modulesLock:
        for i in sorted(ActiveModules.keys()):
            m.update(i.encode('utf-8'))
            for j in sorted(ActiveModules[i].keys()):
                m.update(j.encode('utf-8'))
                m.update(json.dumps(ActiveModules[i][j],sort_keys=True,separators=(',',':')).encode('utf-8'))
    return m.hexdigest().upper()

def hashModule(module):
    m=hashlib.md5()
    with modulesLock:
        m.update(json.dumps(ActiveModules[module],sort_keys=True,separators=(',',':')).encode('utf-8'))
    return m.hexdigest()

def getModuleHash(m):
    if not m in modulehashes:
        modulehashes[m] = hashModule(m)
    return modulehashes[m].upper()

def modulesHaveChanged():
    global moduleschanged,moduleshash, modulehashes
    moduleschanged = True
    moduleshash = hashModules()
    modulehashes = {}
    modules_state.ls_folder.invalidate_cache()

class ResourceObject(dict):
    def __init__(self, m,r,o):
        self.resource =r
        self.module = m
        dict.__init__(self,o)

    def getData():
        return copy.deepcopy(self)

class Event(ResourceObject):
    resourceType = "event"

class Page(ResourceObject):
    resourceType = "page"

class Permission(ResourceObject):
    resourceType = "permission"

class InternalFileRef(ResourceObject):
    resourceType = 'internal-fileref'

    def getPath(self):
        "Return the actual path on the filesystem of things"
        return fileResourceAbsPaths[self.module, self.resource]

class ModuleObject(object):
    """
    These are the objects acessible as 'module' within pages, events, etc.
    Normally you use them to share variables, but they have incomplete and undocumented support
    For acting as an API for user code to acess or modify the resources, which could be useful if you want to be able to
    dynamically create resources, or more likely just acess file resource contents or metadata about the module.
    """
    def __init__(self,modulename):
        self.__kaithem_modulename__ = modulename

    def __getitem__(self,name):
        "When someone acesses a key, return an interface to that module."
        x= ActiveModules[self.__kaithem_modulename__][name]
        module= self.__kaithem_modulename__

        resourcetype = x['resource-type']

        if resourcetype == 'page':
            x = Page(module,name,x)

        elif resourcetype == 'event':
            x = Event(module,name,x)

        elif resourcetype == 'permission':
            x = Permission(module,name,x)

        elif resourcetype == 'internal-fileref':
            x = InternalFileRef(module,name,x)

        return x

        raise KeyError(name)
    def __setitem__(self,name, value):
        "When someone sets an item, validate it, then do any required bookkeeping"

        #Raise an exception on anything non-serializable or without a resource-type,
        #As those could break something.
        json.dumps({name:value})

        if not 'resource-type' in value:
            raise ValueError("Supplied dict has no resource-type")


        with modulesLock:
            resourcetype= value['resource-type']
            module = self.__kaithem_modulename__

            unsaved_changed_obj[(module,name)] = "User code inserted or modified module"
            #Insert the new item into the global modules thing
            ActiveModules[module][name]=value
            modulesHaveChanged()

            #Make sure we recognize the resource-type, or else we can't load it.
            if (not resourcetype in ['event','page','permission','directory']) and (not resourcetype in additionalTypes):
                raise ValueError("Unknown resource-type")

            #Do the type-specific init action
            if resourcetype == 'event':
                e = newevt.make_event_from_resource(module,name)
                newevt.updateOneEvent(module,name,e)

            elif resourcetype == 'page':
                #Yes, module and resource really are backwards, and no, it wasn't a good idea to do that.
                usrpages.updateOnePage(name,module)

            elif resourcetype == 'permission':
                auth.importPermissionsFromModules()

            else:
                additionalTypes[resourcetype].onload(module,name, value)




#Backwards compatible resource loader.
def loadResource(fn):
    try:
        with open(fn) as f:
            d = f.read()

        #This is a workaround for when dolphin puts .directory files in directories and gitignore files
        #and things like that.
        #I'd like to add more workarounds if there are other programs that insert similar crap files.
        if not "resource-type" in d:
            if "/.git" in fn or "/.gitignore" in fn or fn.endswith(".directory"):
                return None

        if "\r---\r" in d:
                f = d.split("\r---\r")
        elif "\r\n\---\r\n" in d:
                f = d.split("\r\n---\r\n")
        else:
            f = d.split("\n---\n")
        r = yaml.load(f[0])

        #Catch new style save files
        if len(f)>1:
            if r['resource-type'] == 'page':
                r['body'] = f[1]

            if r['resource-type'] == 'event':
                r['setup'] = f[1]
                r['action'] = f[2]
        return r
    except:
        print(fn)
        logging.exception("Error loading resource from file "+fn)
        raise

def saveResource2(r,fn):
    r = copy.deepcopy(r)
    if r['resource-type'] == 'page':
        b = r['body']
        del r['body']
        d = yaml.dump(r) + "\n#End YAML metadata, page body mako code begins on first line after ---\n---\n" + b

    elif r['resource-type'] == 'event':
        t = r['setup']
        del r['setup']
        a = r['action']
        del r['action']
        d = yaml.dump(r) + "\n#End metadata. Format: metadata, setup, action, delimited by --- on it's own line.\n---\n" + t + "\n---\n" + a

    else:
        d = yaml.dump(r)

    with open(fn,"w") as f:
        util.chmod_private_try(fn,execute = False)
        f.write(d)


def saveResource(r,fn):
    with open(fn,"w") as f:
        util.chmod_private_try(fn, execute=False)
        f.write(yaml.dump(r))

def cleanupBlobs():
    fddir = os.path.join(directories.vardir,"modules","filedata")
    inUseFiles = [os.path.basename(i) for i in fileResourceAbsPaths.values()]
    for i in os.listdir( fddir):
        if not i in inUseFiles:
            fn = os.path.join(fddir,i )
            os.remove(fn)

def saveAll():
    """saveAll and loadall are the ones outside code shold use to save and load the state of what modules are loaded.
    This function writes to data after backing up to a timestamp dir and deleting old timestamp dirs"""

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

        if os.path.isdir(os.path.join(directories.moduledir,str("data"))):
        #Copy the data found in data to a new directory named after the current time. Don't copy completion marker
            shutil.copytree(os.path.join(directories.moduledir,str("data")), os.path.join(directories.moduledir,str(t)),
                            ignore=shutil.ignore_patterns("__COMPLETE__"))
            #Add completion marker at the end
            with open(os.path.join(directories.moduledir,str(t),'__COMPLETE__'),"w") as x:
                util.chmod_private_try(os.path.join(directories.moduledir,str(t),'__COMPLETE__'), execute=False)
                x.write("This file certifies this folder as valid")

        #This dumps the contents of the active modules in ram to a directory named data"""
        saveModules(os.path.join(directories.moduledir,"data"))
        #We only want 1 backup(for now at least) so clean up old ones.
        util.deleteAllButHighestNumberedNDirectories(directories.moduledir,2)
        cleanupBlobs()
        moduleschanged = False
        return True

def initModules():
    global moduleshash, external_module_locations
    """"Find the most recent module dump folder and use that. Should there not be a module dump folder, it is corrupted, etc,
    Then start with an empty list of modules. Should normally be called once at startup."""


    if not os.path.isdir(directories.moduledir):
        return
    if not util.get_immediate_subdirectories(directories.moduledir):
        return
    try:
        #__COMPLETE__ is a special file we write to the dump directory to show it as valid
        possibledir= os.path.join(directories.moduledir,"data")
        if os.path.isdir(possibledir) and '''__COMPLETE__''' in util.get_files(possibledir):
            loadModules(possibledir)
            #we found the latest good ActiveModules dump! so we break the loop
        else:
            messagebus.postMessage("/system/notifications/errors" ,"Modules folder appears corrupted, falling back to latest backup version")
            for i in range(0,15):
                #Gets the highest numbered of all directories that are named after floating point values(i.e. most recent timestamp)
                name = util.getHighestNumberedTimeDirectory(directories.moduledir,i)
                possibledir = os.path.join(directories.moduledir,name)

                if '''__COMPLETE__''' in util.get_files(possibledir):
                    loadModules(possibledir)
                #we found the latest good ActiveModules dump! so we break the loop
                    break
                else:
                    #If there was no flag indicating that this was an actual complete dump as opposed
                    #To an interruption, rename it and try again
                    try:
                        shutil.copytree(possibledir,os.path.join(directories.moduledir,name+"INCOMPLETE"))
                        #It would be best if we didn't rename or get rid of the data directory because that's where
                        #manual tools might be working.
                        if not possibledir == os.path.join(directories.moduledir,"data"):
                            shutil.rmtree(possibledir)
                    except:
                        logging.exception("Failed to rename corrupted data. This is normal if kaithem's var dir is not currently writable.")

    except:
        messagebus.postMessage("/system/notifications/errors" ," Error loading modules: "+ traceback.format_exc(4))

    auth.importPermissionsFromModules()
    newevt.getEventsFromModules()
    usrpages.getPagesFromModules()
    moduleshash = hashModules()
    try:
        cleanupBlobs()
    except:
        logging.exception("Failed to cleanup old blobs. This is normal if kaithem's var dir is not currently writable.")

def saveModule(module, dir,modulename=None):
    "Returns a list of saved module,resource tuples and the saved resource."
    #Iterate over all of the resources in a module and save them as json files
    #under the URL url module name for the filename.
    saved = []
    try:
        #Make sure there is a directory at where/module/
        util.ensure_dir2(os.path.join(dir))
        util.chmod_private_try(dir)
        for resource in module:
            #Open a file at /where/module/resource
            fn = os.path.join(dir,url(resource))
            #Make a json file there and prettyprint it
            r = module[resource]

            #Allow non-saved virtual resources
            if not hasattr(r,"ephemeral") or r.ephemeral==False:
                saveResource2(r,fn)

            saved.append((modulename,resource))

            if r['resource-type'] == "internal-fileref":
                #Handle two separate ways of handling these file resources.
                #One is to store them directly in the module data in a special folder.
                #That's what we do if we are using an external folder
                #For internal folders we don't want to store duplicate copies in the dumps,
                #So we store them in one big folder that is shared between all loaded modules.
                #Which is not exactly ideal, but all the per-module stuff is stored in dumps.

                #Basically, we want to always copy the current "loaded" version over.
                #But actually we don't need to copy, we can do a move.
                currentFileLocation = fileResourceAbsPaths[modulename,resource]
                if util.in_directory(fn, directories.vardir):
                    newpath = os.path.join(directories.vardir,"modules","filedata",r['target'])
                    util.ensure_dir(newpath)
                    util.fakeUnixRename(currentFileLocation,newpath)
                    fileResourceAbsPaths[modulename,resource] = newpath
                else:
                    newpath = os.path.join(moduledir,"__filedata__",r['target'])
                    util.ensure_dir(newpath)
                    util.fakeUnixRename(currentFileLocation,newpath)
                    fileResourceAbsPaths[modulename,resource] = newpath

        #Now we iterate over the existing resource files in the filesystem and delete those that correspond to
        #resources that have been deleted in the ActiveModules workspace thing.
        #If there were no resources in module, and we never made a dir, don't do anything.
        if os.path.isdir(dir):
            for j in util.get_files(dir):
                if unurl(j) not in module:
                    os.remove(os.path.join(dir,j))
                    #Remove them from the list of unsaved changed things.
                    if (modulename,unurl(j)) in unsaved_changed_obj:
                        saved.append((modulename,unurl(j)))
        saved.append(modulename)
        return saved
    except:
        raise

def saveModules(where):
    """Save the modules in a directory as JSON files. Low level and does not handle the timestamp directories, etc."""
    global unsaved_changed_obj
    #List to keep track of saved modules and resources
    saved = []
    with modulesLock:
        xxx = unsaved_changed_obj.copy()
        try:
            util.ensure_dir2(os.path.join(where))
            util.chmod_private_try(os.path.join(where))
            #If there is a complete marker, remove it before we get started. This marks
            #things as incomplete and then when loading it will use the old version
            #when done saving we put the complete marker back.
            if os.path.isfile(os.path.join(where,'__COMPLETE__')):
                os.remove(os.path.join(where,'__COMPLETE__'))

            #do the saving
            for i in [i for i in ActiveModules if not i in external_module_locations]:
                saved.extend(saveModule(ActiveModules[i],os.path.join(where,url(i)),modulename=i))

            for i in external_module_locations:
                try:
                    saved.extend(saveModule(ActiveModules[i],external_module_locations[i],modulename=i))
                except:
                    messagebus.postMessage("/system/notifications/errors",'Failed to save external module:' + traceback.format_exc(8))

            for i in util.get_immediate_subdirectories(where):
                #Look in the modules directory, and if the module folder is not in ActiveModules\
                #We assume the user deleted the module so we should delete the save file for it.
                #Note that we URL url file names for the module filenames and foldernames.

                #We also delete things that are in the "external_module_locations" because they have been moved there. Unless it happens to point here!
                if unurl(i) not in ActiveModules or (((unurl(i) in external_module_locations)  and not external_module_locations[unurl(i)]==os.path.join(where,i))):
                    shutil.rmtree(os.path.join(where,i))
                    saved.append(unurl(i))

            #Delete the .location pointer files to modules that have been deleted from ActiveModules
            for i in util.get_files(where):
                if i.endswith(".location") and not i[:-9] in ActiveModules:
                    os.remove(os.path.join(where,i))

            for i in external_module_locations:
                if not os.path.isfile(os.path.join(where, "__"+url(i)+".location")):
                    with open(os.path.join(where, "__"+url(i)+".location"),"w+") as f:
                        if not f.read() == external_module_locations[i]:
                            f.seek(0)
                            f.write(external_module_locations[i])


            #This is kind of a hack to deal with deleted external modules
            for i in xxx:
                if isinstance(i,str):
                    saved.append(i)

            with open(os.path.join(where,'__COMPLETE__'),'w') as f:
                util.chmod_private_try(os.path.join(where,'__COMPLETE__'), execute=False)
                f.write("By this string of contents quite arbitrary, I hereby mark this dump as consistant!!!")


            #mark things that get created and deleted before ever saving so they don't persist in the unsaved list
            for i in unsaved_changed_obj:
                if isinstance(i,tuple) and len(i)>1 and (not i[0]  in ActiveModules) or (not i[1] in ActiveModules[i[0]]):
                    saved.append(i)

            #Now that we know the dump is actually valid, we remove those entries from the unsaved list for real
            for i in saved:
                if i in unsaved_changed_obj:
                    del unsaved_changed_obj[i]

        except:
            raise


def loadModules(modulesdir):
    "Load all modules in the given folder to RAM"
    for i in util.get_immediate_subdirectories(modulesdir):
        loadModule(os.path.join(modulesdir,i), i)

    for i in os.listdir(modulesdir):
        try:
            if not i.endswith(".location"):
                continue
            if not os.path.isfile(os.path.join(modulesdir,i)):
                continue
            #Read ythe location we are supposed to load from
            with open(os.path.join(modulesdir,i)) as f:
                s = f.read(1024)
            #Get rid of the __ and .location, then set the location in the dict
            external_module_locations[i[2:-9]] = s
            loadModule(s, i[2:-9])
        except:
            messagebus.postMessage("/system/notifications/errors" ," Error loading external module: "+ traceback.format_exc(4))

def loadModule(folder, modulename):
    "Load a single module but don't bookkeep it . Used by loadModules"
    with modulesLock:
        #Make an empty dict to hold the module resources
        module = {}
        #Iterate over all resource files and load them
        for root, dirs, files in os.walk(folder):
                for i in files:
                    relfn = os.path.relpath(os.path.join(root,i),folder)
                    fn = os.path.join(folder , relfn)
                    #Copy stuff from anything called filedata to handle library modules with filedata
                    if os.path.basename(root) == "__filedata__":
                        shutil.copy(fn, os.path.join(directories.vardir,"modules","filedata"))
                        continue
                    #Load the resource and add it to the dict. Resouce names are urlencodes in filenames.
                    resourcename = unurl(relfn)
                    r = loadResource(fn)
                    if not r:
                        continue
                    module[resourcename] = r
                    if not 'resource-type' in r:
                        logging.warning("No resource type found for "+resourcename)
                        continue
                    if r['resource-type'] == "internal-fileref":
                        #Handle two separate ways of handling these file resources.
                        #One is to store them directly in the module data in a special folder.
                        #That's what we do if we are using an external folder
                        #For internal folders we don't want to store duplicate copies in the dumps,
                        #So we store them in one big folder that is shared between all loaded modules.
                        #Which is not exactly ideal, but all the per-module stuff is stored in dumps.

                        #Note that we handle things in library modules the same as in loaded vardir modules,
                        #Because things in vardir modules get copied to the vardir.
                        if util.in_directory(fn, directories.vardir) or util.in_directory(fn, directories.datadir) :
                            fileResourceAbsPaths[modulename,resourcename] = os.path.join(directories.vardir,"modules","filedata",r['target'])
                        else:
                            fileResourceAbsPaths[modulename,resourcename] = os.path.join(folder,"filedata",r['target'])

                for i in dirs:
                    if i == "__filedata__":
                        continue
                    relfn = os.path.relpath(os.path.join(root,i),folder)
                    fn = os.path.join(folder , relfn)
                    #Load the resource and add it to the dict. Resouce names are urlencodes in filenames.
                    module[unurl(relfn)] = {"resource-type":"directory"}


        scopes[modulename] = ModuleObject(modulename)
        ActiveModules[modulename] = module
        messagebus.postMessage("/system/modules/loaded",modulename)
        #bookkeeponemodule(name)

def getModuleAsZip(module,noFiles=True):
    with modulesLock:
        #We use a stringIO so we can avoid using a real file.
        ram_file = StringIO()
        z = zipfile.ZipFile(ram_file,'w')
        #Dump each resource to JSON in the ZIP
        for resource in ActiveModules[module]:
            #AFAIK Zip files fake the directories with naming conventions
            s = json.dumps(ActiveModules[module][resource],sort_keys=True,indent=4, separators=(',', ': '))
            z.writestr(url(module)+'/'+url(resource)+".json",s)
            if ActiveModules[module][resource]['resource-type'] == "internal-fileref":
                if noFiles:
                    raise RuntimeError("Cannot download this module without admin rights as it contains embedded files")
                z.write(os.path.join(directories.vardir,"modules","filedata",ActiveModules[module][resource]['target']),"__filedata__/"+url(ActiveModules[module][resource]['target']))


        z.close()
        s = ram_file.getvalue()
        ram_file.close()
        return s

def getModuleAsYamlZip(module,noFiles=True):
    with modulesLock:
        #We use a stringIO so we can avoid using a real file.
        ram_file = StringIO()
        z = zipfile.ZipFile(ram_file,'w')
        #Dump each resource to JSON in the ZIP
        for resource in ActiveModules[module]:
            #AFAIK Zip files fake the directories with naming conventions
            s = yaml.dump(ActiveModules[module][resource])
            z.writestr(url(module)+'/'+url(resource)+".yaml",s)
            if ActiveModules[module][resource]['resource-type'] == "internal-fileref":
                if noFiles:
                    raise RuntimeError("Cannot download this module without admin rights as it contains embedded files")
                z.write(os.path.join(directories.vardir,"modules","filedata",ActiveModules[module][resource]['target']),"__filedata__/"+url(ActiveModules[module][resource]['target']))
        z.close()
        s = ram_file.getvalue()
        ram_file.close()
        return s

def load_modules_from_zip(f,replace=False):
    "Given a zip file, import all modules found therin."
    new_modules = {}
    z = zipfile.ZipFile(f)
    newfrpaths = {}
    for i in z.namelist():
        #get just the folder, ie the module
        p = unurl(i.split('/')[0])
        #Remove the.json by getting rid of last 5 chars
        n = unurl((i.split('/'))[1][:-5])
        if p not in new_modules and not "__filedata__" in p:
            new_modules[p] = {}

        if not  "__filedata__" in p:
            f = z.open(i)
            r = yaml.load(f.read().decode())
            new_modules[p][n] = r
            if r['resource-type'] == "internal-fileref":
                newfrpaths[p,n] = os.path.join(directories.vardir,"modules","filedata",r['target'])

            f.close()
        else:
            inputfile = z.open(i)
            folder = os.path.join(directories.vardir,"modules","filedata")
            util.ensure_dir2(folder)
            data_basename = unurl(i.split('/')[1])
            dataname = os.path.join(folder,data_basename)

            total = 0
            with open(dataname,"wb") as f:
                while True:
                    d = inputfile.read(8192)
                    total += len(d)
                    if total> 8*1024*1024*1024:
                        raise RuntimeError("Cannot upload resource file bigger than 8GB")
                    if not d:
                        break
                    f.write(d)
            inputfile.close()
            print(p,n)
            newfrpaths[p,n] = dataname


    with modulesLock:
        backup = {}
        #Precheck if anything is being overwritten
        replaced_count=0
        for i in new_modules:
            if i in ActiveModules:
                if not replace:
                    raise cherrypy.HTTPRedirect("/errors/alreadyexists")
                replaced_count+=1

        for i in new_modules:
            if i in ActiveModules:
                backup[i]=ActiveModules[i].copy()
                rmModule(i,"Module Deleted by " + pages.getAcessingUser())

                messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " Deleted old module " + i+" for auto upgrade")
                messagebus.postMessage("/system/modules/unloaded",i)
                messagebus.postMessage("/system/modules/deleted",{'user':pages.getAcessingUser()})

            try:
                for i in new_modules:
                    ActiveModules[i] = new_modules[i]
                    messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " uploaded module" + i + " from a zip file")
                    bookkeeponemodule(i)
            except:
                for i in new_modules:
                    if i in backup:
                        ActiveModules[i] = backup[i]
                        messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " uploaded module" + i + " from a zip file, but initializing failed. Reverting to old version.")
                        bookkeeponemodule(i)
                raise
        fileResourceAbsPaths.update(newfrpaths)

    z.close()
    return new_modules.keys()

def bookkeeponemodule(module,update=False):
    """Given the name of one module that has been copied to activemodules but nothing else,
    let the rest of the system know the module is there."""
    if not module in scopes:
        scopes[module] = ModuleObject(module)
    for i in ActiveModules[module]:
        if ActiveModules[module][i]['resource-type'] == 'page':
            try:
                usrpages.updateOnePage(i,module)
            except Exception as e:
                usrpages.makeDummyPage(i,module)
                messagebus.postMessage("/system/notifications/errors","Failed to load page resource: " + i +" module: " + module + "\n" +str(e)+"\n"+"please edit and reload.")

    newevt.getEventsFromModules([module])
    auth.importPermissionsFromModules()
    if not update:
        messagebus.postMessage("/system/modules/loaded",module)


def mvResource(module,resource,toModule,toResource):
    #Raise an error if the user ever tries to move something somewhere that does not exist.
    new = util.split_escape(toResource,"/", "\\",True)
    if not ('/'.join(new[:-1]) in ActiveModules[toModule] or len(new)<2):
        raise cherrypy.HTTPRedirect("/errors/nofoldeday1veerror")
    if not toModule in ActiveModules:
        raise cherrypy.HTTPRedirect("/errors/nofoldermoveerror")
    #If something by the name of the directory we are moving to exists but it is not a directory.
    #short circuit evaluating the len makes this clause ignore moves that are to the root of a module.
    if not (len(new)<2 or ActiveModules[toModule]['/'.join(new[:-1])]['resource-type']=='directory'):
        raise cherrypy.HTTPRedirect("/errors/nofoldermoveerror")

    if ActiveModules[module][resource]['resource-type'] == 'internal-fileref':
            ActiveModules[toModule][toResource] = ActiveModules[module][resource]
            del ActiveModules[module][resource]
            fileResourceAbsPaths[toModule,toResource] = fileResourceAbsPaths[module,resource]
            del fileResourceAbsPaths[module,resource]
            return

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

def rmResource(module,resource,message="Resource Deleted"):
    "Delete one resource by name, message is an optional message explaining the change"
    modulesHaveChanged()
    unsaved_changed_obj[(module,resource)] = message

    with modulesLock:
       r = ActiveModules[module].pop(resource)
    try:
        if r['resource-type'] == 'page':
            usrpages.removeOnePage(module,resource)

        elif r['resource-type'] == 'event':
            newevt.removeOneEvent(module,resource)

        elif r['resource-type'] == 'permission':
            auth.importPermissionsFromModules() #sync auth's list of permissions

            #Don't actually delete the file on disk here, because doing stuff on disk should be atomic.
            #We let the blobs cleanup take care of that instead.
        elif r['resource-type'] == 'internal-fileref':
            del fileResourceAbsPaths[module,resource]

        else:
            additionalTypes[r['resource-type']].ondelete(module,resource,r)
    except:
           messagebus.postMessage("/system/modules/errors/unloading","Error deleting resource: "+str((module,resource)))

def newModule(name,location=None):
    "Create a new module by the supplied name, throwing an error if one already exists. If location exists, load from there."
    modulesHaveChanged()
    #Lets do this outside of modules lock just to be safe
    if location:
        with registry.reglock:
            external_module_locations[name]= os.path.expanduser(location)

    #If there is no module by that name, create a blank template and the scope obj
    with modulesLock:
        if name in ActiveModules:
            raise RuntimeError("A module by that name already exists.")
        if location:
            if os.path.isfile(location):
                raise RuntimeError('Cannot create new module that would clobber existing file')

            if os.path.isdir(location):
                loadModule(location,name)
            else:
                ActiveModules[name] = {"__description":
                {"resource-type":"module-description",
                "text":"Module info here"}}
        else:
            ActiveModules[name] = {"__description":
            {"resource-type":"module-description",
            "text":"Module info here"}}

        bookkeeponemodule(name)
        #Go directly to the newly created module
        messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " Created Module " + name)
        messagebus.postMessage("/system/modules/new",{'user':pages.getAcessingUser(), 'module':name})




def rmModule(module,message="deleted"):
    modulesHaveChanged()
    unsaved_changed_obj[module]=message
    with modulesLock:
       j = copy.deepcopy(ActiveModules.pop(module))
       scopes.pop(module)

    #Delete any custom resource types hanging around.
    for k in j:
        if j.get('resource-type',None) in additionalTypes:
            try:
               additionalTypes[j['resource-type']].ondelete(i,k,j[k])
            except:
               messagebus.postMessage("/system/modules/errors/unloading","Error deleting resource: "+str(i,k))
    #Get rid of any lingering cached events
    newevt.removeModuleEvents(module)
    #Get rid of any permissions defined in the modules.
    auth.importPermissionsFromModules()
    usrpages.removeModulePages(module)

    if module in external_module_locations:
        del external_module_locations[module]
    #Get rid of any garbage cycles associated with the event.
    gc.collect()
    messagebus.postMessage("/system/modules/unloaded",module)
    messagebus.postMessage("/system/modules/deleted",{'user':pages.getAcessingUser()})

class KaithemEvent(dict):
    pass
