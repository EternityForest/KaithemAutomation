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

"""Provides a web interface over the authorization system"""

import cherrypy
from . import auth ,pages,messagebus
from .util import quote

class ManageAuthorization():
    @cherrypy.expose
    def index(self):
        pages.require("/admin/users.edit")
        return pages.get_template("auth/index.html").render(auth = auth)
       
    #The actual POST target to delete a user
    @cherrypy.expose
    def deluser(self,**kwargs):
        pages.require("/admin/users.edit")
        pages.postOnly()
        auth.removeUser(kwargs['user'])
        messagebus.postMessage("/system/auth/user/deleted",{'user':kwargs['user'],'deletedby':pages.getAcessingUser()})
        raise cherrypy.HTTPRedirect("/auth")
    
    #POST target for deleting a group
    @cherrypy.expose
    def delgroup(self,**kwargs):
        pages.require("/admin/users.edit")
        pages.postOnly()
        auth.removeGroup(kwargs['group'])
        messagebus.postMessage("/system/auth/group/deleted",{'group':kwargs['group'],'deletedby':pages.getAcessingUser()})
        raise cherrypy.HTTPRedirect("/auth")
    
    #INterface to select a user to delete
    @cherrypy.expose
    def deleteuser(self,**kwargs):
        pages.require("/admin/users.edit")
        return pages.get_template("auth/deleteuser.html").render()
    
    #Interface to select a group to delete
    @cherrypy.expose
    def deletegroup(self,**kwargs):
        pages.require("/admin/users.edit")
        return pages.get_template("auth/deletegroup.html").render()
        
    #Add user interface
    @cherrypy.expose
    def newuser(self):
        pages.require("/admin/users.edit")
        return pages.get_template("auth/adduser.html").render()
        
    #add group interface       
    @cherrypy.expose
    def newgroup(self):
        pages.require("/admin/users.edit")
        return pages.get_template("auth/newgroup.html").render()
        
    @cherrypy.expose
    #handler for the POST request to change user settings
    def newusertarget(self,**kwargs):
        #THIS IS A HACK TO PREVENT UNICODE STRINGS IN PY2.XX FROM GETTING THROUGH
        #BECAUSE QUOTE() IS USUALLY WHERE THEY CRASH. #AWFULHACK
        quote(kwargs['username'])
        pages.require("/admin/users.edit", noautoreturn=True)
        pages.postOnly()
        #create the new user
        auth.addUser(kwargs['username'],kwargs['password'])
        #Take the user back to the users page
        messagebus.postMessage('/system/notifications','New user "'+kwargs['username']+'" added')
        messagebus.postMessage("/system/auth/user/added",{'user':kwargs['username'],'addedby':pages.getAcessingUser()})

        raise cherrypy.HTTPRedirect("/auth/")
            
        
    @cherrypy.expose
    #handler for the POST request to change user settings
    def newgrouptarget(self,**kwargs):
        #THIS IS A HACK TO PREVENT UNICODE STRINGS IN PY2.XX FROM GETTING THROUGH
        #BECAUSE QUOTE() IS USUALLY WHERE THEY CRASH. #AWFULHACK
        quote(kwargs['groupname'])
        pages.require("/admin/users.edit", noautoreturn=True)
        pages.postOnly()
        #create the new user
        auth.addGroup(kwargs['groupname'])
        messagebus.postMessage("/system/auth/group/added",{'group':kwargs['groupname'],'addedby':pages.getAcessingUser()})

        #Take the user back to the users page
        raise cherrypy.HTTPRedirect("/auth/")
            
    @cherrypy.expose
    #handler for the POST request to change user settings
    def updateuser(self,user,**kwargs):
        pages.require("/admin/users.edit",  noautoreturn=True)
        pages.postOnly()

        if not kwargs['password'] == kwargs['password2']:
            raise RuntimeError('passwords must match')
        
        user=user.encode("latin-1").decode("utf-8")
        #THIS IS A HACK TO PREVENT UNICODE STRINGS IN PY2.XX FROM GETTING THROUGH
        #BECAUSE QUOTE() IS USUALLY WHERE THEY CRASH. #AWFULHACK
        quote(kwargs['username'])
        
        #Remove the user from all groups that the checkbox was not checked for
        for i in auth.Users[user]['groups']:
            if not ('Group'+i) in kwargs:
                auth.removeUserFromGroup(user,i)
            
        #Add the user to all checked groups
        for i in kwargs:
            if i[:5] == 'Group':
                if kwargs[i] == 'true':
                    auth.addUserToGroup(user,i[5:])
        if not kwargs['password'] =='':
            auth.changePassword(user,kwargs['password'])
            
        auth.changeUsername(user,kwargs['username'])
        auth.setUserSetting(user,"restrict-lan", 'lanonly' in kwargs)
        messagebus.postMessage("/system/auth/user/modified",{'user':user,'modifiedby':pages.getAcessingUser()})
        #Take the user back to the users page
        raise cherrypy.HTTPRedirect("/auth")
   
    @cherrypy.expose
    #handler for the POST request to change user settings
    def updategroup(self,group,**kwargs):
        pages.require("/admin/users.edit",  noautoreturn=True)
        pages.postOnly()
        group=group.encode("latin-1").decode("utf-8")

        auth.Groups[group]['permissions'] = []
        #Handle all the group permission checkboxes
        for i in kwargs:
            #Since HTTP args don't have namespaces we prefix all the permission checkboxes with permission
            if i[:10] == 'Permission':
                if kwargs[i] == 'true':
                    auth.addGroupPermission(group,i[10:])
                    
        #Take the user back to the users page
        auth.generateUserPermissions() #update all users to have the new permissions lists
        messagebus.postMessage("/system/auth/group/changed",{'group':group,'changedby':pages.getAcessingUser()})

        raise cherrypy.HTTPRedirect("/auth")
            
    #Settings page for one individual user    
    @cherrypy.expose
    def user(self,username):
        username=username.encode("latin-1").decode("utf-8")
        pages.require("/admin/users.edit")
        return pages.get_template("auth/user.html").render(
        usergroups=auth.Users[username]['groups'],
        groups= sorted(auth.Groups.keys()),
        username = username)
            
    #Settings page for one individual group    
    @cherrypy.expose
    def group(self,group):
        group=group.encode("latin-1").decode("utf-8")
        pages.require("/admin/users.edit")
        return pages.get_template("auth/group.html").render(
        auth = auth, name = group)
