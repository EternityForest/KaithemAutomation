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



import  os,threading,copy,sys,shutil
#2 and 3 have basically the same module with diferent names
if sys.version_info < (3,0):
    from urllib import quote
    from urllib import unquote as unurl
else:
    from urllib.parse import quote
    from urllib.parse import unquote as unurl

savelock = threading.RLock()

def url(string):
    return quote(string,'')

def SaveAllState():
    #fix circular import by putting it here
    from . import  auth,modules,messagelogging,messagebus,registry
    
    with savelock:
        try:
            x = False
            x = x or modules.saveAll()
            x = x or auth.dumpDatabase()
            messagelogging.dumpLogFile()
            x = x or registry.sync()
            #Always send the message, because there is almost always going to be at least some log entries saved
            messagebus.postMessage("/system/notifications","Global server state was saved to disk")
            return x
        except Exception as e:
            messagebus.postMessage("/system/notifications/errors",'Failed to save state:' + repr(e))


def SaveAllStateExceptLogs():
    #fix circular import
    from . import  auth,modules,messagelogging,messagebus,registry
    with savelock:
        try:
            x = False
            x = x or auth.dumpDatabase()
            x = x or modules.saveAll()
            x = x or registry.sync()
            if x:
                #Send the message only if something was actually saved.
                messagebus.postMessage("/system/notifications","Global server state was saved to disk")
            return x
        except Exception as e:
            messagebus.postMessage("/system/notifications/errors",'Failed to save state:' + repr(e))

    
def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)
        
def readfile(f):
    with open(f) as fh:
        r = fh.read()
    return r

#Get the names of all subdirectories in a folder but not full paths
def get_immediate_subdirectories(folder):
    return [name for name in os.listdir(folder)
            if os.path.isdir(os.path.join(folder, name))]

#Get a list of all filenames but not the full paths
def get_files(folder):
    return [name for name in os.listdir(folder)
            if not os.path.isdir(os.path.join(folder, name))]
            
#fix this to not be ugly     
def getHighestNumberedTimeDirectory(where):
    """Given a directory containing entirely folders named after floating point values get the name of the highest. ignore files.
        and also ignoring non-timestapt float looking named directories
    """
    asnumbers = {}
    
    for i in get_immediate_subdirectories(where):
        try:
            asnumbers[float(i)] = i
        except ValueError:
            pass
        
    return asnumbers[sorted(asnumbers.keys(), reverse=True)[0]]

def deleteAllButHighestNumberedNDirectories(where,N):
    """In a directory full of folders named after time values, we delete all but the highest N directores ignoring files
       and also ignoring non-timestapt float looking named directories
    """
    asnumbers = {}
    for i in get_immediate_subdirectories(where):
            try:
                asnumbers[float(i)] = i
            except ValueError:
                pass
    
    for i in sorted(asnumbers.keys())[0:-N]:
        shutil.rmtree(os.path.join(where,asnumbers[i]))

class LowPassFiter(object):
    "Speed should be 0 to 1 and express by what percentage to approach the new value per sample"
    def __init__(self,speed,startval=0 ):
        self.value = startval
        self.speed = speed
    
    def sample(self, x):
        self.value = (self.value *(1-self.speed)) +   ((x) *self.speed)

#Credit to Jay of stack overflow for this function
def which(program):
    "Check if a program is installed like you would do with UNIX's which command."
    
    #Because in windows, the actual executable name has .exe while the command name does not.
    if sys.platform == "win32" and not program.endswith(".exe"):
        program += ".exe"
        
    #Find out if path represents a file that the current user can execute.
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    #If the input was a direct path to an executable, return it
    if fpath:
        if is_exe(program):
            return program
        
    #Else search the path for the file.
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
            
    #If we got this far in execution, we assume the file is not there and return None
    return None

def restart():
    cherrypy.engine.restart()

def exit():
    cherrypy.engine.exit()
    
def clearErrors():
    from . import usrpages,newevt
    for i in newevt._events[:]:
        i.errors = []
    for i in usrpages._Pages.items():
        for j in i[1].items():
            j[1].errors = []  


def updateIP():
    global MyExternalIPAdress
    #2 and 3 have basically the same module with diferent names
    if sys.version_info < (3,0):
        from urllib2 import urlopen
    else:
        from urllib.request import urlopen
        
    #Yes, This really is the only way i know of to get your public IP.
    try:
        if config['get-public-ip']:
            u= urlopen("http://ipecho.net/plain", timeout = 60)
        MyExternalIPAdress = u.read()
        
        if sys.version_info > (3,0):
            MyExternalIPAdress = MyExternalIPAdress.decode('utf8')
    except:
        MyExternalIPAdress = "unknown"
    finally:
        try:
            u.close()
        except Exception:
            pass
    return MyExternalIPAdress
          