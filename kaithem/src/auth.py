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

"""This file manages the concept of Users, Groups, and Permissions.
A "User" is a user of the system who can belong to zero or more "Groups" each of which can have
"Permissions". "Permissions" are strings like "WriteDisk". A user must be in at least one group
With a given permission to do that thing.
Users log in by means of a username and password and are given a token.
The token lets them do things. A user is considered "Logged in" if he is in possession
of a valid token"""

#Users and groups are saved in RAM and synched with the filesystem due to the goal
#of not using the filesystem much to save any SD cards.

from . import util,directories,modules_state,registry
import json,base64,os,time,shutil,hashlib,base64,sys,yaml


with open(os.path.join(directories.datadir,"defaultusersettings.yaml")) as f:
    defaultusersettings = yaml.load(f)

if sys.version_info < (3,0):
    #In python 2 bytes is an alias for str
    #So we need to make a version bytes take a dummy arg to match 3.xx interface
    #It's ok if it doesn't actually do anything because of the fact that hash.update is fine with str in 2.xx
    def usr_bytes(s,x):
        return(str(s))
    
else:
    usr_bytes = bytes
    
#If nobody loadsusers from the file make sure nothing breaks(mostly for tests)
Users = {}
Groups = {}

#These are the "built in" permissions required to control basic functions
#User code can add to these
BasePermissions = {
"/admin/users.edit":"Edit users, groups, and permissions, View and change usernames and passwords. Implies full access so watch out who you give this to.",
"/admin/mainpage.view": "View the main page of the application.",
"/admin/modules.view":  "View and download all module contents but not make any changes.",
"/admin/modules.edit":  "Create, Edit, Import, Upload, and Download modules and module contents. Gives root access essentially so watch out.",
"/admin/settings.view": "View but not change settings.",
"/admin/settings.edit": "Change core settings.",
"/admin/logging.edit": "Modify settings in the logging subsystem",
"/users/logs.view": "View the message logs.",
"/users/accountsettings.edit" : "Edit ones own account preferences",
"__all_permissions__": "Special universal permission that grants all permissions in the system. Use with care."
}

Permissions=BasePermissions

#True only if auth module stuff changed since last save
#YOU MUST SET THIS EVERY TIME YOU CHANGE THE STATE AND WANT IT TO BE PERSISTANT
authchanged = False

def importPermissionsFromModules():
    Permissions=BasePermissions
    with modules_state.modulesLock:
        for module in modules_state.ActiveModules.copy():#Iterate over all modules
            #for every resource of type permission
            for resource in modules_state.ActiveModules[module].copy():
                if modules_state.ActiveModules[module][resource]['resource-type']=='permission':
                    #add it to the permissions list
                    Permissions[resource] = modules_state.ActiveModules[module][resource]['description']
 
def getPermissionsFromMail():
    for i in registry.get('system/mail/lists',{}):
        Permissions["/users/mail/lists/"+i+"/subscribe"] = "Subscribe to mailing list with given UUID"

#Python doesn't let us make custom attributes on normal dicts
class User(dict):
    permissions = []
    pass

def changeUsername(old,new):
    global authchanged
    authchanged = True
    #this should work because tokens stores object references ad we are not deleting
    #the actual user object
    Users[new] = Users.pop(old)
    Users[new]['username'] = new
    
def changePassword(user,newpassword):
    global authchanged
    authchanged = True
    salt = os.urandom(16)
    salt64 = base64.b64encode(salt)
    #Python is a great language. But sometimes I'm like WTF???
    #Base64 should never return a byte string. The point of base64 is to store binary data
    #as normal strings. So why would I ever want a base64 value stores as bytes()?
    #Anyway, python2 doesn't do that, so we just decode it if its new python.
    if sys.version_info > (3,0):
        salt64 = salt64.decode("utf8")
    Users[user]['salt'] = salt64
    m = hashlib.sha256()
    m.update(usr_bytes(newpassword,'utf8'))
    m.update(salt)
    p = base64.b64encode(m.digest())
    if sys.version_info > (3,0):
        p = p.decode("utf8")
    Users[user]['password'] = p
    
    
def addUser(username,password):
    global authchanged
    authchanged = True
    if not username in Users: #stop overwriting attempts
        Users[username] = User({'username':username,'groups':[]})
        changePassword(username,password)
        
def removeUser(user):
    global authchanged
    authchanged = True
    x =Users.pop(user)
    #If the user has a token, delete that too
    if hasattr(x,'token'):
        if x.token in Tokens:
            Tokens.pop(x.token)
            
def removeGroup(group):
    global authchanged
    authchanged = True
    x =Groups.pop(group)
    #Remove all references to that group from all users
    for i in Users:
        if group in Users[i]['groups']:
            Users[i]['groups'].remove(group)
    generateUserPermissions()
            
            
def addGroup(groupname):
    global authchanged
    authchanged = True
    if not groupname in Groups: #stop from overwriting
            Groups[groupname] = {'permissions':[]}
        
def addUserToGroup(username,group):
    global authchanged
    authchanged = True
    if group not in Users[username]['groups']: #Don't add multiple copies of a group
        Users[username]['groups'].append(group)
    generateUserPermissions(username)  #Regenerate the per-user permissions cache for that user

def removeUserFromGroup(username,group):
    global authchanged
    authchanged = True
    Users[username]['groups'].remove(group)
    generateUserPermissions(username) #Regenerate the per-user permissions cache for that user

def initializeAuthentication():
    #If no file use default but set filename anyway so the dump function will work
    for i in range(0,15):
        #Gets the highest numbered of all directories that are named after floating point values(i.e. most recent timestamp)
        name = util.getHighestNumberedTimeDirectory(directories.usersdir)
        possibledir = os.path.join(directories.usersdir,name)
        
        #__COMPLETE__ is a special file we write to the dump directory to show it as valid
        if '''__COMPLETE__''' in util.get_files(possibledir):
            try:
                f = open(os.path.join(possibledir,'users.json'))
                temp = json.load(f)
                f.close()
            except:
                p = "same"
                p2 = "different"
                while not p == p2:
                    p = "same"
                    p2 = "different"
                    p = input("No users list found. Account 'admin' created. Choose password:")
                    p2 = input("Reenter Password:")
                    if not p==p2:
                        print("password mismatch")
                        
                m = hashlib.sha256()
                r = os.urandom(16)
                r64 = base64.b64encode(r)
                m.update(p)
                m.update(r)
                pwd = base64.b64encode(m)
                
                temp = {
                        "groups": {
                            "Administrators": {
                                "permissions": [
                                    "/admin/settings.edit",
                                    "/admin/logging.edit",
                                    "/admin/users.edit",
                                    "/users/pagelisting.view",
                                    "/admin/modules.edit",
                                    "/admin/settings.view",
                                    "/admin/mainpage.view",
                                    "/users/logs.view",
                                    "/admin/modules.view"
                                ]
                            }
                        },
                        "users": {
                            "admin": {
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
            for user in Users:
                #What an unreadable line! It turs all the dicts in Users into User() instances
                Users[user] = User(Users[user])
                assignNewToken(user)
                
            generateUserPermissions()
            break #We sucessfully found the latest good users.json dump! so we break the loop
        else:
            #If there was no flag indicating that this was an actual complete dump as opposed
            #To an interruption, rename it and try again
            shutil.copytree(possibledir,os.path.join(directories.usersdir,name+"INCOMPLETE"))
            shutil.rmtree(possibledir)
    getPermissionsFromMail()
    
def generateUserPermissions(username = None):
    #TODO let you do one user at a time
    """Generate the list of permissions for each user from their groups"""
    #Give each user all of the permissions that his or her groups have
    global Users
    for i in Users:
        Users[i].permissions = []
        for j in Users[i]['groups']:
            for k in Groups[j]['permissions']:
                Users[i].permissions.append(k)
        #If the user has a token, update the stored copy of user in the tokens dict too
        if hasattr(Users[i],'token'):
            Tokens[Users[i].token] = Users[i]
                
def userLogin(username,password):
    """return a base64 authentication token on sucess or return False on failure"""
    if  username in Users:
        m = hashlib.sha256()
        m.update(usr_bytes(password,'utf8'))
        print(Users[username]['salt'])
        m.update(base64.b64decode(Users[username]['salt'].encode('utf8')  ))
        m = m.digest()
        if base64.b64decode(Users[username]['password'].encode('utf8')) == m:
            #We can't just always assign a new token because that would break multiple
            #Logins as same user
            if not hasattr(Users[username],'token'):
                assignNewToken(username)
            return (Users[username].token)
    return "failure"

def checkTokenPermission(token,permission):
    """return true if the user associated with token has the permission"""
    if token in Tokens:
        if permission in Tokens[token].permissions:
            return True
        else:
            if '__all_permissions__' in Tokens[token].permissions:
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
    global authchanged
    if not authchanged:
        return False
    
    #Assemble the users and groups data and save it back where we found it
    temp = {"users":Users,"groups":Groups}
    p = os.path.join(directories.usersdir,str(time.time()))
    os.mkdir(p)
    f = open(os.path.join(p,"users.json"),"w")
    #pretty print
    json.dump(temp,f,sort_keys=True, indent=4, separators=(',', ': '))
    f.close()
    f = open(os.path.join(p,"__COMPLETE__"),"w")
    f.write("completely arbitrary text")
    f.close()
    util.deleteAllButHighestNumberedNDirectories(directories.usersdir,2)
    authchanged = False
    return True

    
def addGroupPermission(group,permission):
    global authchanged
    authchanged = True
    if permission not in Groups[group]['permissions']:
        Groups[group]['permissions'].append(permission)
    
def removeGroupPermission(group,permission):
    global authchanged
    authchanged = True
    Groups[group]['permissions'].remove(permission)
        
def whoHasToken(token):
    return Tokens[token]['username']
    

def assignNewToken(user):
    """Log user out by defining a new token"""
    #Generate new token
    x = str(base64.b64encode(os.urandom(24)))
    #Get the old token, delete it, and assign a new one
    if hasattr(Users[user],'token'):
        oldtoken = Users[user].token
        del Tokens[oldtoken]
    Users[user].token = x
    Tokens[x] = Users[user]
    
class UnsetSettingException:
    pass

def setUserSetting(user,setting,value):
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
        if user == '<unknown>':
            return defaultusersettings[setting]
        user = Users[user]
        if not 'settings' in user:
            return defaultusersettings[setting]

        
        if setting in user['settings']:
            return user['settings'][setting]
        else:
            return defaultusersettings[setting]

def canUserDoThis(user,permission):
        #If the special __guest__ user can do it, anybody can.
    if '__guest__' in Users:
        if permission in Users['__guest__'].permissions:
            return True
        
    if '__all_permissions__' in Users[user].permissions:
        return True
    
    if permission in Users[user].permissions:
        return True
    return False

        