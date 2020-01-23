#Copyright Daniel Dunn 2013, 2015,2017
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

"""This file manages the concept of Users, Groups, and Permissions.
A "User" is a user of the system who can belong to zero or more "Groups" each of which can have
"Permissions". "Permissions" are strings like "WriteDisk". A user must be in at least one group
With a given permission to do that thing.
Users log in by means of a username and password and are given a token.
The token lets them do things. A user is considered "Logged in" if he is in possession
of a valid token"""

#Users and groups are saved in RAM and synched with the filesystem due to the goal
#of not using the filesystem much to save any SD cards.

from . import util,directories,modules_state,registry,messagebus
import json,base64,os,time,shutil,hashlib,base64,sys,yaml,hmac,struct,logging, threading
from src import config as cfg

noSecurityMode=False

mode = int(cfg.argcmd.nosecurity) if cfg.argcmd.nosecurity else None
#limit nosecurity to localhost
if mode == 1:
    bindto = '127.0.0.1'
    noSecurityMode = 1

#Unless it's mode 2
if mode == 2:
    noSecurityMode=2

#Unless it's mode 2
if mode == 3:
    noSecurityMode=3





lock= threading.RLock()

logger = logging.getLogger("system.auth")
#This maps raw tokens to users
Tokens = {}

#This maps hashed tokens to users. There's an easy timing attack I'd imagine
#with looking up tokens literally in a dict.
#So instead we hash them, with a salt.

#For discussion of similar things, see:
#https://crypto.stackexchange.com/questions/25607/practical-uses-for-timing-attacks-on-hash-comparisons-e-g-md5
#https://security.stackexchange.com/questions/9192/timing-attacks-on-password-hashes

#This post discusses token auth directly:
#https://stackoverflow.com/questions/18605294/is-devises-token-authenticatable-secure
tokenHashes = {}

with open(os.path.join(directories.datadir,"defaultusersettings.yaml")) as f:
    defaultusersettings = yaml.load(f)

#untested stuff that only works sometimes maybe for supporting logins by unix users
try:
    if sys.version_info < (3,3):
        from shlex import quote as shellquote
    else:
        from pipes import quote as shellquote
except:
    pass

if sys.version_info < (3,0):
    #In python 2 bytes is an alias for str
    #So we need to make a version bytes take a dummy arg to match 3.xx interface
    #It's ok if it doesn't actually do anything because of the fact that hash.update is fine with str in 2.xx
    def usr_bytes(s,x):
        "Bytes is an alias for str in py2x, so we make this wrapper so it has the same interface as py3x"
        return(str(s))

else:
    usr_bytes = bytes

#If nobody loadsusers from the file make sure nothing breaks(mostly for tests)
"""A dict of all the users"""
Users = {}
"""A dict of all the groups"""
Groups = {}

"""These are the "built in" permissions required to control basic functions
User code can add to these"""
BasePermissions = {
"/admin/users.edit":"Edit users, groups, and permissions, View and change usernames and passwords. Implies full access so watch out who you give this to.",
"/admin/mainpage.view": "View the main page of the application.",
"/admin/modules.view":  "View and download all module contents but not make any changes.",
"/admin/modules.edit":  "Create, Edit, Import, Upload, and Download modules and module contents. Gives full access essentially so watch out.",
"/admin/settings.view": "View but not change settings.",
"/admin/settings.edit": "Change core settings.",
"/admin/logging.edit": "Modify settings in the logging subsystem",
"/admin/eventoutput.view": "View the message logs.",
"/users/logs.view": "View the message logs.",
"/users/accountsettings.edit" : "Edit ones own account preferences",
"/users/tagpoints.view" : "View tagpoints",
"/users/tagpoints.edit" : "Override tagpoint values and modify configuration",
"/admin/errors.view": "View errors in resources. Note that /users/logs.view or /admin/modules.edit will also allow this.",
"/users/mixer.edit": "Control the audio mixing functionality",
"__all_permissions__": "Special universal permission that grants all permissions in the system. Use with care.",
"/users/alerts.view": "Required to view alerts",
"/users/alerts.acknowlege": "Required to acknowledge alerts"
}

Permissions=BasePermissions

"""True only if auth module stuff changed since last save, used to prevent unneccesary disk writes.
YOU MUST SET THIS EVERY TIME YOU CHANGE THE STATE AND WANT IT TO BE PERSISTANT"""
authchanged = False

#This __local_secret is really important, otherwise
#the timing attack might be even worse.
__local_secret= os.urandom(24)

def resist_timing_attack(data, maxdelay=0.0001):
    """Input dependant deterministic pseudorandom delay. Use to make sure delay
        is constant for a given user input, so that averaging won't work.
        Theory: http://blog.ircmaxell.com/2014/11/its-all-about-time.html
    """
    #Note the very high timing resolution.
    #Attackers can determine nanosecond level timings.
    h =hashlib.sha256(data+__local_secret).digest()
    t = struct.unpack("<Q", h[:8])[0]
    time.sleep(maxdelay*(t/2**64))

def importPermissionsFromModules():
    "Import all user defined permissions that are module resources into the global list of modules that can be assigned, and delete any that are no loger defined in modules."
    Permissions=BasePermissions
    with modules_state.modulesLock:
        for module in modules_state.ActiveModules.copy():#Iterate over all modules
            #for every resource of type permission
            for resource in modules_state.ActiveModules[module].copy():
                if modules_state.ActiveModules[module][resource]['resource-type']=='permission':
                    #add it to the permissions list
                    Permissions[util.split_escape(resource,'/','\\')[-1]] = modules_state.ActiveModules[module][resource]['description']

def getPermissionsFromMail():
    """Generate a permission for each mailing list, and add that permission to the global list of assignable permissions"""
    for i in registry.get('system/mail/lists',{}):
        Permissions["/users/mail/lists/"+i+"/subscribe"] = "Subscribe to mailing list with given UUID"

#Python doesn't let us make custom attributes on normal dicts
class User(dict):
    permissions = []
    pass

def changeUsername(old,new):
    "Change a user's username"
    global auth
    with lock:
        authchanged = True
        #this should work because tokens stores object references ad we are not deleting
        #the actual user object
        Users[new] = Users.pop(old)
        Users[new]['username'] = new

def changePassword(user,newpassword):
    "Change a user's password"
    global authchanged
    if len(newpassword)>256:
        raise ValueError("Password cannot be longer than 256 bytes")
    with lock:
        authchanged = True
        salt = os.urandom(16)
        salt64 = base64.b64encode(salt)
        #Python is a great language. But sometimes I'm like WTF???
        #Base64 should never return a byte string. The point of base64 is to store binary data
        #as normal strings. So why would I ever want a base64 value stores as bytes()?
        #Anyway, python2 doesn't do that, so we just decode it if its new python.
        if sys.version_info >= (3,0):
            salt64 = salt64.decode("utf8")
        Users[user]['salt'] = salt64
        m = hashlib.sha256()
        m.update(usr_bytes(newpassword,'utf8'))
        m.update(salt)
        p = base64.b64encode(m.digest())
        if sys.version_info >= (3,0):
            p = p.decode("utf8")
        Users[user]['password'] = p


def addUser(username,password):
    global authchanged
    with lock:
        authchanged = True
        if not username in Users: #stop overwriting attempts
            Users[username] = User({'username':username,'groups':[]})
            Users[username].limits = {}
            changePassword(username,password)

def removeUser(user):
    global authchanged
    with lock:
        authchanged = True
        x =Users.pop(user)
        #If the user has a token, delete that too
        if hasattr(x,'token'):
            if x.token in Tokens:
                Tokens.pop(x.token)
                try:
                    tokenHashes.pop(hashToken(x.token))
                except:
                    raise

def removeGroup(group):
    global authchanged
    with lock:
        authchanged = True
        x =Groups.pop(group)
        #Remove all references to that group from all users
        for i in Users:
            if group in Users[i]['groups']:
                Users[i]['groups'].remove(group)
        generateUserPermissions()


def addGroup(groupname):
    global authchanged
    with lock:
        authchanged = True
        if not groupname in Groups: #stop from overwriting
                Groups[groupname] = {'permissions':[]}

def addUserToGroup(username,group):
    global authchanged
    with lock:
        authchanged = True
        if group not in Users[username]['groups']: #Don't add multiple copies of a group
            Users[username]['groups'].append(group)
        generateUserPermissions(username)  #Regenerate the per-user permissions cache for that user

def removeUserFromGroup(username,group):
    global authchanged
    with lock:
        authchanged = True
        Users[username]['groups'].remove(group)
        generateUserPermissions(username) #Regenerate the per-user permissions cache for that user

def promptGenerateUser(username="admin"):
    with lock:
        global authchanged
        p = "samevscdfghjkl,ljhgfdsfhjmk,.lkjhgfdgnm,kjgfdnmj,kjuytredsfvbnhjmk?P>O:P_O>{:?{|<>/,.(0%(%(*5)))}"
        p2 = "differentgfbhnjmuytrfdcvbnjuytfgcvbnmjuytgfvbnmjkiuytgfvbnmjuytgfvbnmjkuyhgf"
        try:
            input2=raw_input
        except:
            input2=input
        while not p == p2:
            p = "samejytfdcvbnjytfgvbnmjuytrfdcv bnmjuytgfvbnmjuytgfvbnmjytgfvbnjytgfcvliku7ytrfghjuytrfg:{<}>?<MLNI)*&(Y?>:I)"
            p2 = "differentkyhgfvbnmjuytrdcxvbhjytredsxcvbnjkjnmkliuytrdsfgtrewsxdcvghjkmkiuhgft54ewe3wdfghujhjkiu76y7yuijh"
            p = input2("Account %s created. Choose password:"%(username))
            p2 = input2("Reenter Password:")
            if not p==p2:
                print("password mismatch")

        m = hashlib.sha256()
        r = os.urandom(16)
        r64 = base64.b64encode(r).decode("utf-8")
        m.update(usr_bytes(p,'utf-8'))
        m.update(r)
        pwd = base64.b64encode(m.digest()).decode('utf-8')

        temp = {
                "groups": {
                    "Administrators": {
                        "permissions": [
                            "__all_permissions__"
                        ]
                    }
                },
                "users": {
                    username: {
                        "groups": [
                            "Administrators"
                        ],
                        "password": pwd,
                        "username": "admin",
                        "salt": r64
                    }
                }
            }
        global Users
        Users = temp['users']
        global Groups
        Groups = temp['groups']
        global Tokens
        Tokens = {}
        tokenHashes = {}
        for user in Users:
            #What an unreadable line! It turs all the dicts in Users into User() instances
            Users[user] = User(Users[user])
            assignNewToken(user)
        authchanged = True
        generateUserPermissions()

def tryToLoadFrom(d):
    with lock:
        if os.path.isfile(os.path.join(d,"__COMPLETE__")):
            try:
                f = open(os.path.join(d,'users.json'))
                temp = json.load(f)
            finally:
                f.close()
            global Users
            Users = temp['users']
            global Groups
            Groups = temp['groups']
            global Tokens
            Tokens = {}
            tokenHashes = {}
            for user in Users:
                #What an unreadable line! It turs all the dicts in Users into User() instances
                Users[user] = User(Users[user])
                assignNewToken(user)
            generateUserPermissions()
            return True
        else:
            raise RuntimeError("No complete marker found")
        logger.info("Loaded auth data from "+d)

data_bad = False
def initializeAuthentication():
    with lock:
        "Load the saved users and groups, and the permissions from the mailing lists, but not the permissions from the modules. "
        #If no file use default but set filename anyway so the dump function will work
        #Gets the highest numbered of all directories that are named after floating point values(i.e. most recent timestamp)
        loaded = False
        try:
            tryToLoadFrom(os.path.join(directories.usersdir,"data"))
            loaded = True
        except Exception as e:
            logger.exception("Error loading auth data, may be able to continue from old state")
            messagebus.postMessage("/system/notifications/errors","Error loading auth data, may be able to continue from old state:\n"+str(e))
            data_bad=True
            try:
                dirname = util.getHighestNumberedTimeDirectory(directories.usersdir)
                tryToLoadFrom(dirname)
                loaded =True
                messagebus.postMessage("/system/notifications/warnings",
                """Saving was interrupted. Using last version of users list.
                This could create a secuirty issue if the old version allowes access to a malicious user.
                To suppress this warning, please review your users and groups, and re-save the server state. You must make at least
                one change to users and groups (Or click save on a user or group without making changes)
                for them to actually be saved.
                """)
            except:
                messagebus.postMessage("/system/notifications/errors","Could not load old state:\n"+str(e))
                pass

        if not loaded:
            time.sleep(2)
            promptGenerateUser()
            messagebus.postMessage("/system/notifications/warnings","No valid users file, using command line prompt")


        getPermissionsFromMail()

def generateUserPermissions(username = None):
   """Generate the list of permissions for each user from their groups plus __guest__"""
   with lock:
        #TODO let you do one user at a time
        #Give each user all of the permissions that his or her groups have
        global Users
        for i in Users:
            limits = {}
            Users[i].permissions = []
            for j in Users[i]['groups']:
                #Handle nonexistant groups
                if not j in Groups:
                    logger.warning("User "+i+" is member of nonexistant group "+ j)

                for k in Groups[j]['permissions']:
                    Users[i].permissions.append(k)

                #A user has access to the highest limit of all the groups he's in
                for k in Groups[j].get('limits',{}):
                    limits[k] = max( Groups[j].get('limits',{})[k],limits.get(k,0))
            Users[i].limits = limits
            #If the user has a token, update the stored copy of user in the tokens dict too
            if hasattr(Users[i],'token'):
                Tokens[Users[i].token] = Users[i]
                tokenHashes[hashToken(Users[i].token)] = Users[i]

def userLogin(username,password):
    """return a base64 authentication token on sucess or return False on failure"""
    with lock:
        if  username in Users:
            m = hashlib.sha256()
            m.update(usr_bytes(password,'utf8'))
            m.update(base64.b64decode(Users[username]['salt'].encode('utf8')  ))
            m = m.digest()
            if hmac.compare_digest(base64.b64decode(Users[username]['password'].encode('utf8')), m):
                #We can't just always assign a new token because that would break multiple
                #Logins as same user
                if not hasattr(Users[username],'token'):
                    assignNewToken(username)
                return (Users[username].token)
        return "failure"



def checkTokenPermission(token,permission):
    """return true if the user associated with token has the permission"""
    with lock:
        token = hashToken(token)
        if token in tokenHashes:
            if permission in tokenHashes[token].permissions:
                return True
            else:
                if '__all_permissions__' in tokenHashes[token].permissions:
                    return True
                else:
                    return False
        else:
                return False

#Remove references to deleted permissions
#NO-OP, Lets just let user manually uncheck them.
def destroyUnusedPermissions():
   pass
   # for i in Groups:
    #    for j in Groups[i]['permissions']:
     #       if j not in Permissions:
      #          Groups[i]['permissions'].pop(j)


#Save the state of the entire users/groups/permissions system

def dumpDatabase():
    """Save the state of the users and groups to a file."""
    with lock:
        global authchanged
        if not authchanged:
            return False
        x = Users.copy()
        for i in x:
            #Don't save the login history.
            if 'loginhistory' in x[i]:
                del x[i]['loginhistory']
        #Assemble the users and groups data and save it back where we found it
        temp = {"users":x,"groups":Groups.copy()}

        if time.time()> util.min_time:
            t = time.time()
        else:
            t = int(util.min_time) +1.234

        if os.path.isdir(os.path.join(directories.usersdir,str("data"))):
        #Copy the data found in data to a new directory named after the current time. Don't copy completion marker

            #If the data dir was corrupt, copy it to a different place than a normal backup.
            if not data_bad:
                copyto = os.path.join(directories.usersdir,str(t))
            else:
                copyto = os.path.join(directories.usersdir,str(t)+"INCOMPLETE")

            shutil.copytree(os.path.join(directories.usersdir,str("data")), copyto,
                            ignore=shutil.ignore_patterns("__COMPLETE__"))
            #Add completion marker at the end
            with open(os.path.join(copyto,'__COMPLETE__'),"w") as x:
                util.chmod_private_try(os.path.join(copyto,'__COMPLETE__'), execute=False)
                x.write("This file certifies this folder as valid")


        p = os.path.join(directories.usersdir,"data")

        if os.path.isfile(os.path.join(p,'__COMPLETE__')):
            os.remove(os.path.join(p,'__COMPLETE__'))

        util.ensure_dir2(p)
        util.chmod_private_try(p)
        try:
            f = open(os.path.join(p,"users.json"),"w")
            util.chmod_private_try(os.path.join(p,"users.json"),execute=False)
            #pretty print
            json.dump(temp,f,sort_keys=True, indent=4, separators=(',', ': '))
        finally:
            f.close()

        try:
            f = open(os.path.join(p,"__COMPLETE__"),"w")
            util.chmod_private_try(os.path.join(p,"__COMPLETE__"),execute=False)
            f.write("completely arbitrary text")
        finally:
            f.close()
        util.deleteAllButHighestNumberedNDirectories(directories.usersdir,2)
        authchanged = False
        return True

def setGroupLimit(group,limit,val):
    with lock:
        global authchanged
        authchanged = True
        if val == 0:
            try:
                Groups[group].get('limits',{}).pop(limit)
            except:
                pass
        else:
            #TODO unlikely race condition here
            gr = Groups[group]
            if not 'limits' in gr:
                gr['limits'] = {}
            gr['limits'][limit] = val

def addGroupPermission(group,permission):
    """Add a permission to a group"""
    with lock:
        global authchanged
        authchanged = True
        if permission not in Groups[group]['permissions']:
            Groups[group]['permissions'].append(permission)

def removeGroupPermission(group,permission):
    global authchanged
    with lock:
        authchanged = True
        Groups[group]['permissions'].remove(permission)

#This is a salt for the token hint. The idea being that we look
#up the tokens by hashing them, not by actually looking them up.
#The attacker has no information about the token hashes or the token secret,
#so it should be safe to compare them and look them in dicts.
#due to them being completely secret 
#and random

#TODO: Someone who knows more about crypto should look this over.


def whoHasToken(token):
    return tokenHashes[hashToken(token)]['username']

tokenHashSecret = os.urandom(24)
def hashToken(token):
    return hashlib.sha256(usr_bytes(token,"utf8")+tokenHashSecret).digest()

def assignNewToken(user):
    """Log user out by defining a new token"""
    with lock:
        #Generate new token
        x = base64.b64encode(os.urandom(24)).decode()
        #Get the old token, delete it, and assign a new one
        if hasattr(Users[user],'token'):
            oldtoken = Users[user].token
            del Tokens[oldtoken]
            try:
                del tokenHashes[hashToken(oldtoken)]
            except:
                #Not there?
                pass
        Users[user].token = x
        Tokens[x] = Users[user]
        tokenHashes[hashToken(x)] = Users[user]

class UnsetSettingException:
    pass

def setUserSetting(user,setting,value):
    with lock:
        global authchanged
        authchanged = True
        un=user
        if user == "<unknown>":
            return
        user = Users[user]
        #This line is just there to raise an error on bad data.
        json.dumps(value)
        if not 'settings' in user:
            user['settings'] = {}

        Users[un]['settings'][setting]= value

def getUserSetting(user,setting):
    #I suppose this doesnt need a lock?
    if user == '<unknown>':
        return defaultusersettings[setting]
    user = Users[user]
    if not 'settings' in user:
        return defaultusersettings[setting]


    if setting in user['settings']:
        return user['settings'][setting]
    else:
        return defaultusersettings[setting]

def getUserLimit(user,limit,maximum=2**64):
    """Return the user's limit for any limit category, or 0 if not set. Limit to maximum. 
        If user has __all_permissions__, limit _is_ maximum.
    """
    if '__guest__' in Users:
            guestlimit = min(Users['__guest__'].limits.get(limit,0),maximum)
    else:
        guestlimit = 0 
    if user in Users:
        if not '__all_permissions__' in  Users[user].permissions:
            val = max(min(Users[user].limits.get(limit,0),maximum),guestlimit)
        else:
            val = maximum
        return min(val,maximum)
    else:
        return guestlimit
    return 0

def canUserDoThis(user,permission):
    """Return True if given user(by username) has access to the given permission"""

    if not user in Users:
        if '__guest__' in Users and permission in Users["__guest__"].permissions:
            return True
        else:
            if '__guest__' in Users and "__all_permissions__" in Users["__guest__"].permissions:
                return True

            if noSecurityMode==1:
                if cherrypy.request.remote.ip.startswith("127."):
                    return True
                else:
                    return False
                    
            if noSecurityMode==2:
                x = cherrypy.request.remote.ip
                if x.startswith("192."):
                    return True
                if x.startswith("10."):
                    return True
                if x.startswith("127."):
                    return True
                return False
        return False

    if permission in Users[user].permissions:
        return True

    if '__all_permissions__' in Users[user].permissions:
        return True

    if '__guest__' in Users and "__all_permissions__" in Users["__guest__"].permissions:
        return True
    
    if '__guest__' in Users and "__all_permissions__" in Users["__guest__"].permissions:
        return True


    return False
import cherrypy

def sys_login(username, password):
    return subprocess.check_output('echo "'+ shellquote(password[:40]) +'" | sudo  -S -u ' + shellquote(username[:25]) +' groups', shell=True)[:-1]
