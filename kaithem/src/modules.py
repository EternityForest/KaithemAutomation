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
import threading,urllib,shutil,sys,time,os,json,traceback,copy,hashlib
import cherrypy,yaml
from . import auth,pages,directories,util,newevt,kaithemobj,usrpages,messagebus,scheduling,modules_state
from .modules_state import ActiveModules,modulesLock,scopes


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




moduleshash= "000000000000000000000000"
modulehashes = {}

def hashModules():
    m=hashlib.md5()
    with modulesLock:
        for i in sorted(ActiveModules.keys()):
            for j in sorted(ActiveModules[i].keys()):
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


#Backwards compatible resource loader.
def loadResource(r):
    with open(r) as f:
        d = f.read()
    if "\r---\r" in d:
            f = d.split("\r---\r")
    elif "\r\n\---\r\n" in d:
            f = d.split("\r\n---\r\n")
    else:
        f = d.split("\n---\n")
    r = yaml.load(f[0])

    #Catch old style save files
    if len(f)>1:
        if r['resource-type'] == 'page':
            r['body'] = f[1]

        if r['resource-type'] == 'event':
            r['setup'] = f[1]
            r['action'] = f[2]

    return r

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
        moduleschanged = False
        return True

def initModules():
    global moduleshash
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
                name = util.getHighestNumberedTimeDirectory(directories.moduledir)
                possibledir = os.path.join(directories.moduledir,name)

                if '''__COMPLETE__''' in util.get_files(possibledir):
                    loadModules(possibledir)
                #we found the latest good ActiveModules dump! so we break the loop
                    break
                else:
                    #If there was no flag indicating that this was an actual complete dump as opposed
                    #To an interruption, rename it and try again

                    shutil.copytree(possibledir,os.path.join(directories.moduledir,name+"INCOMPLETE"))
                    #It would be best if we didn't rename or get rid of the data directory because that's where
                    #manual tools might be working.
                    if not possibledir == os.path.join(directories.moduledir,"data"):
                        shutil.rmtree(possibledir)
    except:
        messagebus.postMessage("/system/notifications/errors" ," Error loading modules: "+ traceback.format_exc(4))

    auth.importPermissionsFromModules()
    newevt.getEventsFromModules()
    usrpages.getPagesFromModules()
    moduleshash = hashModules()



def saveModules(where):
    """Save the modules in a directory as JSON files. Low level and does not handle the timestamp directories, etc."""
    with modulesLock:
        util.ensure_dir2(os.path.join(where))
        util.chmod_private_try(os.path.join(where))
        #If there is a complete marker, remove it before we get started. This marks
        #things as incomplete and then when loading it will use the old version
        #when done saving we put the complete marker back.
        if os.path.isfile(os.path.join(where,'__COMPLETE__')):
            os.remove(os.path.join(where,'__COMPLETE__'))
        for i in ActiveModules:
            #Iterate over all of the resources in a module and save them as json files
            #under the URL urld module name for the filename.
            for resource in ActiveModules[i]:
                #Make sure there is a directory at where/module/
                util.ensure_dir(os.path.join(where,url(i),url(resource))  )
                util.chmod_private_try(os.path.join(where,url(i)))
                #Open a file at /where/module/resource
                fn = os.path.join(where,url(i),url(resource))
                #Make a json file there and prettyprint it
                saveResource2(ActiveModules[i][resource],fn)

            #Now we iterate over the existing resource files in the filesystem and delete those that correspond to
            #modules that have been deleted in the ActiveModules workspace thing.
            for j in util.get_files(os.path.join(where,url(i))):
                if unurl(j) not in ActiveModules[i]:
                    os.remove(os.path.join(where,url(i),j))

        for i in util.get_immediate_subdirectories(where):
            #Look in the modules directory, and if the module folder is not in ActiveModules\
            #We assume the user deleted the module so we should delete the save file for it.
            #Note that we URL url file names for the module filenames and foldernames.
            if unurl(i) not in ActiveModules:
                shutil.rmtree(os.path.join(where,i))
        with open(os.path.join(where,'__COMPLETE__'),'w') as f:
            util.chmod_private_try(os.path.join(where,'__COMPLETE__'), execute=False)
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
        for root, dirs, files in os.walk(os.path.join(path_to_module_folder,moduledir)):
                for i in files:
                    relfn = os.path.relpath(os.path.join(root,i),os.path.join(path_to_module_folder,moduledir))
                    fn = os.path.join(path_to_module_folder,moduledir , relfn)
                    #Load the resource and add it to the dict. Resouce names are urlencodes in filenames.
                    module[unurl(relfn)] = loadResource(fn)
                for i in dirs:
                    relfn = os.path.relpath(os.path.join(root,i),os.path.join(path_to_module_folder,moduledir))
                    fn = os.path.join(path_to_module_folder,moduledir , relfn)
                    #Load the resource and add it to the dict. Resouce names are urlencodes in filenames.
                    module[unurl(relfn)] = {"resource-type":"directory"}


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

def getModuleAsYamlZip(module):
    with modulesLock:
        #We use a stringIO so we can avoid using a real file.
        ram_file = StringIO()
        z = zipfile.ZipFile(ram_file,'w')
        #Dump each resource to JSON in the ZIP
        for resource in ActiveModules[module]:
            #AFAIK Zip files fake the directories with naming conventions
            s = yaml.dump(ActiveModules[module][resource])
            z.writestr(url(module)+'/'+url(resource)+".yaml",s)
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
        new_modules[p][n] = yaml.load(f.read().decode())
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
