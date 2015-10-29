# -*- coding: utf-8 -*-
#Copyright Daniel Dunn 2013
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


"This file ideally should only depend on sdtilb stuff and import the rest as needed. We don't want this to drag in threads and everything"
import  os,threading,copy,sys,shutil,difflib,time,json,traceback,stat,subprocess,copy
import yaml
#2 and 3 have basically the same module with diferent names
if sys.version_info < (3,0):
    from urllib import quote
    from urllib import unquote as unurl
    import repr as reprlib
else:
    from urllib.parse import quote
    from urllib.parse import unquote as unurl
    import reprlib

min_time = 0

if sys.version_info < (3,0):
    from urllib2 import urlopen
else:
    from urllib.request import urlopen

savelock = threading.RLock()

def chmod_private_try(p, execute=True):
    try:
        if execute:
            os.chmod(p,stat.S_IRUSR|stat.S_IWUSR|stat.S_IXUSR)
        else:
            os.chmod(p,stat.S_IRUSR|stat.S_IWUSR)
    except Exception as e:
        raise e

def open_private_text_write(p):
    try:
        x = os.open('/path/to/file', os.O_RDWR | os.O_CREAT, 0o0600)
        return os.fdopen(x,'w')
    except:
        try:
            os.close(x)
        except:
            pass
        return open(p,'w')


def url(string):
    return quote(string,'')

def SaveAllState():
    #fix circular import by putting it here
    from . import  auth,modules,messagelogging,messagebus,registry

    with savelock:
        try:
            x = False
            if modules.saveAll():
                x=True
            if auth.dumpDatabase():
                x=True
            messagelogging.dumpLogFile()
            if registry.sync():
                x=True
            #Always send the message, because there is almost always going to be at least some log entries saved
            messagebus.postMessage("/system/notifications/important","Global server state was saved to disk")
            return x
        except Exception as e:
            messagebus.postMessage("/system/notifications/errors",'Failed to save state:' + traceback.format_exc(8))


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
                messagebus.postMessage("/system/notifications/important","Global server state was saved to disk")
            return x
        except Exception as e:
            messagebus.postMessage("/system/notifications/errors",'Failed to save state:' + repr(e))


def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)

def ensure_dir2(f):
    if not os.path.exists(f):
        os.makedirs(f)

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

def getHighestNumberedTimeDirectory(where):
    """Given a directory containing entirely folders named after floating point values get the name of the highest. ignore files.
        and also ignoring non-timestapt float looking named directories
    """
    asnumbers = {}
    global min_time

    for i in get_immediate_subdirectories(where):
        try:
            asnumbers[float(i)] = i
        except ValueError:
            pass
    min_time = max(sorted(asnumbers.keys(), reverse=True)[0],min_time)
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

last = time.time()
def ip_geolocate():
   #Block for a bit if its been less than a second since the last time we did this
   while time.time()-last < 1.5:
       time.sleep(0.1)
   u=urlopen("http://ip-api.com/json", timeout = 60)
   try:
       return(json.loads(u.read().decode('utf8')))

   finally:
       u.close()

lastNTP = 0
oldNTPOffset = 30*365*24*60*60
hasInternet = False

def timeaccuracy():
    from . import messagebus
    global lastNTP,oldNTPOffset
    try:
        if (time.time() -lastNTP) > 600:
            lastNTP = time.time()
            c = ntplib.NTPClient()
            response = c.request("ntp.pool.org", version=3)
            oldNTPOffset = response.offset + response.root_delay + response.root_dispersion
            if not hasInternet:
                messagebus.postMessage("/system/internet",True)
            hasInternet = True
            return oldNTPOffset
        else:
            return oldNTPOffset + (time.time() -lastNTP)/10000
    except:
        if hasInternet:
            messagebus.postMessage("/system/internet",False)
        hasInternet = False
        return oldNTPOffset + (time.time() -lastNTP)/10000

def diff(a,b):
    x = a.split("\n")
    x2 = []
    for i in x:
        x2.append(i)
    y=b.split("\n")
    y2 = []
    for i in y:
        y2.append(i)
    return ''.join(difflib.unified_diff(x2,y2))


#This returns either the current time, or a value that is higher than any
#timestamp in the latest server save
def time_or_increment():
    if time.time()>min_time:
        return time.time()
    else:
        return int(min_time)+1.234567

def roundto(n,s):
    if not s:
        return n
    if((n%s)>(s/2)):
        return n+(s-(n%s))
    else:
        return n - n%s

def split_escape(s, separator, escape=None,preserve_escapes=False):
    current_token = ""
    tokens = []
    literal = False

    for i in s:
        if literal:
            current_token += i
            literal = False
        elif i == separator:
            tokens+= [current_token]
            current_token = ""

        elif i == escape:
            literal = True
            if preserve_escapes:
                current_token += i
        else:
            current_token +=i

    if current_token:
        return tokens+[current_token]
    else:
        return tokens

def unescape(s,escape="\\"):
    s2 = ""
    literal = False
    for i in s:
        if literal:
            s2+=i
            literal= False
        elif i == escape:
            literal = True
        else:
            s2+=i
    return s2

def resourcename_escape(s):
    return s.replace("\\","\\\\").replace("/","\\/")

def module_onelevelup(s):
    return "/".join([i.replace("\\","\\\\").replace("/","\\/") for i in split_escape(s,"/","\\")[:-1]])

numberlock = threading.Lock()
current_number = -1
def unique_number():
    global current_number
    with numberlock:
        current_number +=1
        x = current_number
    return x

def is_private_ip(ip):
    if '.' in ip:
        ip = [int(i) for i in ip.split('.')]

        if ip[0] == 10 or ip[0] == 127:
            return True

        elif ip[0] == [172]:
                if ip[1]>= 16 and ip[1]<= 31:
                    return True

        elif ip[0] == 192 and ip[1] == 168:
            return True

        return False
    else:
         raise ValueError("This function doesn't support IPv6")


srepr = reprlib.Repr()

srepr.maxdict = 25
srepr.maxlist = 10
srepr.maxset = 10
srepr.maxlong = 10
srepr.maxstring = 80
srepr.maxother = 80

saferepr = srepr.repr

#Partly based on code by Tamás of stack overflow.
def drop_perms(user, group = None):
    if os.name == 'nt':
        return
    if os.getuid() != 0:
        return

    import grp, pwd

    #Thanks to Gareth A. Lloyd of Stack Exchange!
    groups = [g.gr_gid for g in grp.getgrall() if user in g.gr_mem]
    gid = pwd.getpwnam(user).pw_gid
    groups.append(grp.getgrgid(gid).gr_gid)

    if  group == "__default__":
        group = user

    running_uid = pwd.getpwnam(user).pw_uid
    running_gid = grp.getgrnam(group).gr_gid
    os.setgroups(groups)
    os.setgid(running_gid)
    os.setuid(running_uid)

def display_yaml(d):
    d = copy.deepcopy(d)
    _yaml_esc(d)
    return yaml.dump(d)

def _yaml_esc(s,depth=0,r=""):
    if depth>20:
        raise RuntimeError()
    if isinstance(s,(str,float,int)):
        return
    if isinstance(s,list):
        x = range(0,len(s))
    else:
        x = s
    for i in x:
        if isinstance(s[i],str):
            s[i] = s[i].replace("\t","\\t").replace("\r",r)
        else:
            _yaml_esc(s[i])
        
            
