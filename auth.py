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

#This file manages the concept of Users, Groups, and Permissions.
#A "User" is a user of the system who can belong to zero or more "Groups" each of which can have
#"Permissions". "Permissions" are strings like "WriteDisk". A user must be in at least one group
#With a given permission to do that thing.
#Users log in by means of a username and password and are given a token.
#The token lets them do things. A user is considered "Logged in" if he is in possession
#of a valid token

#Users and groups are saved in RAM and synched with the filesystem due to the goal
#of not using the filesystem much to save any SD cards.



import json
import base64
import os
import modules
import util
import directories
import time
import shutil
#These are the "built in" permissions required to control basic functions
#User code can add to these
BasePermissions = {
"/admin/users.edit":"Edit users, groups, and permissions, View and change usernames and passwords. Implies full access so watch out who you give this to.",
"/admin/mainpage.view": "View the main page of the application.",
"/admin/modules.view":  "View and download all module contents but not make any changes.",
"/admin/modules.edit":  "Create, Edit, Import, Upload, and Download modules and module contents. Gives root access essentially so watch out.",
"/admin/settings.view": "View but not change settings.",
"/admin/settings.edit": "Change core settings.",
"/admin/console.acess": "Use the remote python shell"
}

Permissions=BasePermissions


def importPermissionsFromModules():
    Permissions=BasePermissions
    with modules.modulesLock:
        for module in modules.ActiveModules.copy():#Iterate over all modules
		    #for every resource of type permission
            for resource in modules.ActiveModules[module].copy():
                if modules.ActiveModules[module][resource]['resource-type']=='permission':
				    #add it to the permissions list
                    Permissions[resource] = modules.ActiveModules[module][resource]['description']
                    

#Python doesn't let us make custom attributes on normal dicts
class User(dict):
    permissions = []
    pass

def changeUsername(old,new):
    #this should work because tokens stores object references ad we are not deleting
    #the actual user object
    Users[new] = Users.pop(old)
    Users[new]['username'] = new
    
def changePassword(user,newpassword):
    Users[user]['password'] = newpassword
    
def addUser(username,password):
    if not username in Users: #stop overwriting attempts
        Users[username] = User({'password':password,'username':username,'groups':[]})
        
def removeUser(user):
    x =Users.pop(user)
	#If the user has a token, delete that too
    if hasattr(x,'token'):
        if x.token in Tokens:
            Tokens.pop(x.token)
            
def removeGroup(group):
    x =Groups.pop(group)
	#Remove all references to that group from all users
    for i in Users:
        if group in Users[i]['groups']:
            Users[i]['groups'].remove(group)
    generateUserPermissions()
            
            
def addGroup(groupname):
        if not groupname in Groups: #stop from overwriting
                Groups[groupname] = {'permissions':[]}
        
def addUserToGroup(username,group):
    if group not in Users[username]['groups']: #Don't add multiple copies of a group
        Users[username]['groups'].append(group)
    generateUserPermissions(username)  #Regenerate the per-user permissions cache for that user

def removeUserFromGroup(username,group):
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
               temp = {'users':{},'groups':{}}
               
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
        if Users[username]['password'] == password:
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
    #Assemble the users and groups data and save it back where we found it
    temp = {"users":Users,"groups":Groups}
    p = os.path.join(directories.usersdir,str(time.time()))
    os.mkdir(p)
    f = open(os.path.join(p,"users.json"),"w")
    #prettyprint
    json.dump(temp,f,sort_keys=True, indent=4, separators=(',', ': '))
    f.close()
    f = open(os.path.join(p,"__COMPLETE__"),"w")
    f.write("completely arbitrary text")
    f.close()
    util.deleteAllButHighestNumberedNDirectories(directories.usersdir,2)
    
def addGroupPermission(group,permission):
        if permission not in Groups[group]['permissions']:
            Groups[group]['permissions'].append(permission)
        
def removeGroupPermission(group,permission):
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
