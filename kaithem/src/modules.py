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
import threading,urllib,shutil,sys,time,os,json,traceback,copy,hashlib,logging,uuid, gc,re,weakref,sqlite3
import cherrypy,yaml
from . import auth,pages,directories,util,newevt,kaithemobj,usrpages,messagebus,scheduling,modules_state,registry,remotedevices
from .modules_state import ActiveModules,modulesLock,scopes,additionalTypes,fileResourceAbsPaths
from .virtualresource import VirtualResource, VirtualResourceInterface


logger = logging.getLogger("system")


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
    from typing import Optional, Tuple

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
modulewordhashes = {}


def hashModules():
    """For some unknown lagacy reason, the hash of the entire module state is different from the hash of individual modules 
        hashed together
    """
    try:
        m=hashlib.md5()
        with modulesLock:
            for i in sorted(ActiveModules.keys()):
                m.update(i.encode('utf-8'))
                for j in sorted(ActiveModules[i].keys()):
                    if isinstance(ActiveModules[i][j],weakref.ref):
                        continue
                    m.update(j.encode('utf-8'))
                    m.update(json.dumps(ActiveModules[i][j],sort_keys=True,separators=(',',':')).encode('utf-8'))
        return m.hexdigest().upper()
    except:
        logger.exception("Could not hash modules")
        return("ERRORHASHINGMODULES")

def hashModule(module: str):
    try:
        m=hashlib.md5()
        with modulesLock:
            m.update(json.dumps({i:ActiveModules[module][i] for i in ActiveModules[module] if not isinstance(ActiveModules[module][i],weakref.ref)} ,sort_keys=True,separators=(',',':')).encode('utf-8'))
        return m.hexdigest()
    except:
        logger.exception("Could not hash module")
        return("ERRORHASHINGMODULE")

def wordHashModule(module: str):
    try:
        m=hashlib.blake2b()
        with modulesLock:
            return util.blakeMemorable(json.dumps({i:ActiveModules[module][i] for i in ActiveModules[module] if not isinstance(ActiveModules[module][i],weakref.ref)} ,sort_keys=True,separators=(',',':')).encode('utf-8'), num=12,separator=" ")
    except:
        logger.exception("Could not hash module")
        return("ERRORHASHINGMODULE")

def getModuleHash(m: str):
    if not m in modulewordhashes:
        modulehashes[m] = hashModule(m)
    return modulehashes[m].upper()


def getModuleWordHash(m: str):
    if not m in modulewordhashes:
        modulehashes[m] = wordHashModule(m)
    return modulehashes[m].upper()


def modulesHaveChanged():
    global moduleschanged,moduleshash, modulehashes
    moduleschanged = True
    moduleshash = hashModules()
    modulehashes = {}
    modulewordhashes = {}
    modules_state.ls_folder.invalidate_cache()

class ResourceObject():
    def __init__(self, m:str=None,r:str=None,o=None):
        self.resource =r
        self.module = m
        self._object = o

class EventAPI(ResourceObject):
    resourceType = "event"

    def __init__(self, m,r,o):
        ResourceObject.__init__(self,m,r,o)


    def run(self):
        newevt.EventReferences[self.module,self.resource].manualRun()

    @property
    def scope(self):
        return newevt.EventReferences[self.module,self.resource].pymodule
    
    @property
    def data(self):
        return newevt.EventReferences[self.module,self.resource].data

    #Allow people to start and stop events at runtime.
    #Some events support a separate new pause/unpause api, otherwise use register
    #and unregister. It might not be safe to re-register events that
    #have a pause api.

    def start(self):
        ev = newevt.EventReferences[self.module,self.resource]
        if hasattr(ev,"unpause"):
            ev.unpause()
        else:
            ev.register()

    def stop(self):
        ev = newevt.EventReferences[self.module,self.resource]
        if hasattr(ev,"pause"):
            ev.pause()
        else:
            ev.unregister()
    
    def reportException(self):
        """Call in an exception handler to handle the exception as if it came from the given event"""
        newevt.EventReferences[self.module,self.resource]._handle_exception()


class Page(ResourceObject):
    resourceType = "page"

class Permission(ResourceObject):
    resourceType = "permission"

class InternalFileRef(ResourceObject):
    resourceType = 'internal-fileref'

    def getPath(self):
        "Return the actual path on the filesystem of things"
        return fileResourceAbsPaths[self.module, self.resource]


class VirtualResourceReference(weakref.ref):
    def __getitem__(self,name):
        if name == "resource-type":
            return "virtual-resource"
        else:
            raise KeyError(name)

class ModuleObject(object):
    """
    These are the objects acessible as 'module' within pages, events, etc.
    Normally you use them to share variables, but they have incomplete and undocumented support
    For acting as an API for user code to acess or modify the resources, which could be useful if you want to be able to
    dynamically create resources, or more likely just acess file resource contents or metadata about the module.
    """
    def __init__(self,modulename:str):
        self.__kaithem_modulename__ = modulename

    def __getitem__(self,name):
        "When someone acesses a key, return an interface to that module."
        x= ActiveModules[self.__kaithem_modulename__][name]

        if isinstance(x,weakref.ref):
            return VirtualResourceInterface(x())

        module= self.__kaithem_modulename__

        resourcetype = x['resource-type']

        if resourcetype == 'page':
            x = Page(module,name,x)

        elif resourcetype == 'event':
            x = EventAPI(module,name,x)

        elif resourcetype == 'permission':
            x = Permission(module,name,x)

        elif resourcetype == 'internal-fileref':
            x = InternalFileRef(module,name,x)

        return x

        raise KeyError(name)

    def __setitem__(self,name, value):
        "When someone sets an item, validate it, then do any required bookkeeping"


        module = self.__kaithem_modulename__

        with modulesLock:
            #Delete dead weakrefs
            if isinstance(value, VirtualResource):
                insertVirtualResource(module,name,value)
                return
            else:
                if not 'resource-type' in value:
                    raise ValueError("Supplied dict has no resource-type")
                resourcetype= value['resource-type']
                #Raise an exception on anything non-serializable or without a resource-type,
                #As those could break something.
                json.dumps({name:value})
                unsaved_changed_obj[(module,name)] = "User code inserted or modified module"
                #Insert the new item into the global modules thing
                ActiveModules[module][name]=value
                modules_state.createRecoveryEntry(module,name,value)
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




#This is used for the kaithem object.
class ResourceAPI(object):
    VirtualResource = VirtualResource

    def __getitem__(self,name):
        if isinstance(name,tuple):
            x= ActiveModules[name[0]][name[1]]
            if isinstance(x,weakref.ref):
                return x
            else:
                raise ValueError("Name refers to a non-virtual resource")

kaithemobj.kaithem.resource = ResourceAPI()


def insertVirtualResource(modulename:str,name:str,value:VirtualResource):
    with modulesLock:
        module=ActiveModules[modulename]
        rmlist = []
        for i in module:
            if isinstance( module[i], weakref.ref):
                if not module[i]():
                    rmlist.append(i)
        for i in rmlist:
            del  module[i]

        if name in module:
            if not isinstance(module[name], weakref.ref):
                raise RuntimeError("Cannot overwrite real resource with virtual. You must delete old resource first")
            if not isinstance(value, module[name]().__class__):
                raise RuntimeError("Can only overwrite virtual resource with same class. Delete old resource first.")
            x = module[name]()
            if x:
                x.handoff(value)

        module[name]=VirtualResourceReference(value)

        #Set the value's "name". A virtual resource may only have one "hard link". The rest of the links, if you insert under multiple
        #names, will work, but won't be the "real" name, and subscriptions and things like that are always to the real name.
        
        #VResources can have names set elsewhere, and those are respected
        if not value.name:
            value.name="x-module:"+ util.url(modulename)+"/"+ "/".join([util.url(i) for i in util.split_escape(name,"/","\\")])

def parsePyModule(s):
    "Unused at the moment"
    md =''
    tr = ''
    act =''
    mode = 'setup'

    for i in s.split(lines):

        if not( i.startswith(' ') or i.startswith('\t')):
            if 'def trigger' in i:
                mode='trig'
            if 'def action' in i:
                mode='act'
            if '#---BEGIN_METADATA---' in i:
                mode = 'meta'
            if '#---END_METADATA---' in i:
                mode = 'setup'
            continue

        if mode=='trig':
            if not i.strip():
                continue
            if i.strip().startswith("#"):
                continue
            if tr:
                raise ValueError("Multiline trigger")
            i = i.strip()
            if i.startswith('return'):
                tr = i[6:]

        if mode=='act':
            i = i.strip()
            act+=i+'\n'
                    
        if mode=='meta':
            i = i.strip()
            md+=i+'\n'

        if mode=='setup':
            i = i.strip()
            setup+=i+'\n'
                   
#Backwards compatible resource loader.
def loadResource(fn:str,ver:int=1):
    try:
        with open(fn,"rb") as f:
            try:
                d = f.read().decode("utf-8")
                #This regex is meant to handle any combination of cr, lf, and trailing whitespaces
                sections = re.split("\r?\n---[ |\t]*?\r?\n",d)
                r = yaml.load(sections[0])
            except:
                #This is a workaround for when dolphin puts .directory files in directories and gitignore files
                #and things like that. Also ignore attempts to load from filedata
                #I'd like to add more workarounds if there are other programs that insert similar crap files.
                if "/.git" in fn or "/.gitignore" in fn or "__filedata__" in fn or fn.endswith(".directory"):
                    return None
                else:
                    raise
            if not r or not 'resource-type' in r:
                if "/.git" in fn or "/.gitignore" in fn or "__filedata__" in fn or fn.endswith(".directory"):
                    return None
                else:
                    print(fn)




        #Catch new style save files
        if len(sections)>1:
            if r['resource-type'] == 'page':
                r['body'] = sections[1]

            if r['resource-type'] == 'event':
                r['setup'] = sections[1]
                r['action'] = sections[2]
        
        #If no resource timestamp use the one from the file time.
        if not 'resource-timestamp' in r:
            r['resource-timestamp'] = int(os.stat(fn).st_mtime*1000000)
        return r
    except:
        logger.exception("Error loading resource from file "+fn)
        raise
    logger.debug("Loaded resource from file "+fn)

def saveResource2(r,fn:str):
    #Don't save VResources
    if isinstance(r,weakref.ref):
        logger.debug("Did not save resource because it is virtual")
        return
    logger.debug("Saving resource to"+str(fn))

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

    with open(fn,"wb") as f:
        util.chmod_private_try(fn,execute = False)
        f.write(d.encode("utf-8"))

    logger.debug("saved resource to file "+ fn)

def saveResource(r,fn:str):
    with open(fn,"wb") as f:
        util.chmod_private_try(fn, execute=False)
        f.write(yaml.dump(r).encode("utf-8"))

def cleanupBlobs():
    fddir = os.path.join(directories.vardir,"modules","filedata")
    inUseFiles = [os.path.basename(i) for i in fileResourceAbsPaths.values()]
    #Defensive programming against nonexistant file dumps directory
    if not os.path.exists(fddir):
        return
    for i in os.listdir(fddir):
        if not i in inUseFiles:
            fn = os.path.join(fddir,i )
            os.remove(fn)

def saveAll():
    """saveAll and loadall are the ones outside code shold use to save and load the state of what modules are loaded.
    This function writes to data after backing up to a timestamp dir and deleting old timestamp dirs"""

    #This is an RLock, and we need to use the lock so that someone else doesn't make a change while we are saving that isn't caught by
    #moduleschanged.
    
    with modulesLock:
        if not unsaved_changed_obj:
            return False
        logger.info("Begin saving all modules")
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

def loadRecoveryDbInfo(completeFileTimestamp=0):
    global moduleschanged
    with modulesLock:
        if modules_state.enable_sqlite_backup:
            recoveryDb = sqlite3.connect(modules_state.recoveryDbPath)

            with recoveryDb:
                c = modules_state.recoveryDb.cursor()
                c.execute("select * from change")
                for i in c:
                    #Older than what we have now, ignore, the state was saved
                    #After this entry was created
                    if not i['time']/1000000 > completeFileTimestamp:
                        continue
                    unsaved_changed_obj[i['module'],i['resource']] = "Recovered from RAM"
                    moduleschanged = True
                    if i['flag'] ==0:
                        if not i['module'] in modules_state.ActiveModules:
                            modules_state.ActiveModules[i['module']]={}
                            scopes[i['module']] = ModuleObject(i['module'])
                        
                   
                        r = json.loads(i['value'])
                        modules_state.ActiveModules[i['module']][i['resource']] = r

                        if r['resource-type'] == "internal-fileref":
                            newpath = os.path.join(directories.vardir,"modules","filedata",r['target'])
                            fileResourceAbsPaths[i['module'],i['resource']] = newpath

                    else:
                        if not i['module'] in modules_state.ActiveModules:
                            continue
                        if i['resource'] in  modules_state.ActiveModules[i['module']]:
                            del modules_state.ActiveModules[i['module']][i['resource']]
                        if not modules_state.ActiveModules[i['module']]:
                            del modules_state.ActiveModules[i['module']]
            recoveryDb.close()


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
                        logger.exception("Failed to rename corrupted data. This is normal if kaithem's var dir is not currently writable.")
        
        loadRecoveryDbInfo(completeFileTimestamp=os.stat(os.path.join(possibledir,'__COMPLETE__')).st_mtime)

    except:
        messagebus.postMessage("/system/notifications/errors" ," Error loading modules: "+ traceback.format_exc(4))
    
    
    auth.importPermissionsFromModules()
    newevt.getEventsFromModules()
    usrpages.getPagesFromModules()
    remotedevices.loadProgramsFromModules()
    moduleshash = hashModules()
    try:
        cleanupBlobs()
    except:
        logger.exception("Failed to cleanup old blobs. This is normal if kaithem's var dir is not currently writable.")
    logger.info("Initialized modules")

def saveModule(module, dir:str,modulename:Optional[str]=None, ignore_func=None):
    """Returns a list of saved module,resource tuples and the saved resource.
    ignore_func if present must take an abs path and return true if that path should be
    left alone. It's meant for external modules and version control systems.
    """
    #Iterate over all of the resources in a module and save them as json files
    #under the URL url module name for the filename.
    logger.debug("Saving module "+str(modulename))
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
                currentFileLocation = fileResourceAbsPaths[modulename,resource]
                #Handle broken targets if a file was manually deleted
                if os.path.isfile(currentFileLocation):
                    #If the resource yaml file is in the vardir, so the file data goes in filedata from wherever it currently is.
                    if util.in_directory(fn, directories.vardir):
                        newpath = os.path.join(directories.vardir,"modules","filedata",r['target'])
                        #And the file is not already in place
                        if not newpath == currentFileLocation:
                            util.ensure_dir(newpath)
                            #It doesn't matter if this gets interrupted. Files are UUID identified so they never overwite
                            #So really if a dump gets interrupted there won't be anything valid to reference it
                            #and it will just get cleaned up as an unused blob.
                            #What's important is not deleting stuff in external folders for no reason.
                            shutil.copyfile(currentFileLocation, newpath)
                            fileResourceAbsPaths[modulename,resource] = newpath
                    #Resource file is outside vardir. So the actual file data belongs with the module folder
                    else:
                        newpath = os.path.join(dir,"__filedata__",r['target'])
                        if not newpath == currentFileLocation:
                            util.ensure_dir(newpath)
                            #Storage is cheap enough I guess, might as well copy instead of move for now. Maybe
                            #change it?
                            shutil.copyfile(currentFileLocation, newpath)
                            fileResourceAbsPaths[modulename,resource] = newpath
                #broken target
                else:
                    logger.error("File reference resource has nonexistant target, igonring.")

        #Now we iterate over the existing resource files in the filesystem and delete those that correspond to
        #resources that have been deleted in the ActiveModules workspace thing.
        #If there were no resources in module, and we never made a dir, don't do anything.
        if os.path.isdir(dir):
            for j in util.get_files(dir):
                p = os.path.join(dir,j)
                if ignore_func and ignore_func(p):
                    continue
                if util.unurl(j) not in module:
                    os.remove(p)
                    #Remove them from the list of unsaved changed things.
                    if (modulename,util.unurl(j)) in unsaved_changed_obj:
                        saved.append((modulename,util.unurl(j)))
        saved.append(modulename)
        return saved
    except:
        raise

def saveToRam():
    #Command line arguments plus file location should be good enough to
    #tell instances apart on one machine
    uniqueInstanceId = ",".join(sys.argv) + os.path.normpath(__file__)
    uniqueInstanceId= hashlib.sha1(uniqueInstanceId.encode("utf8")).hexdigest()[:24]
    if os.path.exists("/dev/shm/"):
        saveModules(os.path.join("/dev/shm/kaithem"+uniqueInstanceId, "modulesbackup"), markSaved=False)

def saveModules(where:str,markSaved=True):
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

            for i in [i for i in ActiveModules if i in external_module_locations]:
                try:
                    saved.extend(saveModule(ActiveModules[i],external_module_locations[i],modulename=i,ignore_func=detect_ignorable))
                except:
                    try:
                        logger.exception("Failed to save external module to"+str(external_module_locations[i]))
                    except:
                        pass
                    messagebus.postMessage("/system/notifications/errors",'Failed to save external module:' + traceback.format_exc(8))

            for i in util.get_immediate_subdirectories(where):
                #Look in the modules directory, and if the module folder is not in ActiveModules\
                #We assume the user deleted the module so we should delete the save file for it.
                #Note that we URL url file names for the module filenames and foldernames.

                #We also delete things that are in the "external_module_locations" because they have been moved there. Unless it happens to point here!
                if util.unurl(i) not in ActiveModules or (((util.unurl(i) in external_module_locations)  and not external_module_locations[util.unurl(i)]==os.path.join(where,i))):
                    shutil.rmtree(os.path.join(where,i))
                    saved.append(util.unurl(i))

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


            #mark things that get created and deleted before ever saving so they don't persist in the unsaved list.
            #note that we skip things beginning with __ because that is reserved and migh not even represent a module.
            for i in unsaved_changed_obj:
                if isinstance(i,tuple) and len(i)>1 and (not i[0].startswith("__")) and ((not i[0]  in ActiveModules) or (not i[1] in ActiveModules[i[0]])):
                    saved.append(i)
                else:
                    if isinstance(i,str) and not i.startswith("__") and not i in ActiveModules:
                        saved.append(i)

            if markSaved:
                #Now that we know the dump is actually valid, we remove those entries from the unsaved list for real
                for i in saved:
                    if i in unsaved_changed_obj:
                        del unsaved_changed_obj[i]
            modules_state.purgeSqliteBackup()

        except:
            raise


def loadModules(modulesdir:str):
    "Load all modules in the given folder to RAM."
    logger.debug("Loading modules from "+modulesdir)
    for i in util.get_immediate_subdirectories(modulesdir):
        loadModule(os.path.join(modulesdir,i), util.unurl(i))

    for i in os.listdir(modulesdir):
        try:
            if not i.endswith(".location"):
                continue
            if not os.path.isfile(os.path.join(modulesdir,i)):
                continue
            #Read ythe location we are supposed to load from
            with open(os.path.join(modulesdir,i)) as f:
                s = f.read(4096)
            #Get rid of the __ and .location, then set the location in the dict
            with modulesLock:
                external_module_locations[util.unurl(i[2:-9])] = s
            #We use the ignore func when loading ext modules
            loadModule(s, util.unurl(i[2:-9]),detect_ignorable)
        except:
            messagebus.postMessage("/system/notifications/errors" ," Error loading external module: "+ traceback.format_exc(4))


def detect_ignorable(path:str):
    "Recursive detect paths that should be ignored and left alone when loading and saving"
    #Safety counter, this seems like it might need it.
    for i in range(64):
        if _detect_ignorable(path):
            return True
        path = os.path.dirname(path)
        #Detect end of path
        if not os.path.split(path)[1]:
            return

def _detect_ignorable(path:str):
    "Detect paths that should be ignored when loading a module"
    #Detect .git
    if os.path.basename(path) == ".git":
        #Double check, because we can, on the off chance something else is named .git
        if os.path.exists(os.path.join(path,"HEAD")) or os.path.exists(os.path.join(path,"branches")):
            return True
    #I think that's how you detect hg repos?
    if os.path.basename(path) == ".hg" and os.path.isdir(path):
        return True
    if os.path.basename(path) in [".gitignore",".gitconfig"]:
        return True


def loadModule(folder:str, modulename:str, ignore_func=None):
    "Load a single module but don't bookkeep it . Used by loadModules"
    logger.debug("Attempting to load module "+modulename)
    with modulesLock:
        #Make an empty dict to hold the module resources
        module = {}
        #Iterate over all resource files and load them
        for root, dirs, files in os.walk(folder):
                #Function used to ignore things like VCS folders and such
                if ignore_func and ignore_func(root):
                    continue
                for i in files:
                    if ignore_func and ignore_func(i):
                        continue
                    relfn = os.path.relpath(os.path.join(root,i),folder)
                    fn = os.path.join(folder , relfn)
                    #Copy stuff from anything called filedata to handle library modules with filedata
                    if os.path.basename(root) == "__filedata__":
                        if not os.path.exists(os.path.join(directories.vardir,"modules","filedata")):
                            os.makedirs(os.path.join(directories.vardir,"modules","filedata"),700)

                        #Special case handling of if we are loading from the data dir
                        if util.in_directory(fn, directories.datadir):
                            shutil.copy(fn, os.path.join(directories.vardir,"modules","filedata"))
                        continue
                    #Load the resource and add it to the dict. Resouce names are urlencodes in filenames.
                    resourcename = util.unurl(relfn)
                    r = loadResource(fn)
                    if not r:
                        continue
                    module[resourcename] = r
                    if not 'resource-type' in r:
                        logger.warning("No resource type found for "+resourcename)
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
                            fileResourceAbsPaths[modulename,resourcename] = os.path.join(folder,"__filedata__",r['target'])

                for i in dirs:
                    if i == "__filedata__":
                        continue
                    if ignore_func and ignore_func(i):
                        continue
                    relfn = os.path.relpath(os.path.join(root,i),folder)
                    fn = os.path.join(folder , relfn)
                    #Load the resource and add it to the dict. Resouce names are urlencodes in filenames.
                    module[util.unurl(relfn)] = {"resource-type":"directory"}


        scopes[modulename] = ModuleObject(modulename)
        ActiveModules[modulename] = module
        messagebus.postMessage("/system/modules/loaded",modulename)
        logger.info("Loaded module "+modulename +" with md5 "+getModuleHash(modulename))
        #bookkeeponemodule(name)

def getModuleAsZip(module:str,noFiles:bool=True):
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
        p = util.unurl(i.split('/')[0])
        #Remove the.json by getting rid of last 5 chars
        n = util.unurl((i.split('/'))[1][:-5])
        if p not in new_modules and not "__filedata__" in p:
            new_modules[p] = {}
        try:
            if not  "__filedata__" in p:
                try:
                    f = z.open(i)
                    r = yaml.load(f.read().decode())
                    if r==None:
                        raise RuntimeError("Attempting to decode file "+str(i)+" resulted in a value of None")
                    new_modules[p][n] = r
                    if r['resource-type'] == "internal-fileref":
                        newfrpaths[p,n] = os.path.join(directories.vardir,"modules","filedata",r['target'])
                finally:
                    f.close()
            else:
                try:
                    inputfile = z.open(i)
                    folder = os.path.join(directories.vardir,"modules","filedata")
                    util.ensure_dir2(folder)
                    data_basename = util.unurl(i.split('/')[1])
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
                finally:
                    inputfile.close()
                newfrpaths[p,n] = dataname
        except:
            raise RuntimeError("Could not correctly process "+str(i))


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
                rmModule(i,"Module Deleted by " + pages.getAcessingUser() + " during process of update")

                messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " Deleted old module " + i+" for auto upgrade")
                messagebus.postMessage("/system/modules/unloaded",i)
                messagebus.postMessage("/system/modules/deleted",{'user':pages.getAcessingUser()})

        try:
            for i in new_modules:
                ActiveModules[i] = new_modules[i]
                
                for j in ActiveModules[i]:
                    modules_state.createRecoveryEntry(i,j,ActiveModules[i][j])
                messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " uploaded module" + i + " from a zip file")
                bookkeeponemodule(i)
        except:
            for i in new_modules:
                if i in backup:
                    ActiveModules[i] = backup[i]
                    for j in ActiveModules[i]:
                        modules_state.createRecoveryEntry(i,j,ActiveModules[i][j])
                    messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " uploaded module" + i + " from a zip file, but initializing failed. Reverting to old version.")
                    bookkeeponemodule(i)
            raise
        fileResourceAbsPaths.update(newfrpaths)

        modulesHaveChanged()
        for i in new_modules:
            unsaved_changed_obj[i] = "Changed or created by zip upload"
            for j in new_modules[i]:
                unsaved_changed_obj[i,j] ="Changed or created by zip upload"

    z.close()
    return new_modules.keys()

def bookkeeponemodule(module,update=False):
    """Given the name of one module that has been copied to activemodules but nothing else,
    let the rest of the system know the module is there."""
    if not module in scopes:
        scopes[module] = ModuleObject(module)
    for i in ActiveModules[module]:
        if ActiveModules[module][i]['resource-type'] == 'k4dprog_sq':
            remotedevices.updateProgram(module, i, ActiveModules[module][i])



        if ActiveModules[module][i]['resource-type'] == 'page':
            try:
                usrpages.updateOnePage(i,module)
            except Exception as e:
                usrpages.makeDummyPage(i,module)
                logger.exception("failed to load resource")
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
       modules_state.createRecoveryEntry(module,resource,None)
    try:
        if r['resource-type'] == 'page':
            usrpages.removeOnePage(module,resource)

        elif r['resource-type'] == 'event':
            newevt.removeOneEvent(module,resource)

        elif r['resource-type'] == "k4dprog_sq":
            remotedevices.removeProgram(module,resource)

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
    unsaved_changed_obj[name] = "Module Created"

    #If there is no module by that name, create a blank template and the scope obj
    with modulesLock:
        if location:
            external_module_locations[name]= os.path.expanduser(location)

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
        modules_state.createRecoveryEntry(name,"__description",ActiveModules[name]["__description"])
        bookkeeponemodule(name)
        #Go directly to the newly created module
        messagebus.postMessage("/system/notifications","User "+ pages.getAcessingUser() + " Created Module " + name)
        messagebus.postMessage("/system/modules/new",{'user':pages.getAcessingUser(), 'module':name})




def rmModule(module,message="deleted"):
    modulesHaveChanged()
    unsaved_changed_obj[module]=message
    with modulesLock:
        x =ActiveModules.pop(module)
        j = {i:copy.deepcopy(x[i])  for i in x if not(isinstance(x[i], weakref.ref))}
        scopes.pop(module)

    #Delete any custom resource types hanging around.
    for k in j:
        if j[k].get('resource-type',None) in additionalTypes:
            try:
                additionalTypes[j[k]['resource-type']].ondelete(module,k,j[k])
            except:
                messagebus.postMessage("/system/modules/errors/unloading","Error deleting resource: "+str(module,k))
        modules_state.createRecoveryEntry(module,k,None)
    #Get rid of any lingering cached events
    newevt.removeModuleEvents(module)
    #Get rid of any permissions defined in the modules.
    auth.importPermissionsFromModules()
    usrpages.removeModulePages(module)
    with modulesLock:
        if module in external_module_locations:
            del external_module_locations[module]
    #Get rid of any garbage cycles associated with the event.
    gc.collect()
    messagebus.postMessage("/system/modules/unloaded",module)
    messagebus.postMessage("/system/modules/deleted",{'user':pages.getAcessingUser()})

class KaithemEvent(dict):
    pass

kaithemobj.kaithem.resource.VirtualResource = VirtualResource
