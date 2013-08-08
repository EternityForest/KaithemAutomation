import threading,os,shutil,time
import cherrypy
from . import util,json,directories,pages
from .util import url, unurl
persistancedicts = {}

#This is only used for checking if a dict already exists and creating it with defaults if not.
persistance_dict_connection_lock = threading.RLock()

persistancefileschanged = False

class WebInterface(object):
    
    @cherrypy.expose
    def index(self):
        pages.require("/admin/persistancefiles.view")
        return pages.get_template("persistfiles/index.html").render()
    
    @cherrypy.expose
    def index(self):
        pages.require("/admin/persistancefiles.view")
        return pages.get_template("persistfiles/delete.html").render()
    
    
    @cherrypy.expose
    def deletetarget(self,**kwargs):
        pages.require("/admin/persistancefiles.edit")
        with persistance_dict_connection_lock:
            #If there are only two references(the one passed to getrefcount and the dit entry)
            #That means that no user code is keeping a reference and it is not in use.
            if sys.getrefcount(persistancedicts[kwargs['name']]) == 2:
                del persistancedicts[kwargs['name']]
            else:
                raise cherrypy.HTTPRedirect("/errors/inuse")
        
def loadAll():
    for i in range(0,15):
        #Gets the highest numbered of all directories that are named after floating point values(i.e. most recent timestamp)
        name = util.getHighestNumberedTimeDirectory(directories.persistdir)
        possibledir = os.path.join(directories.persistdir,name)
        
        #__COMPLETE__ is a special file we write to the dump directory to show it as valid
        if '''__COMPLETE__''' in util.get_files(possibledir):
            with persistance_dict_connection_lock:
                for i in util.get_files(possibledir):
                    with open(os.path.join(directories.persistdir,i)) as f:
                        persistancedict[util.unurl(i)] = _PersistanceFile(json.load(f))
                
            break #We sucessfully found the latest good ActiveModules dump! so we break the loop
        else:
            #If there was no flag indicating that this was an actual complete dump as opposed
            #To an interruption, rename it and try again
            shutil.copytree(possibledir,os.path.join(directories.persistdir,name+"INCOMPLETE"))
            shutil.rmtree(possibledir)
            
#saveall and loadall are the ones outside code shold use to save and load the state of what modules are loaded
def saveAll():
    #This dumps the contents of the active modules in ram to a subfolder of the moduledir named after the current unix time"""
    dn = os.path.join(directories.persistdir,str(time.time()) )
    #Ensure dir does not make the last path component
    util.ensure_dir(os.path.join(dn,"dummy"))
    savefiles(dn)
    #We only want 1 backup(for now at least) so clean up old ones.  
    util.deleteAllButHighestNumberedNDirectories(directories.persistdir,2)

def savefiles(where):
    
    with persistance_dict_connection_lock:
        for i in persistancedicts:
            #Nobody can chang it while we are saving
            with persistancedicts[i].lock:
                #Open a file at /where/module/resource
                with open(os.path.join(where,url(i)),"w") as f:
                    #Make a json file there and prettyprint it
                    json.dump(persistancedicts[i].d,f,sort_keys=True,indent=4, separators=(',', ': '))

        with open(os.path.join(where,'__COMPLETE__'),'w') as f:
            f.write("By this string of contents quite arbitrary, I hereby mark this dump as consistant!!!")

def PersistanceFile(fn):
    with persistance_dict_connection_lock:
        if fn in persistancedicts:
            return persistancedicts[fn]
        else:
            persistancedicts[fn] = _PersistanceFile({})
            return persistancedicts[fn]

class _PersistanceFile(object):
    "This class represents on persistance file using the pathlist API"
    def __init__(self,d):
        self.d = d
        #This MUST be a reentrant lock because functions call other functions that also need the lock.
        self.lock = threading.RLock()

    def __split_path(self,path ):
        if isinstance(path,str):
           if path.startswith('/'):
               path = path[1:]
           
           path = path.split('/')
        return path
    
    def __resolve_path(self, path):
        path = self.__split_path(path)
        
        #Resolving the root, split path will have gotten rid of the startign slash
        if not(path):
            return self.d
        x = self.d[path[0]]
        for i in path[1:]:
            x = x[i]
            
        return x
    
    def __make_path(self, path):
        "Make all directories that arent there up to path, bulldozing all lists in the path. path must be list"
        path = self.__split_path(path)
        x = self.d
        for i in path:
            if not i in x:
                x[i] = {}
            if not isinstance(x[i],dict):
                x[i] = {}
                
            x = x[i]
            
        return x
    
    def write(self,path,value):
        "Write a value to a list at path, replacing anything that might be there"
        if not isinstance(value,(str,bool,int,float,list)):
            raise TypeError("Value must be string, boolean, integer, or floating point, or list containing only those.")
        
        with self.lock:
            global persistancefileschanged
            persistancefileschanged = True
            path = self.__split_path(path)
            #Make all the dirs
            x = self.__make_path(path[:-1])
            #The last element of the path is the list name
            if not isinstance(value,(list)):
                x[path[-1]] = [value] #Values are special cases of lists with one element.
            else:
                for i in value:
                    if not isinstance(i,(str,bool,int,float,list)):
                        raise TypeError("Lists may only contain strings, bools, and floats.")
                
                x[path[-1]] = value
                
    
    def write_if_missing(self, key,value):
        #This is implemented as a guard wrapper around write
        with self.lock:
            if self.whatis(key) == None:
                global persistancefileschanged
                persistancefileschanged = True
                self.write(key,value)
                return True
            else:
                return False
    

    def append(self,path,value):
        "Given a path that represents a list, append something to that list, creating it if it is not there."
        if not isinstance(value,(str,bool,int,float)):
            raise TypeError("Value must be string, boolean, integer, or floating point")
        
        with self.lock:
            global persistancefileschanged
            try:
                x = self.__resolve_path(path)
            except KeyError:
                self.overwrite(path,value)
                persistancefileschanged = True
                
        
            if isinstance(x,list):
                x.append(value)
                persistancefileschanged = True
            else:
                raise RuntimeError("Path must represent a list, but given path is a dir.")
            
    def remove_first_match(self,path,value):
        "Given a path that represents a list, remove one item by value"
        if not isinstance(value,(str,bool,int,float)):
            raise TypeError("Value must be string, boolean, integer, or floating point")
        
        with self.lock:
            global persistancefileschanged
            x = self.__resolve_path(path)
            
            if isinstance(x,list):
                if value in x:
                    x.remove(value)
                    persistancefileschanged =True
                    return True
                else:
                    return False
            else:
                raise RuntimeError("path is a directory and not a list. Use rmtree to remove directories")
            
    
    def whatis(self, path):
        "Given a path, returns none, dict, or list depending on what the path is."
        with self.lock:
            try:
                x = self.__resolve_path(path)
            except KeyError:
                return None
            
            if isinstance(x,list):
                return list
            
            else:
                return dict
    
    def get(self,path,index =0, default = None):
        with self.lock:
            try:
                x = self.__resolve_path(path)
            except KeyError:
                if not default == None:
                    return default
                else:
                    raise RuntimeError("Path does not refer to anything")
            
            if isinstance(x,list):
                return x[index]
            
            else:
                raise RuntimeError("Path refers to a directory, not a value")
            
    def get_list(self, path):
        with self.lock:
            if self.whatis(path) == list:
                return self.__resolve_path(path)
            else:
                raise RuntimeError("Path must be a list")  
    
    def remove(self,path):
        with self.lock:
            global persistancefileschanged
            try:
                x = self.__split_path(path)
                container = self.__resolve_path(x[:-1])
                del container[x[-1]]
                persistancefileschanged = True
                return True
            except KeyError:
                return False
      
    def len(self, path):
        with self.lock:
            if self.whatis(path) == list:
                return len(self.__resolve_path(path))
            else:
                raise RuntimeError("Path must be a list")
            
    def ls(self, path):
        with self.lock:
            if self.whatis(path) == dict:
                return list(self.__resolve_path(path).keys())
            else:
                raise RuntimeError("Path must be a directory")
            

    
class TestHook(_PersistanceFile):
       "Same, but no file connection, so it is totally testable"
       def __init__(self):
            self.d = {}
            self.lock = threading.RLock()   
        
    

